"""Causal (chunk-by-chunk) sampling for long guide-latent edits: one render, no shot seams.

Adapted from SolarRenderer's causal sampler (https://github.com/Enderfga/SolarRenderer, comfyui/causal.py,
Apache-2.0; its held-silence asset h3_silence_153_158_170.safetensors is redistributed here under the same license).
Differences: it takes Henge's H3 conditioning (the aligned Add Guide keyframe over every target frame, plus native
reference pictures) on any LoRA stack, and steps with Euler like the shot renderer.

Each chunk of `chunk` latent frames (1 latent frame = 4 video frames) is denoised against a key/value cache holding
the prompt, the reference pictures, the held silence, the guide of its own and the previous `window - 1` chunks and
the rendered frames of those previous chunks - never anything later. The LoRAs Henge ships were trained on full
bidirectional clips, so this is an experimental path: the guide keeps every chunk on the source timeline, the cached
rendered chunks carry identity and look forward.
"""
import logging
import os

import torch

import comfy.model_management as mm
import comfy.nested_tensor
import comfy.quant_ops
import comfy.utils
import latent_preview
from comfy.ldm.minimax.model import PackedLayout, pack_audio, patchify_video, rope_rotation_table, unpatchify_video

SILENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'h3_silence_153_158_170.safetensors')
STATIC_TIME = 1.0      # prompt rows
CLEAN_LEVEL = 0.999    # references, guide, soundtrack and every rendered chunk as later chunks see them
SHIFT_VIDEO = 12.0
TAG_VIDEO, TAG_AUDIO = 0, 2


def silence(length, edge=20):
    """H3's encoded silence over `length` audio latents [1, 32, 2, length]; the middle column repeats past 170 frames."""
    s = comfy.utils.load_torch_file(SILENCE)['silence_170f'].float().permute(1, 0, 2).unsqueeze(0)
    columns = s.shape[-1]
    if length <= columns:
        return s[..., :length]
    middle = s[..., columns // 2:columns // 2 + 1].expand(*s.shape[:-1], length - 2 * edge)
    return torch.cat((s[..., :edge], middle, s[..., columns - edge:]), dim=-1).contiguous()


def shifted_sigmas(steps, shift=SHIFT_VIDEO):
    base = torch.linspace(1.0, 0.0, steps + 1, dtype=torch.float32)
    return shift * base / (1.0 + (shift - 1.0) * base)


def attend(q, k, v):  # [1, tokens, heads, head_dim]
    return torch.nn.functional.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2)).transpose(1, 2)


class Cache:
    """Per layer, keys/values (after the rotary) of written rows under (kind, chunk); chunks of a kind older than the
    window are dropped as new ones arrive."""

    def __init__(self, window, device):
        self.layers, self.window, self.device = {}, window, device

    def put(self, layer, name, key, value):
        entries = self.layers.setdefault(layer, {})
        entries[name] = (key.to(self.device, copy=True), value.to(self.device, copy=True))
        kind, chunk = name
        for old in [n for n in entries if n[0] == kind and n[1] <= chunk - self.window]:
            entries.pop(old)

    def get(self, layer, name, device):
        key, value = self.layers[layer][name]
        return key.to(device, non_blocking=True), value.to(device, non_blocking=True)


