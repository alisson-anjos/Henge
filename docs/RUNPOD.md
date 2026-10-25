# Run Henge on RunPod

One container runs everything: the web UI (port 8188), the bridge and ComfyUI.
Models download on the first boot into the pod's volume at `/workspace`, so the
next boots (or a new pod with a different GPU on the same network volume) start
without downloading again.

## Models

On every boot the container reads the bundled manifest
`config/model-repos.example.json` and downloads, by `url`, every entry whose
profile is `common` or listed in `HENGE_MODEL_PROFILES`. Files already on the
volume are skipped, so only the first boot downloads. To change a link, edit
that file (and rebuild) or override it at runtime (see below).

## 1. Image

The GitHub Actions workflow `.github/workflows/docker.yml` builds and pushes:

```
ghcr.io/alisson-anjos/henge:latest        # main
ghcr.io/alisson-anjos/henge:<branch>      # any other branch
ghcr.io/alisson-anjos/henge:sha-<commit>  # every build
```

If the GHCR package is private, add a registry credential in RunPod
(**Settings → Container Registry Auth**): registry `ghcr.io`, your GitHub username
and a personal access token with `read:packages`. Select it in the template.
A public package needs no credential.

## 2. Create the template

RunPod → **My Templates → New Template** (type *Pod*):

| Field | Value |
|---|---|
| Container image | `ghcr.io/alisson-anjos/henge:latest` |
| Container disk | 30 GB |
| Volume disk | 150 GB (default profiles incl. OmniRef) |
| Volume mount path | `/workspace` |
| Expose HTTP ports | `8188` (add `8189` to open ComfyUI too) |
| Expose TCP ports | `22` |

Environment variables (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `HENGE_MODEL_PROFILES` | `character,motion10500,motion4500,solar,headswap,sharpness,omniref` | Comma list: `character`, `omniref` (+22 GB base), `fibo`, `sam2d`, `sam3d`, `audio`, `motion10500`, `motion4500`, `solar` (~25 GB: SolarRenderer control alone, its 0.5 merges with motion 10500/4500, and the Solar 4-step turbo) |
| `HF_TOKEN` | — | **Required for the motion LoRAs** (private for now). Use a RunPod secret: `{{ RUNPOD_SECRET_hf_token }}` |
| `HENGE_MODEL_OVERRIDES` | — | JSON that fills manifest entries, e.g. the private motion LoRAs (below) |
| `HENGE_VLM_CLIP` | `qwen3.5_9b_w4a8_gptq.safetensors` | Prompt planner / VLM |
| `HENGE_COMFY_ARGS` | `--lowvram` | Extra ComfyUI flags. On 80 GB GPUs try `--highvram` |
| `HENGE_EXPOSE_COMFY` | — | `1` makes ComfyUI listen on `0.0.0.0:8189` for debugging |
| `PUBLIC_KEY` | — | RunPod injects your SSH key; enables `sshd` |

The motion LoRAs live in the private dataset `Alissonerdx/Kagemage-Backups`
until they are published, so the default profiles
(`character,motion10500,motion4500,solar,headswap,sharpness,omniref`) need `HF_TOKEN` with read access. Without
it, Character Swap still installs and the motion modes show as unavailable.

To point an entry at another link without rebuilding, set
`HENGE_MODEL_OVERRIDES`, e.g.
`{"motion4500":{"url":"https://huggingface.co/USER/REPO/resolve/main/file.safetensors"}}`.
You can also drop a complete manifest at `/workspace/henge/model-repos.json`;
it replaces the bundled one.

## 3. GPU

The image uses PyTorch 2.14 + CUDA 13.0, so the host driver must support CUDA 13
(driver ≥ 580). In the deploy screen, set the **CUDA version filter to 13.0+**.

- 32 GB VRAM works with `--lowvram` (RTX 5090 tested locally).
- 48 GB (L40S, RTX 6000 Ada) or 80 GB (A100, H100) give more headroom and speed.
- Prefer ≥ 64 GB system RAM: the H3 text encoder alone is 27 GB.

## 4. First boot

Watch **Logs**. The first boot downloads ≈ 65 GB with the default profiles
(H3 21 GB + H3 text encoder 27 GB + VAE 5 GB + Qwen3.5 planner 7 GB + Character
LoRAs 2.4 GB + motion LoRAs + adapter V2 1.6 GB). When ComfyUI and the UI are up, open **Connect → HTTP 8188**
(`https://<pod-id>-8188.proxy.runpod.net`).

A model that cannot be downloaded (e.g. a private LoRA without a token) is
logged and skipped; the UI marks that mode unavailable instead of the pod
restarting in a loop.

## 5. Data layout on the volume

```
/workspace/henge/
  models/            ComfyUI models (symlinked from /opt/ComfyUI/models)
  input/  output/    ComfyUI input/output
  state/jobs/        Henge job history and artifacts
  huggingface/       HF cache
  model-repos.json   optional manifest override
```

Set `HENGE_WORKSPACE=off` to keep everything inside the container instead.

## Optional base model: FastH3 OmniRef

Add `omniref` to `HENGE_MODEL_PROFILES` to download
[FastVideo/FastH3-Omni-Comfy](https://huggingface.co/FastVideo/FastH3-Omni-Comfy)
(`fasth3_omniref_8step_pruned_int8_convrot`, 22 GB; use a 150 GB volume). Pick it in
**Advanced → Base model**; it is already distilled to 8 steps, so Turbo LoRA switches to
**None**. The task LoRAs (Character Swap, Head Swap, LMS, Motion) still load on top.
