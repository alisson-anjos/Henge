# Models and local setup

Henge uses an existing ComfyUI installation plus its local job bridge. Model
weights are not included in this GitHub repository. Place files under the
ComfyUI directory configured by `COMFY_ROOT`, or expose them with ComfyUI's
`extra_model_paths.yaml`. Restart ComfyUI after adding models.

## What the user selects

| Task | LoRA | Method |
| --- | --- | --- |
| Character Swap | Character Swap v1.1, selected automatically | Guide Latents (default) or TARA (experimental) |
| Motion Transfer | Motion Transfer v1.0 or Motion Transfer TARA v1.0 | Guide Latents (default) or TARA (experimental), in the main generation panel |

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
| [Motion profiles' training adapter V2](https://huggingface.co/ostris/minimax_h3_training_adapter/resolve/main/minimax_h3_ref2va_training_adapter_v2.safetensors) | `models/loras/henge/minimax_h3_ref2va_training_adapter_v2.safetensors` |
| [H3 audio VAE](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors), optional for audio conditioning | `models/vae/minimax_h3_audio_vae_fp32.safetensors` |

H3 conditioning uses the 32B H3 encoder even when a smaller VLM is used for prompt
writing. The writer does not replace that encoder.

### Henge LoRAs (BFS collection)

Every file keeps its published name under `models/loras/henge/`; no renaming. All are public on
[Alissonerdx/Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI) (`download_models.py`
profiles in brackets).

| Mode | File |
| --- | --- |
| Motion Transfer v1.0 (`motion`) | [`minimax_h3_motion_transfer_v1.0_ref2va.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_motion_transfer_v1.0_ref2va.safetensors) |
| Motion Transfer TARA v1.0 (`motion`) | [`minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors) |
| Motion Transfer Combined, test (`motion`) | [`…combined_v1.0_dyn95`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_motion_transfer_combined_v1.0_dyn95.safetensors), [`…combined_v1.0_dyn99`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_motion_transfer_combined_v1.0_dyn99.safetensors) |
| Head Swap v1.0 (`headswap`) | [`minimax_h3_head_swap_v1.0_r32.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_head_swap_v1.0_r32.safetensors) |
| Little More Sharpness v1.0 (`sharpness`) | [`minimax_h3_lms_v1.0_r64.safetensors`](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_lms_v1.0_r64.safetensors) |

**Training adapter V2 with the motion LoRAs.** The Motion Transfer LoRAs were trained on top of
[ostris' training adapter V2](https://huggingface.co/ostris/minimax_h3_training_adapter) kept frozen. They will usually
work without it, but loading the adapter first (strength 1) and the motion LoRA after it reproduces the training
conditions, which is what Henge does; compare both on your own clips. Do not load a file that already merges the
adapter (for example an exact Motion Transfer v1.0 + V2 merge) together with the adapter again.

Models already in your ComfyUI are reused as they are: under an older short name (for example `character_v1_1`,
`training_adapter_v2`) or in another subfolder (for example `vae/minimax/…`). The bridge finds them by name and
`download_models.py` skips them without renaming, so your other workflows keep working.
The experimental FFP model (`ffp`) and the `solar` profile are third-party merges and stay private.

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

FIBO is recommended when an animal reference needs to follow a human performance:
for example, a dog with upright posture and human-compatible limbs while keeping
its animal identity. A normal human-to-human swap does not activate preparation
because of hair, wardrobe, makeup or skin color. The reviewed plan offers **Adapt
reference** and **Use original image**. Preparation can also be disabled under
Advanced. The uploaded original is retained; the prepared image is additional.

| File / download | Destination |
| --- | --- |
| [FIBO 2.0 Edit Turbo INT8](https://huggingface.co/Comfy-Org/Fibo-2.0/resolve/main/diffusion_models/fibo2_edit_turbo_int8_convrot.safetensors) | `models/diffusion_models/fibo2_edit_turbo_int8_convrot.safetensors` |
| [FIBO Qwen3-VL 4B encoder](https://huggingface.co/Comfy-Org/Fibo-2.0/resolve/main/text_encoders/qwen3vl_4b_int8_convrot.safetensors) | `models/text_encoders/qwen3vl_4b_int8_convrot.safetensors` |
| [Flux2 VAE](https://huggingface.co/Comfy-Org/Fibo-2.0/resolve/main/vae/flux2-vae.safetensors) | `models/vae/flux2-vae.safetensors` |

See the [FIBO model card](https://huggingface.co/Comfy-Org/Fibo-2.0) for its
license, including noncommercial restrictions. Preparation is an appearance/pose
aid, not full temporal skeletal retargeting or a quality guarantee.

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
