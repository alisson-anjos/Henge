"""Sharpness 2K/4K upscalers for MiniMax H3.

- HengeH3LatentUpscale: the MiniMax H3 3D latent upscaler (LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler, MIT),
  as packaged in bbaudio-2025/Comfyui-MMH3-UltimateUpscale (MIT, nodes/h3_latent_upscaler.py): copied below.
- HengeH3TiledDiffusion: per-step spatial tiled diffusion for H3 with global window positions, copied from
  bbaudio-2025/Comfyui-MMH3-UltimateUpscale (MIT, nodes/tiled_diffusion.py, itself a port of
  shiimizu/ComfyUI-TiledDiffusion). Lets the refine pass run at 4K: each step samples overlapping tiles.
- HengeRTXUpscale: NVIDIA RTX Video Super Resolution through the nvidia-vfx SDK (pip install nvidia-vfx).

Copied code keeps its upstream structure; changes are the log prefixes, dropping the io.ComfyNode wrappers, and the
classic node classes at the end. MIT notices: THIRD_PARTY_NOTICES.md.
"""

import os
import re

import torch
import torch.nn as nn
import torch.nn.functional as F

import folder_paths

# Spatial compression factor of the MiniMax H3 3D VAE (16x).
VAE_DOWNSAMPLE = 16

# ---------------------------------------------------------------------------
# H3 3D latent upscaler (copied from Comfyui_Minimax_h3_latent_Upscaler)
# ---------------------------------------------------------------------------

_LATENT_UPSCALE_FOLDER = "latent_upscale_models"
if _LATENT_UPSCALE_FOLDER not in folder_paths.folder_names_and_paths:
    folder_paths.add_model_folder_path(
        _LATENT_UPSCALE_FOLDER,
        os.path.join(folder_paths.models_dir, _LATENT_UPSCALE_FOLDER)
    )

LATENTS_MEAN = [
    0.858090341091156, -0.9606591463088989, 1.0661640167236328, -0.5090325474739075,
    -0.2727581858634949, -1.3675414323806763, -0.2553254961967468, -0.26907554268836975,
    -0.5376840829849243, -0.0464097298681736, 0.6657370328903198, 0.19690127670764923,
    -0.5460608005523682, -0.4035342037677765, -0.23683024942874908, 0.25928452610969543,
    -0.30133944749832153, 0.211341992020607, -1.1206848621368408, 0.3581933379173279,
    -0.04225143790245056, 0.2604829967021942, 0.22864092886447906, 0.7056031823158264
]
LATENTS_STD = [
    1.2223774194717407, 1.2767263650894165, 1.6831774711608887, 1.7549455165863037,
    1.5636216402053833, 2.194143533706665, 0.9653137922286987, 1.0569885969161987,
    0.841948926448822, 0.7729952931404114, 1.8955937623977661, 0.946841835975647,
    0.7996809482574463, 0.44988900423049927, 0.7197399735450745, 0.6936293244361877,
    2.961095094680786, 2.7694199085235596, 3.0496184825897217, 2.1088054180265264,
    3.276226282119751, 3.1627357006073, 2.2816812992095947, 2.6127843856811523
]


def _make_norm_tensors(device, dtype):
    mean = torch.tensor(LATENTS_MEAN, dtype=dtype, device=device).view(1, -1, 1, 1, 1)
    std = torch.tensor(LATENTS_STD, dtype=dtype, device=device).view(1, -1, 1, 1, 1)
    return mean, std


def _normalization(channels):
    return nn.GroupNorm(32, channels)


def _zero_module(module):
    for p in module.parameters():
        p.detach().zero_()
    return module


class _AttnBlock3D(nn.Module):
    def __init__(self, in_channels):
        super().__init__()
        self.norm = _normalization(in_channels)
        self.q = nn.Conv3d(in_channels, in_channels, 1)
        self.k = nn.Conv3d(in_channels, in_channels, 1)
        self.v = nn.Conv3d(in_channels, in_channels, 1)
        self.proj_out = nn.Conv3d(in_channels, in_channels, 1)

    def forward(self, x):
        h = self.norm(x)
        b, c, t, hh, w = h.shape
        q = self.q(h).flatten(2).transpose(1, 2)
        k = self.k(h).flatten(2).transpose(1, 2)
        v = self.v(h).flatten(2).transpose(1, 2)
        h = F.scaled_dot_product_attention(q, k, v)
        h = h.transpose(1, 2).view(b, c, t, hh, w)
        return x + self.proj_out(h)


