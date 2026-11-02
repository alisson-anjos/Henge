# Models and local setup

Henge uses an existing ComfyUI installation plus its local job bridge. Model
weights are not included in this GitHub repository. Place files under the
ComfyUI directory configured by `COMFY_ROOT`, or expose them with ComfyUI's
`extra_model_paths.yaml`. Restart ComfyUI after adding models.

## What the user selects

| Task | LoRA | Method |
| --- | --- | --- |
| Character Swap | Character Swap v1.1, selected automatically | Guide Latents (default) or TARA (experimental) |
| Motion Transfer | Motion Transfer v1.0, Motion Transfer TARA v1.0 or Motion Transfer FFP v1.0, selected in the main generation panel (a First Frame selects Motion Transfer FFP v1.0) | Guide Latents (default) or TARA (experimental) |

The motion model and method are independent. A guide-trained LoRA may be used
with TARA; a TARA-trained LoRA may be selected with Guide Latents. Wiring support
is not a claim that all combinations have equal quality.

## Required H3 files

Download the exact files below. The last column is relative to ComfyUI.

| File / download | Destination |
| --- | --- |
| [H3 ref2va pruned INT8 ConvRot](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors) | `models/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| [H3 Qwen3-VL 32B text encoder](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors) | `models/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors` |
| [H3 video VAE FP16](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors) | `models/vae/minimax_h3_video_vae_fp16.safetensors` |
| [Character Swap v1.1](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_character_swap_v1.1_ref2va_fro.safetensors) | `models/loras/henge/minimax_h3_character_swap_v1.1_ref2va_fro.safetensors` |
| [Character profile's 8-step DMD adapter](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI/resolve/main/experimental/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors) | `models/loras/henge/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors` |
| [H3 audio VAE](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors), optional for audio conditioning | `models/vae/minimax_h3_audio_vae_fp32.safetensors` |

H3 conditioning uses the 32B H3 encoder even when a smaller VLM is used for prompt
writing. The writer does not replace that encoder.

### Henge LoRAs (BFS collection)

Every file keeps its published name under `models/loras/henge/`; no renaming. All are public on
[Alissonerdx/Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI) (`download_models.py`
profiles in brackets).

| Mode | File |
| --- | --- |
| Motion Transfer v1.0 (`motion`) | [`minimax_h3_motion_transfer_v1.0_ref2va.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_motion_transfer_v1.0_ref2va.safetensors) — 185 MB, training adapter V2 merged in |
| Motion Transfer TARA v1.0 (`motion`) | [`minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors) — 126 MB, training adapter V2 merged in |
| Motion Transfer FFP v1.0 (`ffp`, part of `motion`) | [`minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors) — 220 MB: the VFX Edit first-frame LoRA (rank 128) ×1.0 + SolarRenderer control ×0.5, rank concat with per-module SVD keeping 99% of the Frobenius energy. The studio selects it whenever a First Frame is attached |
| SolarRenderer 4-step turbo (`solar`, installed with `ffp`) | [`solarrenderer/solarrenderer_4step_comfy_fro_dyn99.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/solarrenderer/solarrenderer_4step_comfy_fro_dyn99.safetensors) — 1.4 GB, per-module SVD keeping 99% of the Frobenius energy (the full-rank 5.9 GB `solarrenderer_4step_comfy.safetensors` is used when already installed). Optional speed LoRA: the Edit model already carries SolarRenderer control, so it runs on the standard 4-step turbo. Any model can select it under Advanced → Turbo LoRA |
| Head Swap v1.0 (`headswap`) | [`minimax_h3_head_swap_v1.0_r32.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_head_swap_v1.0_r32.safetensors) |
| Little More Sharpness v1.0 (`sharpness`) | [`minimax_h3_lms_v1.0_r64.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_lms_v1.0_r64.safetensors) |

**Training adapter V2 merged in.** The Motion Transfer LoRAs were trained on top of
[ostris' training adapter V2](https://huggingface.co/ostris/minimax_h3_training_adapter), which counters the
distillation of the base while training. Since 2026-11-02 the published `minimax_h3_motion_transfer_v1.0_ref2va` and
`minimax_h3_motion_transfer_tara_v1.0_ref2va` files carry it: LoRA x1 + adapter x1 by exact rank concat, then per-module
SVD keeping 99% of the Frobenius energy (185 MB and 126 MB instead of 620 MB + 310 MB). Generation runs base, turbo LoRA,
then this one file; do not load the adapter again on top. The previous files (without the adapter) are kept in
`loras/base_loras_ignore/`. The manifest gives these two files a `size`: a copy of another size under the same name (the
previous release) counts as not installed, so `/health` lists the model as missing and installing it again downloads the
new file. In tests with the same seed they matched the full LoRA + separate adapter, including TARA's frame sync across
camera cuts.

Models already in your ComfyUI are reused as they are: under an older short name (for example `character_v1_1`,
`training_adapter_v2`) or in another subfolder (for example `vae/minimax/…`). The bridge finds them by name and
`download_models.py` skips them without renaming, so your other workflows keep working.
The VFX Edit first-frame LoRA behind Motion Transfer FFP v1.0 (`ffp`, part of `motion`) is merged with SolarRenderer
control (Enderfga, MiniMax H3 Community License); both are public on the same Hugging Face repository. The older
comparison LoRAs (the dyn95 mixes and the SolarRenderer control alone, kept under `loras/experimental/`) were removed
from that repository: a job rendered with them re-renders only where those files are still installed.

## Prompt writer / media analysis

The current local planner defaults to
[qwen3.5_9b_w4a8_gptq.safetensors](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors)
(Qwen3.5 9B, W4A8 GPTQ).
Put it in `models/text_encoders/`. `HENGE_VLM_CLIP` may select another installed
ComfyUI-compatible vision encoder supported by TextGenerate. Selecting an
incompatible checkpoint is not automatic model conversion.

Each reference is described separately, sampled guide frames are analyzed
separately, then a text-only stage composes the H3 prompt. The routing analysis
chooses optional preparation without rewriting that execution prompt. Turning
off Enhance prompt preserves the user's text.

## Automatic reference preparation (optional)

Reference preparation and frame edits use one installed image editor: **FIBO 2.0 edit turbo** by default, which samples
the latent of the frame it is given, so the camera, the performer and the composition survive the edit. **Qwen-Image
2.1 Turbo** and **FLUX Klein** are alternatives you pick in the First Frame modal. It can prepare an upright, human-compatible animal reference while
preserving its identity. Normal human-to-human swaps do not require adaptation just because
of hair, wardrobe, makeup or skin colour. Review the plan and choose **Adapt reference** or
**Use original image**; the uploaded original is retained.

The `fibo` profile lists the FIBO 2.0 model, its Qwen3-VL 4B encoder and the shared FLUX VAE. `qwen21` (optional) adds
Qwen-Image 2.1 with its Qwen3-VL 8B encoder and its own VAE; `klein` and `klein3` stay available as alternative FLUX
editors. In `qwen21`, Henge loads the 7.3 GB Turbo checkpoint when it is installed; the 335 MB
`p_q_image_2.1_5_steps_v0.1_comfyui_bf16.safetensors` LoRA gives the full checkpoint the same 5 steps at CFG 1, so a
disk that cannot fit the Turbo build still gets the fast edit. `TextEncodeFibo2` and `TextEncodeQwenImage21` are core
ComfyUI nodes: no custom node pack is needed. Set `HENGE_FRAME_EDITOR=fibo|qwen21|klein|klein3` to change the order the
studio starts from.

Preparation is an appearance/pose aid, not temporal skeletal retargeting or a quality guarantee.

## Optional subject guidance

- [SAM 3.1 multiplex FP16](https://huggingface.co/Comfy-Org/SAM3.1/resolve/main/checkpoints/sam3.1_multiplex_fp16.safetensors): `models/checkpoints/sam3.1_multiplex_fp16.safetensors`.
- [SAM 3D Body DINOv3 BF16](https://huggingface.co/Comfy-Org/sam-3d-body/resolve/main/detection/sam_3d_body_dinov3_bf16.safetensors): `models/detection/sam_3d_body_dinov3_bf16.safetensors`.
- The current human 3D path also loads `moge_2_vitl_normal_fp16.safetensors` from
  `models/geometry_estimation/`; use the distribution supported by ComfyUI's
  native LoadMoGeModel node. A verified public download link for that exact
  packaged file remains to be documented.

SAM 3D Body is for human sources. Animal sources use original or 2D guidance.
The original-guide branch does not require these tracking models.

## Nodes and startup

Install the [BFSNodes main branch](https://github.com/alisson-anjos/ComfyUI-BFSNodes)
for TARA and link/copy `backend/comfy_nodes/henge` into
`ComfyUI/custom_nodes/henge`. The provided launcher allows both `henge` and
`bfsnodes` through its custom-node whitelist. The backend API port is 8766 and
ComfyUI is 8189; the browser connects to Next.js, which proxies the bridge.
Configure `.env.local` for your paths and start with `python scripts/start_backend.py`.
The launcher's default paths and dependency overlay are Linux/pod defaults;
adapt them for your local environment. It is not a one-click Windows installer.

Model registration and CPU graph checks do not prove every optional GPU branch
works on every machine. Review actual results, especially multi-character
bindings, anatomical changes, cuts and 3D guidance. Check each model's own license.

## Live sampling preview

The launcher enables ComfyUI's `--preview-method taesd`. For H3, install a
[ComfyUI-compatible `taeh3.safetensors`](https://huggingface.co/t8star/Taeh3-Comfy/resolve/main/models/vae_approx/taeh3.safetensors) in `models/vae_approx/` (the shared model
paths now include `vae_approx`). If the decoder is missing, ComfyUI may fall back
to a simpler latent-to-RGB preview; it must not be described as a verified TAEH3
preview in that configuration.

During video sampling the bridge receives ComfyUI's per-client binary image
previews and the studio displays them beside the guide and under progress.
This is an approximate **frame** that updates across sampling steps, not a
playback of every generated video frame. The final video still uses the full
video VAE. Previews are tied to their job, and malformed or foreign-job metadata
is discarded. CPU protocol checks are separate from real GPU preview validation.

## Finished preview and downloads

Once a job finishes, the result player offers **Result** and **Guide + result +
references**. The second view is one synchronized MP4 containing the original
guide, generated result and labelled original Picture thumbnails. It can also
be downloaded with **Download comparison + references**. The first request
creates and caches that comparison on CPU; existing completed jobs with their
uploaded references can use it too. Audio follows the finished result. Preview
width is capped at 1600 pixels to keep the comparison manageable; the separate
result download retains its original resolution.

## Pika H3 Flex turbo

The Ref2VA Comfy adapter is included in normal downloads through the `common` profile, with a pinned upstream
revision and license/notice files. It is an optional turbo choice, not a new default turbo. Install it under
`models/loras/henge/pika_h3_flex_ref2va_comfy_bf16.safetensors` (the official full-rank Pika-Labs BF16 adapter,
approximately 1.96 GB); `--profiles pika` can top up an existing models
folder. Serverless needs a volume top-up through a pod, not just a worker environment change.
See [Pika sampling, step overrides and deployment](pika-h3-flex.md).

New catalog entries can also be installed from **Settings → Models**, locally or through an updated Serverless
worker. See [model installation and update notifications](models-and-updates.md).
