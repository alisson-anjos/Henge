# Henge — open character & motion studio

Character swap and motion transfer for video, built on **ComfyUI** with
**MiniMax-H3**. One pod runs the web UI, the job bridge and ComfyUI.

**Open the app:** *Connect → HTTP Service [8188]* once the logs show the UI is up.

## First boot

The pod downloads the models into your volume at `/workspace/henge/models`
(≈ 65 GB with the default profiles). This takes a while the first time only;
later boots, or a new pod on the same network volume, start straight away.
Follow progress in **Logs** (`Downloading: …` / `Installed: …`).

## Modes

| Mode | Models |
|---|---|
| Character Swap v1.1 | H3 ref2va + Character Swap v1.1 LoRA + DMD 8-step |
| Motion · Original 10500 | H3 ref2va + training adapter V2 + motion 10500 |
| Motion · TARA 4500 | H3 ref2va + training adapter V2 + TARA motion 4500 |

The prompt planner / VLM is Qwen3.5 9B (W4A8 GPTQ), running inside ComfyUI.

## GPU

- Needs a host driver with **CUDA 13.0+** — set the CUDA filter when deploying.
- 32 GB VRAM works (RTX 5090); 48–80 GB (L40S, RTX 6000 Ada, A100, H100) is faster.
- Prefer ≥ 64 GB system RAM.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `HF_TOKEN` | — | Hugging Face token. Required for the motion LoRAs while they are private |
| `HENGE_MODEL_PROFILES` | `character,motion10500,motion4500` | Also: `fibo`, `sam2d`, `sam3d`, `audio` |
| `HENGE_MODEL_OVERRIDES` | — | JSON to replace a model URL, e.g. `{"motion4500":{"url":"https://…"}}` |
| `HENGE_COMFY_ARGS` | `--lowvram` | Extra ComfyUI flags (`--highvram` on 80 GB GPUs) |
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