class _ResBlockEmb3D(nn.Module):
    def __init__(self, channels, emb_channels, dropout=0, out_channels=None):
        super().__init__()
        self.out_channels = out_channels or channels
        self.in_layers = nn.Sequential(
            _normalization(channels), nn.SiLU(),
            nn.Conv3d(channels, self.out_channels, 3, padding=1),
        )
        self.emb_layers = nn.Sequential(
            nn.SiLU(), nn.Linear(emb_channels, 2 * self.out_channels),
        )
        self.out_norm = _normalization(self.out_channels)
        self.out_layers = nn.Sequential(
            nn.SiLU(), nn.Dropout(p=dropout),
            _zero_module(nn.Conv3d(self.out_channels, self.out_channels, 3, padding=1)),
        )
        self.skip = (
            nn.Conv3d(channels, self.out_channels, 1)
            if self.out_channels != channels else nn.Identity()
        )

    def forward(self, x, emb):
        h = self.in_layers(x)
        emb_out = self.emb_layers(emb).type(h.dtype)
        while len(emb_out.shape) < len(h.shape):
            emb_out = emb_out[..., None]
        scale, shift = torch.chunk(emb_out, 2, dim=1)
        h = self.out_norm(h) * (1 + scale) + shift
        h = self.out_layers(h)
        return self.skip(x) + h


class _TemporalConv(nn.Module):
    def __init__(self, channels, kernel_size=5):
        super().__init__()
        padding = kernel_size // 2
        self.norm = _normalization(channels)
        self.dwconv = nn.Conv3d(channels, channels,
                                kernel_size=(kernel_size, 1, 1),
                                padding=(padding, 0, 0),
                                groups=channels)
        self.pwconv = nn.Conv3d(channels, channels, kernel_size=1)
        nn.init.zeros_(self.pwconv.weight)
        nn.init.zeros_(self.pwconv.bias)

    def forward(self, x):
        identity = x
        h = self.norm(x)
        h = F.silu(h)
        h = self.dwconv(h)
        h = self.pwconv(h)
        return identity + h


class _LatentResizer3D(nn.Module):
    def __init__(self, in_channels=24, in_blocks=12, out_blocks=12,
                 channels=512, dropout=0.1, attn=False,
                 temporal_every=2, temporal_kernel=5):
        super().__init__()
        self.conv_in = nn.Conv3d(in_channels, channels, 3, padding=1)
        embed_dim = 64
        self.embed = nn.Sequential(
            nn.Linear(1, embed_dim), nn.SiLU(), nn.Linear(embed_dim, embed_dim))

        self.in_blocks = nn.ModuleList()
        for b in range(in_blocks):
            if (b == 1 or b == in_blocks - 1) and attn:
                self.in_blocks.append(_AttnBlock3D(channels))
            self.in_blocks.append(_ResBlockEmb3D(channels, embed_dim, dropout))
            if temporal_every > 0 and b % temporal_every == 0:
                self.in_blocks.append(_TemporalConv(channels, temporal_kernel))

        self.out_blocks = nn.ModuleList()
        for b in range(out_blocks):
            if (b == 1 or b == out_blocks - 1) and attn:
                self.out_blocks.append(_AttnBlock3D(channels))
            self.out_blocks.append(_ResBlockEmb3D(channels, embed_dim, dropout))
            if temporal_every > 0 and b % temporal_every == 0:
                self.out_blocks.append(_TemporalConv(channels, temporal_kernel))

        self.norm_out = _normalization(channels)
        self.conv_out = nn.Conv3d(channels, in_channels, 3, padding=1)

    def forward(self, x, scale=None, target_size=None):
        if target_size is not None:
            size = target_size
        elif scale is not None:
            size = tuple(int(round(s * scale)) for s in x.shape[-3:])
        else:
            return x

        if size == x.shape[-3:]:
            return x

        scale_emb = torch.tensor(
            [scale - 1 if scale is not None else 0.0],
            dtype=x.dtype, device=x.device).unsqueeze(0)
        emb = self.embed(scale_emb)

        x = self.conv_in(x)
        for b in self.in_blocks:
            if isinstance(b, _ResBlockEmb3D):
                emb_t = emb.expand(x.shape[0], -1)
                x = b(x, emb_t)
            else:
                x = b(x)

        x = F.interpolate(x, size=size, mode="trilinear", align_corners=False)

        for b in self.out_blocks:
            if isinstance(b, _ResBlockEmb3D):
                emb_t = emb.expand(x.shape[0], -1)
                x = b(x, emb_t)
            else:
                x = b(x)

        x = self.norm_out(x)
        x = F.silu(x)
        x = self.conv_out(x)
        return x


