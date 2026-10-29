# Henge — Swap · Motion · Transform

Character swap, motion transfer, head swap and sharpness for video, built on **ComfyUI** with
**MiniMax H3** and a trained LoRA per mode. One pod runs the web UI, the job bridge and ComfyUI.

New to RunPod? Create your account with our link: https://get.runpod.io/z4bz8o1va7a7

**Open the app:** *Connect → HTTP Service [8188]* once the logs show the UI is up.

## First boot

The pod downloads the models into your volume at `/workspace/henge/models`
(≈ 125 GB with the default profiles, about 10 minutes). Open *Connect → HTTP 8188*:
the setup screen shows each model's progress and opens the studio when they are ready.

To keep the models when the pod is deleted (or to feed a Serverless endpoint), create a
network volume first (*Storage → New volume*, 180 GB) and pick it under *Region → Network
volume*; later pods on that volume start straight away. Pick a GPU with more than 32 GB.

## Modes

| Mode | Models |
|---|---|
| Character Swap v1.1 | H3 ref2va + Character Swap v1.1 LoRA + DMD 8-step |
| Motion Transfer v1.0 / TARA v1.0 / Combined / FFP | H3 ref2va + training adapter V2 + the Motion Transfer LoRAs (`motion` profile) |
| Head Swap v1.0 | H3 ref2va + Head Swap r32 + turbo LoRA; face picture + source video |
| Sharpness | Ref2VA + LMS, then Refiner + LMS + Add Guide by default (1080p/2K; requires optional `regenerate` weights and updated worker). H3 and NVIDIA upscale remain available, including 4K. Source video only. |

Turbo LoRA (Character, Head Swap): DMD 8-step (default), DMAD 4-step,
lightx2v 8-step v1.1 or lightx2v 4-step v1.0, chosen in the advanced settings.

The prompt planner / VLM is Qwen3.5 9B (W4A8 GPTQ), running inside ComfyUI.

## GPU

- Needs a host driver with **CUDA 13.0+** — set the CUDA filter when deploying.
- 32 GB VRAM works (RTX 5090); 48–80 GB (L40S, RTX 6000 Ada, A100, H100) is faster.
- Prefer ≥ 64 GB system RAM.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `HF_TOKEN` | — | **Not needed** for the default profiles. Only for the optional `klein3` (FLUX.3 [image klein], gated: accept its license on Hugging Face first) |
| `HENGE_MODEL_PROFILES` | `character,motion,headswap,sharpness,regenerate,omniref,klein,sam2d,sam3d,audio` | `motion` = every Motion Transfer LoRA, FFP included; `regenerate` = Open-H3 refiner and native latent upscaler (default Sharpness method); `klein` = FLUX.2 Klein 4B first-frame editor; also `solar` (~25 GB) |
| `HENGE_MODEL_OVERRIDES` | — | JSON to replace a model URL, e.g. `{"motion_transfer_tara_v1":{"url":"https://…"}}` |
| `HENGE_COMFY_ARGS` | `--lowvram` | Extra ComfyUI flags. Leave the default: ComfyUI's dynamic VRAM loads and offloads models as needed. Do not use `--highvram` or `--gpu-only`, even on 80 GB GPUs: they keep the 32B text encoder and the VLM on the GPU next to H3 and run out of memory. (`--normalvram` does not exist in this ComfyUI and stops it from starting.) |
| `HENGE_EXPOSE_COMFY` | — | `1` also serves ComfyUI on port 8189 |

A model that fails to download is skipped and its mode shows as unavailable;
the pod keeps running.

## Data on the volume

```
/workspace/henge/models       ComfyUI models
/workspace/henge/input|output ComfyUI input / output
/workspace/henge/state/jobs   job history and results
```

Source, setup and license (MIT): https://github.com/alisson-anjos/Henge

## Optional base model: FastH3 OmniRef

Add `omniref` to `HENGE_MODEL_PROFILES` to download
[FastVideo/FastH3-Omni-Comfy](https://huggingface.co/FastVideo/FastH3-Omni-Comfy)
(`fasth3_omniref_8step_pruned_int8_convrot`, 22 GB; with the default profiles use a 180 GB volume). Pick it in
**Advanced → Base model**; it is already distilled to 8 steps, so Turbo LoRA switches to
**None**. The task LoRAs (Character Swap, Head Swap, Motion) still load on top.

### Enable Refiner + LMS

For a normal pod, add `regenerate` to `HENGE_MODEL_PROFILES` and use the updated image.
Serverless workers do not download weights: first top up the attached network volume with a temporary fill pod, then update/recycle the workers and refresh the bridge inventory through a short Henge job. See [Serverless upgrade steps](../docs/SERVERLESS.md#enable-refiner--lms-on-an-existing-endpoint) and [required files/nodes](../docs/open-h3-regenerate.md).
