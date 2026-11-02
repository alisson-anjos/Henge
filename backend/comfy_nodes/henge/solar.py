"""SolarRenderer's own conditioning and sampling, for Motion Transfer SolarRenderer FFP.

Ported from SolarRenderer (https://github.com/Enderfga/SolarRenderer, comfyui/nodes.py, Apache-2.0; see
THIRD_PARTY_NOTICES.md), so the worker needs no extra node pack:

* HengeSolarConditioning - the clip's inputs as SolarRenderer's training encoded them: the structure video (the guide)
  laid over every target frame and the first frame over frame 0, both as frame-aligned keyframes, and the prompt read
  by H3's Qwen3-VL with the two shown to it as <Video 1> and <Video 2> at 2 fps (the first frame held 13 frames).
* HengeSolarModel - the soundtrack held at H3's encoded silence through sampling, as the renderer was trained (it never
  generates sound). assets/h3_silence_153_158_170.safetensors comes from the same repository.
* solar_sigmas() - the four-step grid (shift 12) the four-step LoRA was trained on, for ManualSigmas; sample it with
  the "lcm" sampler and a BasicGuider.
"""
import os

import torch

import comfy.patcher_extension
import comfy.utils

FPS = 24
LONG, SHOWN_LONG = 362, 158        # past LONG frames, the text encoder sees the first SHOWN_LONG
STILL_FRAMES = 13                  # H3 takes no reference video shorter than this; the first frame is held that long
SHIFT_VIDEO, SHIFT_AUDIO = 12.0, 3.0
SILENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'h3_silence_153_158_170.safetensors')


def solar_sigmas(steps=4, shift=SHIFT_VIDEO):
    base = torch.linspace(1.0, 0.0, steps + 1, dtype=torch.float32)
    return (shift * base / (1.0 + (shift - 1.0) * base)).tolist()


def _fit(frames, width, height):
    """[T, H, W, C] -> [T, height, width, 3], cut to the canvas's aspect at the centre and LANCZOS-resized."""
    samples = frames[..., :3].movedim(-1, 1)
    if tuple(samples.shape[-2:]) != (height, width):
        samples = comfy.utils.common_upscale(samples, width, height, 'lanczos', 'center')
    return samples.movedim(1, -1).clamp(0.0, 1.0)


def _shown(frames):
    """A reference as H3's Qwen3-VL reads it: every 12th of the 24 fps frames, timestamped at 2 fps."""
    index = list(range(0, frames.shape[0], FPS // 2))
    return {'type': 'video', 'data': frames[index], 'timestamps': [i / 2.0 for i in range(len(index))]}


class HengeSolarConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'clip': ('CLIP',), 'vae': ('VAE',), 'structure': ('IMAGE',), 'prompt': ('STRING', {'multiline': True}),
                             'width': ('INT', {'default': 1344, 'min': 32, 'max': 4096, 'step': 32}),
                             'height': ('INT', {'default': 768, 'min': 32, 'max': 4096, 'step': 32}),
                             'length': ('INT', {'default': 158, 'min': 22, 'max': 3609})},
                'optional': {'first_frame': ('IMAGE',)}}
    RETURN_TYPES = ('CONDITIONING', 'LATENT')
    RETURN_NAMES = ('positive', 'latent')
    FUNCTION = 'encode'
    CATEGORY = 'Henge'

    def encode(self, clip, vae, structure, prompt, width, height, length, first_frame=None):
        from comfy_extras.nodes_minimax_h3 import _empty_av_latent
        frames = min(int(length), int(structure.shape[0]))
        if frames < 22:
            raise ValueError(f'SolarRenderer needs at least 22 frames of structure video, got {frames}')
        while frames % 17 != 5:
            frames -= 1
        video = _fit(structure[:frames], width, height)
        items = [_shown(video if frames <= LONG else video[:SHOWN_LONG])]
        still = None
        if first_frame is not None:
            still = _fit(first_frame[:1], width, height)
            items.append(_shown(still.repeat(STILL_FRAMES, 1, 1, 1)))
        positive = clip.encode_from_tokens_scheduled(clip.tokenize(prompt, minimax_ref_items=items))
        keyframes = [{'resolved_frame_index': 0, 'latent': vae.encode(video)}]
        if still is not None:
            keyframes.append({'resolved_frame_index': 0, 'latent': vae.encode(still)})
        positive = [[c[0], {**c[1], 'minimax_keyframes': keyframes}] for c in positive]
        latent, _ = _empty_av_latent(width, height, frames)
        print(f'[Henge H3] SolarRenderer conditioning: {frames} frames, first frame {"yes" if still is not None else "no"}', flush=True)
        return (positive, latent)


class _SilentSoundtrack:
    """Holds the audio stream at H3's encoded silence, noised to the step's audio time with one fixed draw."""

    def __init__(self, silence, seed):
        self.silence, self.seed, self.noise = silence, seed, None

    def __call__(self, executor, x, timestep, context, transformer_options={}, **kwargs):
        from comfy.ldm.minimax.model import time_shift_sigma
        video, audio = x[0], x[1]
        t = audio.shape[-1]
        if self.silence.shape[-1] < t:
            raise ValueError(f'the held silence covers 170 frames ({self.silence.shape[-1]} audio latents); this clip needs {t}')
        clean = self.silence[..., :t].to(audio.device, torch.float32)
        if self.noise is None or self.noise.shape != clean.shape:
            generator = torch.Generator('cpu').manual_seed(self.seed)
            self.noise = torch.randn(clean.shape, generator=generator, dtype=torch.float32)
        sigma_v = (timestep.flatten()[0] / 1000.0).float().clamp(min=1e-6)
        shift_v = float(transformer_options.get('minimax_h3_sigma_shift_video', SHIFT_VIDEO))
        shift_a = float(transformer_options.get('minimax_h3_sigma_shift_audio', SHIFT_AUDIO))
        sigma_a = float(time_shift_sigma(sigma_v, shift_v, shift_a))
        held = ((1.0 - sigma_a) * clean + sigma_a * self.noise.to(clean.device)).to(audio.dtype)
        return executor([video, held], timestep, context, transformer_options, **kwargs)


class HengeSolarModel:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'model': ('MODEL',), 'seed': ('INT', {'default': 0, 'min': 0, 'max': 0xFFFFFFFFFFFFFFFF})}}
    RETURN_TYPES = ('MODEL',)
    FUNCTION = 'patch'
    CATEGORY = 'Henge'

    def patch(self, model, seed):
        silence = comfy.utils.load_torch_file(SILENCE)['silence_170f'].float()   # [channels 2, 32, T]
        silence = silence.permute(1, 0, 2).unsqueeze(0)                           # ComfyUI's audio latent: [1, 32, channels, T]
        model = model.clone()
        model.add_wrapper(comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL, _SilentSoundtrack(silence, seed))
        return (model,)