_MODEL_CACHE = {}

# Only safetensors checkpoints are accepted, and they are rejected *before* the
# file is read: torch.load() on a pickle checkpoint can execute arbitrary code,
# and weights_only=True is not a sufficient defence on torch < 2.6
# (CVE-2025-32434). ".sft" is the other extension ComfyUI core accepts for
# safetensors (comfy.utils.load_torch_file), so it is allowed here as well.
_SUPPORTED_MODEL_EXTENSIONS = (".safetensors", ".sft")

# Formats that used to be accepted and are now refused on purpose. Only used to
# print an actionable hint instead of a silent "no models found".
_REJECTED_MODEL_EXTENSIONS = (".pth", ".pt", ".pt2", ".ckpt", ".bin", ".pkl")

_CONVERT_HINT = (
    "Convert it once with:\n"
    "    import torch, safetensors.torch\n"
    "    sd = torch.load('model.pth', map_location='cpu', weights_only=True)\n"
    "    sd = sd['model'] if isinstance(sd, dict) and 'model' in sd else sd\n"
    "    safetensors.torch.save_file(sd, 'model.safetensors')\n"
    "If weights_only=True fails, the checkpoint is not a plain state dict and "
    "should not be trusted."
)


def _model_ext(name):
    """Lower-cased extension, so the scanner and the loader agree on case."""
    return os.path.splitext(name)[1].lower()


def _model_dirs():
    return folder_paths.get_folder_paths(_LATENT_UPSCALE_FOLDER)


def _get_models_dir():
    """First registered models dir. Used for messages only - loading resolves a
    name across every registered dir (see load_upscale_model)."""
    return _model_dirs()[0]


def _scan_models():
    """List usable checkpoints across ALL registered latent_upscale_models dirs.

    Uses folder_paths.get_filename_list (same as the upstream node) rather than a
    glob on a single directory, so models registered via extra_model_paths.yaml
    and sub-folders show up too, and the extension filter is case-insensitive.
    """
    all_names = folder_paths.get_filename_list(_LATENT_UPSCALE_FOLDER)
    names = sorted(n for n in all_names
                   if _model_ext(n) in _SUPPORTED_MODEL_EXTENSIONS)
    rejected = sorted(n for n in all_names
                      if _model_ext(n) in _REJECTED_MODEL_EXTENSIONS)
    if rejected:
        print(f"[Henge upscale] Ignored {len(rejected)} pickle checkpoint(s) "
              f"in the latent_upscale_models folder (only .safetensors is supported): "
              f"{', '.join(rejected)}")
    if not names:
        return [f"(no .safetensors upscale models found in: {', '.join(_model_dirs())})"]
    return names


def _load_raw_sd(path):
    """Read a checkpoint into a raw state dict. Only safetensors is accepted;
    pickle formats are refused before the file is opened."""
    if _model_ext(path) not in _SUPPORTED_MODEL_EXTENSIONS:
        raise ValueError(
            f"Refusing to load '{os.path.basename(path)}': this node only accepts "
            f"{' / '.join(_SUPPORTED_MODEL_EXTENSIONS)} checkpoints. Pickle formats "
            f"(.pth / .pt / .ckpt) can execute arbitrary code when loaded, so they "
            f"are rejected before the file is read. {_CONVERT_HINT}"
        )
    from safetensors.torch import load_file
    sd = load_file(path, device='cpu')
    if isinstance(sd, dict) and isinstance(sd.get('model'), dict):
        # Pickle checkpoints sometimes wrap the weights in {"model": ...}. Guard
        # on the value type so a tensor literally named "model" can't break this.
        sd = sd['model']
    sd = {k: v.to(torch.float16) if v.dtype == torch.float8_e4m3fn else v
          for k, v in sd.items()}
    return sd