class CausalRun:
    def __init__(self, dm, device, dtype, context, extra, latent_shapes, seed, cache_device, window):
        self.dm, self.device, self.dtype, self.window = dm, device, dtype, window
        self.generator = torch.Generator(device=device).manual_seed(int(seed))
        (_, _, frames, height, width), audio_t = latent_shapes[0], latent_shapes[1][-1]
        if height % 2 or width % 2:
            raise ValueError('Causal sampling needs width and height in multiples of 32')
        self.frames, self.height, self.width = frames, height, width
        self.per_frame = (height // 2) * (width // 2)

        guide = [k for k in extra.get('minimax_keyframes') or [] if k.get('latent') is not None and k['latent'].shape[2] == frames][:1]
        if not guide:
            raise ValueError('Causal sampling needs the aligned guide (Guide Latents conditioning) over every target frame')
        refs = [r for r in extra.get('minimax_refs') or [] if r.get('kind') == 'image']
        if len(refs) != len(extra.get('minimax_refs') or []):
            raise ValueError('Causal sampling takes reference pictures only (no TARA reference video)')
        context = context.to(device, dtype)
        layout = PackedLayout(context.shape[1], frames, height, width, audio_t, keyframes=guide, refs=refs or None)
        self.positions = layout.position_ids
        segments = layout.segments
        self.text = segments[0][:2]
        self.guide_start = next(s[0] for s in segments if s[2] == 'cond')
        self.refs = [s[:2] for s in segments if s[2] == 'ref_img']
        self.audio = next(s[:2] for s in segments if s[2] == 'audio')
        self.video_start = next(s[0] for s in segments if s[2] == 'video')
        # guide rows then reference rows, noised to the cond level exactly as ComfyUI does for a full render
        self.cond_rows = dm._cond_video_rows({'cond_video_latents': [guide[0]['latent']] + [r['latent'] for r in refs], 'seed': int(seed)}, device)
        self.text_embed = dm.preprocess_text_embeds(context)[0]
        tags = extra.get('minimax_token_tags')
        self.text_tags = tags.view(-1).tolist() if tags is not None else [1] * context.shape[1]
        clean = silence(audio_t).to(device)
        noise = torch.randn(clean.shape, generator=self.generator, device=device, dtype=torch.float32)
        self.audio_embed = dm.audio_patch_proj(pack_audio(CLEAN_LEVEL * clean + (1.0 - CLEAN_LEVEL) * noise)).to(dtype)
        self.cache = Cache(window, cache_device)

    def video_embed(self, rows):
        return self.dm.video_patch_proj(rows.to(self.device, torch.float32)).to(self.dtype)

    def forward(self, pieces, cached, commit, sigma=None):
        """Run rows `pieces` [(embed, (start, stop) in the packed sequence, time, tag)] against the cached `cached`;
        write their keys/values as `commit`; with `sigma`, return the last piece's velocity rows."""
        dm = self.dm
        h = torch.cat([p[0] for p in pieces]).contiguous()
        positions = torch.cat([self.positions[a:b] for _, (a, b), _, _ in pieces])
        times = sorted({p[2] for p in pieces})
        index = {t: i for i, t in enumerate(times)}
        mod, row = [], 0
        for embed, _, t, tag in pieces:
            n = embed.shape[0]
            if isinstance(tag, list):  # prompt rows carry their own tags
                start = 0
                for i in range(1, n + 1):
                    if i == n or tag[i] != tag[start]:
                        mod.append((row + start, row + i, index[t] * 3 + int(tag[start])))
                        start = i
            else:
                mod.append((row, row + n, index[t] * 3 + tag))
            row += n
        t_vals = torch.tensor(times, dtype=torch.float32, device=self.device)
        if dm.use_adaln_curves:
            table = mm.cast_to(dm.adaln_t_table, device=self.device)
            pos = t_vals.clamp(0.0, 1.0) * (table.shape[0] - 1)
            i0 = pos.floor().long().clamp(max=table.shape[0] - 2)
            t_emb = torch.lerp(table[i0], table[i0 + 1], (pos - i0).unsqueeze(1))
        else:
            t_emb = dm.time_embedder(t_vals).to(self.dtype)
        rope = rope_rotation_table(dm.rope_freqs(positions, self.device), self.dtype)
        for layer, block in enumerate(dm.blocks):
            h = block(h, t_emb, mod, rope, transformer_options={}, attention=self.attention(block.attn, layer, cached, commit))
        if sigma is None:
            return None
        n = pieces[-1][0].shape[0]
        a, b = row - n, row
        video, _ = dm.final_layer(h, t_emb, (a, b, index[pieces[-1][2]]), (b, b, index[pieces[-1][2]]),
                                  torch.tensor(sigma), None, (SHIFT_VIDEO, 3.0))
        return video

    def attention(self, attn, layer, cached, commit):
        def run(x, rope_freqs=None, transformer_options={}):
            s, heads, dim = x.shape[0], attn.heads, attn.head_dim
            q, k, v = attn.qkv_proj(x).split(heads * dim, dim=-1)
            v = v.view(s, heads, dim)
            q, k = q.view(1, s, heads, dim), k.view(1, s, heads, dim)
            qw = mm.cast_to(attn.q_norm.weight, device=x.device)
            kw = mm.cast_to(attn.k_norm.weight, device=x.device)
            comfy.quant_ops.ck.rms_rope_split_half_(q, k, rope_freqs, qw, kw, epsilon=attn.q_norm.eps, rot_dim=rope_freqs.shape[-3] * 2)
            k = k[0]
            if commit is not None:
                self.cache.put(layer, commit, k, v)
            keys, values = [], []
            for name in cached:
                ck, cv = self.cache.get(layer, name, x.device)
                keys.append(ck)
                values.append(cv)
            keys.append(k)
            values.append(v)
            out = attend(q.contiguous(), torch.cat(keys).unsqueeze(0).contiguous(), torch.cat(values).unsqueeze(0).contiguous())
            return attn.out_proj(out.reshape(s, heads * dim))
        return run

    def prefill(self):
        """Prompt and reference pictures, then the soundtrack, into the cache."""
        static = [(self.text_embed, self.text, STATIC_TIME, self.text_tags)]
        offset = self.frames * self.per_frame
        for a, b in self.refs:
            static.append((self.video_embed(self.cond_rows[offset:offset + b - a]), (a, b), CLEAN_LEVEL, TAG_VIDEO))
            offset += b - a
        self.forward(static, (), ('static', 0))
        self.forward([(self.audio_embed, self.audio, CLEAN_LEVEL, TAG_AUDIO)], [('static', 0)], ('audio', 0))

    def chunk(self, c, f0, f1, sigmas, euler, on_step=None):
        """Render latent frames f0:f1 (chunk c) -> [1, 24, f1 - f0, h, w]."""
        rows = (f0 * self.per_frame, f1 * self.per_frame)
        guide = (self.guide_start + rows[0], self.guide_start + rows[1])
        target = (self.video_start + rows[0], self.video_start + rows[1])
        self.forward([(self.video_embed(self.cond_rows[rows[0]:rows[1]]), guide, CLEAN_LEVEL, TAG_VIDEO)], [('static', 0)], ('guide', c))
        window = range(max(0, c - self.window + 1), c + 1)
        history = [('static', 0), ('audio', 0), *(('guide', j) for j in window), *(('clean', j) for j in window if j < c)]
        shape = (1, 24, f1 - f0, self.height, self.width)
        draw = lambda: torch.randn(shape, generator=self.generator, device=self.device, dtype=torch.float32)  # noqa: E731
        current = draw()
        steps = len(sigmas) - 1
        for i in range(steps):
            mm.throw_exception_if_processing_interrupted()
            sigma, sigma_next = float(sigmas[i]), float(sigmas[i + 1])
            embed = self.video_embed(patchify_video(current, self.dm.patch_size))
            velocity = self.forward([(embed, target, 1.0 - sigma, TAG_VIDEO)], history, None, sigma=sigma)
            velocity = unpatchify_video(velocity, f1 - f0, self.height // 2, self.width // 2, 24, self.dm.patch_size).float()
            estimate = current + sigma * velocity
            if i == steps - 1:
                current = estimate
            elif euler:
                current = current + (sigma - sigma_next) * velocity
            else:  # lcm: clean estimate, fresh noise (SolarRenderer's four-step path)
                current = (1.0 - sigma_next) * estimate + sigma_next * draw()
            if on_step:
                on_step(i, estimate)
        written = CLEAN_LEVEL * current + (1.0 - CLEAN_LEVEL) * draw()
        self.forward([(self.video_embed(patchify_video(written, self.dm.patch_size)), target, CLEAN_LEVEL, TAG_VIDEO)], history, ('clean', c))
        return current


class HengeCausalSampler:
    """Render a whole guided clip chunk by chunk (no shot seams); memory follows the window, not the clip length."""
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'model': ('MODEL',), 'positive': ('CONDITIONING',), 'latent': ('LATENT',),
                             'seed': ('INT', {'default': 0, 'min': 0, 'max': 0xFFFFFFFFFFFFFFFF}),
                             'steps': ('INT', {'default': 8, 'min': 1, 'max': 50}),
                             'chunk': ('INT', {'default': 5, 'min': 1, 'max': 32, 'tooltip': 'Latent frames per chunk (1 latent frame = 4 video frames).'}),
                             'window': ('INT', {'default': 6, 'min': 1, 'max': 16, 'tooltip': 'Chunks each chunk sees, its own included.'}),
                             'sampler': (['euler', 'lcm'],),
                             'cache': (['auto', 'gpu', 'system memory'],)}}
    RETURN_TYPES = ('LATENT',)
    FUNCTION = 'sample'
    CATEGORY = 'Henge'

    def sample(self, model, positive, latent, seed, steps, chunk, window, sampler, cache):
        streams = latent['samples']
        shapes = [t.shape for t in streams.tensors] if getattr(streams, 'is_nested', False) else None
        if shapes is None or len(shapes) < 2:
            raise ValueError('Causal sampling takes a MiniMax H3 AV latent')
        mm.load_models_gpu([model])
        device, dtype = model.load_device, model.model.get_dtype_inference()
        dm = model.model.diffusion_model
        context, extra = positive[0][0], positive[0][1]
        _, _, frames, height, width = shapes[0]
        rows = (height // 2) * (width // 2)
        attn = dm.blocks[0].attn
        need = rows * chunk * (2 * window) * 2 * attn.heads * attn.head_dim * 2 * len(dm.blocks)
        on_gpu = cache == 'gpu' or (cache == 'auto' and mm.get_free_memory(device) > need * 1.3)
        sigmas = shifted_sigmas(steps)
        chunks = [(f, min(f + chunk, frames)) for f in range(0, frames, chunk)]
        logging.info(f"[Henge causal] {len(chunks)} chunks x {steps} steps, window {window}, cache on {'GPU' if on_gpu else 'system memory'} (up to {need / 2**30:.1f} GB)")
        with torch.inference_mode():
            run = CausalRun(dm, device, dtype, context, extra, shapes, seed, device if on_gpu else torch.device('cpu'), window)
            total = len(chunks) * steps
            callback = latent_preview.prepare_callback(model, total)
            run.prefill()
            clip = torch.zeros(shapes[0], dtype=torch.float32)
            for c, (f0, f1) in enumerate(chunks):
                def on_step(i, estimate, c=c):
                    try:
                        callback(c * steps + i, estimate, None, total)
                    except Exception as e:  # a preview never stops the render
                        logging.debug(f'[Henge causal] no preview: {e}')
                clip[:, :, f0:f1] = run.chunk(c, f0, f1, sigmas, sampler == 'euler', on_step).cpu()
            del run
        out = latent.copy()
        out['samples'] = comfy.nested_tensor.NestedTensor((clip.to(mm.intermediate_device()), silence(shapes[1][-1]).to(clip.dtype)))
        return (out,)