def _extract_upscaler_sd(sd):
    if any(k.startswith("upscaler.") for k in sd):
        return {k[len("upscaler."):]: v for k, v in sd.items() if k.startswith("upscaler.")}
    return sd


def _detect_arch(sd):
    cfg = {
        "in_channels": 24, "in_blocks": 12, "out_blocks": 12, "channels": 512,
        "dropout": 0.1, "attn": False, "temporal_every": 2, "temporal_kernel": 5,
    }
    conv_key = 'conv_in.weight'
    if conv_key in sd:
        cfg["in_channels"] = sd[conv_key].shape[1]
        cfg["channels"] = sd[conv_key].shape[0]

    in_ids, out_ids = set(), set()
    temporal_in_indices, temporal_out_indices = set(), set()
    for k in sd.keys():
        m = re.match(r'in_blocks\.(\d+)\.in_layers\.', k)
        if m:
            in_ids.add(int(m.group(1)))
        m = re.match(r'out_blocks\.(\d+)\.in_layers\.', k)
        if m:
            out_ids.add(int(m.group(1)))
        m = re.match(r'in_blocks\.(\d+)\.dwconv\.weight', k)
        if m:
            temporal_in_indices.add(int(m.group(1)))
        m = re.match(r'out_blocks\.(\d+)\.dwconv\.weight', k)
        if m:
            temporal_out_indices.add(int(m.group(1)))

    if in_ids:
        cfg["in_blocks"] = len(in_ids)
    if out_ids:
        cfg["out_blocks"] = len(out_ids)

    if temporal_in_indices or temporal_out_indices:
        cfg["temporal_every"] = 2
        for k in sd.keys():
            if 'dwconv.weight' in k and k.endswith('dwconv.weight'):
                cfg["temporal_kernel"] = sd[k].shape[2]
                break
    else:
        cfg["temporal_every"] = 0

    cfg["attn"] = False
    return cfg


def load_upscale_model(name, device, precision):
    cache_key = f"{name}::{device}::{precision}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key].to(device)

    # Resolve the name against every registered latent_upscale_models dir, not
    # just the first one, so extra_model_paths.yaml entries are usable.
    path = folder_paths.get_full_path(_LATENT_UPSCALE_FOLDER, name)
    if path is None or not os.path.isfile(path):
        raise FileNotFoundError(
            f"Model file not found: {name} (searched: {', '.join(_model_dirs())})")

    raw_sd = _load_raw_sd(path)
    up_sd = _extract_upscaler_sd(raw_sd)
    cfg = _detect_arch(up_sd)
    if cfg["in_channels"] != 24:
        raise ValueError(
            f"Checkpoint '{name}' is not an H3 latent upscaler "
            f"(expected 24 input channels, got {cfg['in_channels']})."
        )

    model = _LatentResizer3D(
        in_channels=cfg["in_channels"], in_blocks=cfg["in_blocks"], out_blocks=cfg["out_blocks"],
        channels=cfg["channels"], dropout=cfg["dropout"], attn=cfg["attn"],
        temporal_every=cfg["temporal_every"], temporal_kernel=cfg["temporal_kernel"],
    )
    model.load_state_dict(up_sd, strict=True)
    dtype = {"fp32": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}.get(precision, torch.float32)
    model = model.to(device).eval().requires_grad_(False)
    if dtype != torch.float32:
        model = model.to(dtype)

    _MODEL_CACHE[cache_key] = model
    print(f"[Henge upscale] Loaded upscale model: {name}")
    return model


def unload_upscale_model(name, device, precision):
    """Free VRAM after upscaling: move the cached upscale model back to CPU. It stays
    in _MODEL_CACHE so the next chunk only re-copies weights to GPU, not re-reads disk."""
    cache_key = f"{name}::{device}::{precision}"
    model = _MODEL_CACHE.get(cache_key)
    if model is not None and str(next(model.parameters()).device) != "cpu":
        model.to("cpu")
        print(f"[Henge upscale] Offloaded upscale model: {name}")
    if str(device) == "cuda":
        torch.cuda.empty_cache()


def _compute_upscale_target(width, height, h_in, w_in):
    """Pixel target W/H + effective scale from EXPLICIT target dimensions.

    The upscale target is always an exact pixel size (it must match the
    conditioning's generation size)."""
    ds = VAE_DOWNSAMPLE
    w_px = float(width)
    h_px = float(height)
    eff = (w_px / (w_in * ds) + h_px / (h_in * ds)) / 2.0

    w_px_f = round(w_px / ds) * ds
    h_px_f = round(h_px / ds) * ds
    w_out = max(1, int(w_px_f // ds))
    h_out = max(1, int(h_px_f // ds))
    return h_out, w_out, eff


def upscale_video(video, param):
    """Upscale one chunk's video latent with the H3 3D upscaler. Audio untouched.

    Returns (upscaled_video, new_h, new_w). The target is computed in pixel
    space (explicit width/height, snapped to the VAE 16x grid), then the
    H3 network resizes to it. scale 1.0 (or an equivalent target) is a no-op."""
    model_name = param["model_name"]
    width = int(param["width"])
    height = int(param["height"])
    device = param["device"]
    precision = param["precision"]

    orig_dtype = video.dtype
    dev = torch.device(device if (device == "cpu" or torch.cuda.is_available()) else "cpu")
    compute_dtype = {"fp32": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}[precision]

    _, c, t, h_in, w_in = video.shape
    h_out, w_out, eff = _compute_upscale_target(width, height, h_in, w_in)

    if eff < 1.0 and (w_out < w_in or h_out < h_in):
        raise ValueError("This model only supports upscaling (effective scale >= 1.0).")
    if w_out == w_in and h_out == h_in:
        return video, h_in, w_in

    if str(model_name).startswith('('):
        raise ValueError(
            "No usable H3 upscale model selected. Put a .safetensors checkpoint "
            "(e.g. minimax_h3_latent_upscaler_3d_fp16.safetensors) into the "
            "latent_upscale_models folder and restart ComfyUI. Pickle checkpoints "
            "(.pth / .pt / .ckpt) are no longer accepted for security reasons."
        )

    s = video.to(device=dev, dtype=compute_dtype, copy=True)
    model = load_upscale_model(model_name, dev, precision)
    norm_mean, norm_std = _make_norm_tensors(dev, compute_dtype)

    with torch.inference_mode():
        s = s.sub(norm_mean).div(norm_std)
        out = model(s, scale=eff, target_size=(t, h_out, w_out))
        del s
        out = out.mul(norm_std).add(norm_mean)

    out = out.to(device="cpu", dtype=orig_dtype)
    if param.get("offload_model", True):
        unload_upscale_model(model_name, dev, precision)
    return out, h_out, w_out


import comfy.ldm.common_dit
from comfy.ldm.minimax.model import PackedLayout

# ---------------------------------------------------------------------------
# Per-step tiled diffusion for H3 (copied from bbaudio-2025/Comfyui-MMH3-UltimateUpscale, MIT)
# ---------------------------------------------------------------------------

def _ceil2(x):
    """Round up to the next even number (the H3 2x2 spatial patch grid)."""
    return (x + 1) // 2 * 2


def _tile_starts(total, tile, overlap):
    """Start offsets covering [0, total) with `tile`-unit tiles overlapping by
    `overlap`. Tile sizes and overlaps are multiples of 2 latent units (the H3
    2x2 spatial patch grid, i.e. 32 px) so every boundary stays patch-aligned."""
    if tile >= total:
        return [0]
    stride = tile - overlap
    starts = list(range(0, total - tile + 1, stride))
    if starts[-1] + tile < total:
        starts.append(total - tile)
    return starts


class _WindowLayout:
    """PackedLayout-compatible layout whose video / keyframe rows keep the
    GLOBAL frame coordinates of the tile window (instead of restarting the
    RoPE grid at the tile origin), and whose audio anchors come from the full
    frame so every tile positions the audio stream identically."""

    def __init__(self, full, keyframes, T, Hp, Wp, h0, w0, h1, w1, audio_t, text_len):
        # padded window bounds on the full frame's patch grid
        hp1, wp1 = h0 + _ceil2(h1 - h0), w0 + _ceil2(w1 - w0)
        rows = torch.arange(h0 // 2, hp1 // 2, dtype=torch.long)[:, None] * (Wp // 2) \
            + torch.arange(w0 // 2, wp1 // 2, dtype=torch.long)[None, :]
        idx = rows.reshape(-1)
        frame_rows = (Hp // 2) * (Wp // 2)
        # temporal token count per keyframe that packs a video latent, in
        # PackedLayout's segment order (one 'cond' segment per such keyframe)
        kf_vts = [kf["latent"].shape[2] for kf in (keyframes or ()) if kf.get("latent") is not None]

        pos, img_pos, img_upd, aud_pos, aud_upd, segments = [], [], [], [], [], []
        kf_i = 0
        row = 0
        for a, b, kind in full.segments:
            p = full.position_ids[a:b]
            if kind == "video":
                p = p.reshape(T, frame_rows, 3)[:, idx, :].reshape(-1, 3)
            elif kind == "cond":
                vt = kf_vts[kf_i]
                kf_i += 1
                p = p.reshape(vt, frame_rows, 3)[:, idx, :].reshape(-1, 3)
            n = p.shape[0]
            pos.append(p)
            segments.append((row, row + n, kind))
            if kind in ("cond", "ref_img", "video"):
                img_pos.append(torch.arange(row, row + n))
                img_upd.append(torch.full((n,), kind == "video", dtype=torch.bool))
            elif kind in ("cond_audio", "ref_audio", "audio"):
                aud_pos.append(torch.arange(row, row + n))
                aud_upd.append(torch.full((n,), kind == "audio", dtype=torch.bool))
            row += n

        self.position_ids = torch.cat(pos)
        self.img_pos = torch.cat(img_pos)
        self.img_update = torch.cat(img_upd)
        self.audio_pos = torch.cat(aud_pos)
        self.audio_update = torch.cat(aud_upd)
        self.segments = segments
        self.seq_len = row
        self.signature = (text_len, T, hp1 - h0, wp1 - w0, audio_t)


class _H3TiledDiffusionImpl:
    """model_function_wrapper installed via set_model_unet_function_wrapper.

    Receives the flat packed AV latent ([B, 1, video_elems + audio_elems], see
    comfy.utils.pack_latents) plus the cond dict carrying latent_shapes and the
    minimax payload (keyframes / refs / prebuilt packed layout)."""

    def __init__(self, method, tile_h, tile_w, overlap):
        self.method = method
        self.tile_h = tile_h
        self.tile_w = tile_w
        self.overlap = overlap
        # (payload, video shape) -> (tiles, weights, per-tile payloads); rebuilt
        # when the conditioning payload or the chunk shape changes
        self._cache = None

    def _build(self, payload, video, audio, c):
        _, _, T, H, W = video.shape
        rows = _tile_starts(H, self.tile_h, self.overlap)
        cols = _tile_starts(W, self.tile_w, self.overlap)
        text = c.get("c_crossattn")
        text_len = text.shape[1] if text is not None else 0
        audio_t = audio.shape[-1]
        keyframes = payload.get("keyframes")
        refs = payload.get("refs")

        # full-frame layout as the source of global window positions; the
        # payload usually carries the one model_base prebuilt per chunk
        Hp, Wp = _ceil2(H), _ceil2(W)
        full = payload.get("layout")
        if full is None or full.signature != (text_len, T, Hp, Wp, audio_t):
            full = PackedLayout(text_len, T, Hp, Wp, audio_t,
                                keyframes=keyframes, refs=refs)

        tiles, weights, payloads = [], [], []
        for h0 in rows:
            for w0 in cols:
                h1, w1 = min(h0 + self.tile_h, H), min(w0 + self.tile_w, W)
                th, tw = h1 - h0, w1 - w0
                tiles.append((h0, w0, h1, w1))
                if self.method == "gaussian":
                    sigma = max(min(th, tw) / 8.0, 1e-6)
                    yy = torch.arange(th, dtype=torch.float32) - (th - 1) / 2.0
                    xx = torch.arange(tw, dtype=torch.float32) - (tw - 1) / 2.0
                    w = torch.exp(-(yy[:, None] ** 2 + xx[None, :] ** 2) / (2.0 * sigma * sigma))
                else:
                    w = torch.ones(th, tw, dtype=torch.float32)
                weights.append(w.to(device=video.device, dtype=video.dtype))

                p = dict(payload)
                if keyframes:
                    # keyframe latents share the target spatial grid, so crop
                    # (or resize-then-crop) them to the tile exactly like the
                    # spatial split path's crop_keyframes_to_tile does
                    kfs, cond_v = [], []
                    for kf in keyframes:
                        nkf = dict(kf)
                        lt = nkf.get("latent")
                        if lt is not None:
                            if lt.shape[3] != H or lt.shape[4] != W:
                                Bk, Ck, Tk, Hk, Wk = lt.shape
                                lt = torch.nn.functional.interpolate(
                                    lt.reshape(Bk * Tk, Ck, Hk, Wk).float(),
                                    size=(H, W), mode="bilinear", align_corners=False,
                                ).reshape(Bk, Ck, Tk, H, W).to(lt.dtype)
                            crop = lt[:, :, :, h0:h1, w0:w1].contiguous()
                            nkf["latent"] = comfy.ldm.common_dit.pad_to_patch_size(crop, (1, 2, 2))
                            cond_v.append(nkf["latent"])
                        kfs.append(nkf)
                    p["keyframes"] = kfs
                    # refs keep their own resolution and grid - only keyframes
                    # are cropped; the flattened cond list must mirror that
                    p["cond_video_latents"] = cond_v + [
                        r["latent"] for r in (refs or ()) if "latent" in r]
                # window layout with GLOBAL positions so the tile predicts
                # what the full-frame model would inside this window
                p["layout"] = _WindowLayout(full, keyframes, T, Hp, Wp,
                                            h0, w0, h1, w1, audio_t, text_len)
                payloads.append(p)
        print(f"[Henge tiled diffusion] {len(tiles)} tiles ({len(rows)}x{len(cols)}) "
              f"on {H}x{W} latent, overlap {self.overlap * 16}px, method={self.method}, "
              f"global window positions")
        return tiles, weights, payloads

    def __call__(self, model_function, args):
        x = args["input"]
        t = args["timestep"]
        c = args["c"]

        payload = c.get("minimax_payload")
        if payload is None:
            raise ValueError("Henge tiled diffusion only works with the MiniMax H3 model.")
        for k in ("control", "denoise_mask", "audio_denoise_mask"):
            if c.get(k) is not None:
                raise ValueError(
                    f"Henge tiled diffusion (experimental) does not support '{k}'. "
                    "Disconnect the fun controlnet / inpaint chain, or use the "
                    "spatial split path of MMH3 Ultimate Upscale instead.")

        streams = comfy.utils.unpack_latents(x, c["latent_shapes"])
        video, audio = streams[0], streams[1] if len(streams) > 1 else None
        _, _, T, H, W = video.shape

        entry = self._cache
        if entry is None or entry[0] is not payload or entry[1] != (T, H, W):
            entry = (payload, (T, H, W)) + self._build(payload, video, audio, c)
            self._cache = entry
        _, _, tiles, weights, payloads = entry

        buf = torch.zeros_like(video)
        wsum = torch.zeros((1, 1, 1, H, W), device=video.device, dtype=video.dtype)
        audio_acc = None
        for (h0, w0, h1, w1), w, p in zip(tiles, weights, payloads):
            v_t = video[:, :, :, h0:h1, w0:w1]
            c_t = dict(c)
            c_t["minimax_payload"] = p
            if audio is not None:
                x_t, shapes_t = comfy.utils.pack_latents([v_t, audio])
                c_t["latent_shapes"] = shapes_t
                v_out, a_out = comfy.utils.unpack_latents(
                    model_function(x_t, t, **c_t), shapes_t)
            else:
                v_out = model_function(v_t, t, **c_t)
                a_out = None
            buf[:, :, :, h0:h1, w0:w1] += v_out * w[None, None, None]
            wsum[:, :, :, h0:h1, w0:w1] += w[None, None, None]
            if a_out is not None:
                audio_acc = a_out if audio_acc is None else audio_acc + a_out

        out_v = buf / wsum.clamp(min=1e-8)
        if audio is None:
            return out_v
        # every tile saw the full audio stream; average its predictions
        out, _ = comfy.utils.pack_latents([out_v, audio_acc / len(tiles)])
        return out


# ---------------------------------------------------------------------------
# Henge nodes
# ---------------------------------------------------------------------------

class HengeH3LatentUpscale:
    """Video latent [1,24,T,H,W] to the exact pixel size width x height (16 px grid) with the H3 3D upscaler."""
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'latent':('LATENT',),'model_name':(_scan_models(),),'width':('INT',{'default':1088,'min':64,'max':8192,'step':16}),
                                             'height':('INT',{'default':1920,'min':64,'max':8192,'step':16}),'precision':(['fp16','bf16','fp32'],{'default':'fp16'})}}
    RETURN_TYPES=('LATENT',);FUNCTION='upscale';CATEGORY='henge'
    def upscale(self,latent,model_name,width,height,precision='fp16'):
        import comfy.model_management as mm
        video,_,_=upscale_video(latent['samples'],{'model_name':model_name,'width':width,'height':height,'device':str(mm.get_torch_device()),'precision':precision})
        return ({**latent,'samples':video},)


class HengeH3TiledDiffusion:
    """Patch an H3 model so every sampling step runs on overlapping spatial tiles (needed to refine at 4K)."""
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'model':('MODEL',),'tile_width':('INT',{'default':1024,'min':256,'max':8192,'step':32}),
                                             'tile_height':('INT',{'default':1024,'min':256,'max':8192,'step':32}),'tile_overlap':('INT',{'default':256,'min':0,'max':4096,'step':32}),
                                             'method':(['gaussian','uniform'],{'default':'gaussian'})}}
    RETURN_TYPES=('MODEL',);FUNCTION='patch';CATEGORY='henge'
    def patch(self,model,tile_width,tile_height,tile_overlap,method='gaussian'):
        tw,th,ov=int(round(tile_width/32.))*2,int(round(tile_height/32.))*2,int(round(tile_overlap/32.))*2
        if ov>=min(tw,th):raise ValueError('Tile overlap must be smaller than the tile size')
        patched=model.clone();patched.set_model_unet_function_wrapper(_H3TiledDiffusionImpl(method,th,tw,ov))
        return (patched,)


class HengeRTXUpscale:
    """Frames to width x height with NVIDIA RTX Video Super Resolution (no diffusion, no invented detail)."""
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'width':('INT',{'default':1920,'min':64,'max':8192,'step':8}),
                                             'height':('INT',{'default':1080,'min':64,'max':8192,'step':8}),'quality':(['LOW','MEDIUM','HIGH','ULTRA'],{'default':'ULTRA'})}}
    RETURN_TYPES=('IMAGE',);FUNCTION='upscale';CATEGORY='henge'
    def upscale(self,images,width,height,quality='ULTRA'):
        try:import nvvfx
        except ImportError as e:raise RuntimeError('NVIDIA upscale needs the nvidia-vfx package (pip install nvidia-vfx) and an RTX GPU') from e
        import comfy.model_management as mm
        device=mm.get_torch_device();mm.unload_all_models();mm.soft_empty_cache()
        vsr=nvvfx.VideoSuperRes(quality=getattr(nvvfx.VideoSuperRes.QualityLevel,quality),device=device.index or 0)
        vsr.output_width,vsr.output_height=int(width),int(height);vsr.load()
        out=torch.empty((images.shape[0],int(height),int(width),3),dtype=images.dtype)
        try:
            for i,frame in enumerate(images):
                # SDK contract: (3,H,W) float32 RGB in [0,1] on CUDA; the result must be copied before the next call.
                x=frame[...,:3].to(device,torch.float32).permute(2,0,1).contiguous()
                y=torch.from_dlpack(vsr.run(x).image)
                out[i]=y.permute(1,2,0).clamp(0,1).to('cpu',images.dtype)
        finally:vsr.close()
        return (out,)


NODE_CLASS_MAPPINGS={c.__name__:c for c in [HengeH3LatentUpscale,HengeH3TiledDiffusion]}
# Listed only where the SDK is installed, so the bridge can tell whether the NVIDIA upscaler is usable.
import importlib.util
if importlib.util.find_spec('nvvfx'):NODE_CLASS_MAPPINGS['HengeRTXUpscale']=HengeRTXUpscale
