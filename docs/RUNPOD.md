# Run Kawarimi on RunPod

One container runs everything: the web UI (port 8188), the bridge and ComfyUI.
Models download on the first boot into the pod's volume at `/workspace`, so the
next boots (or a new pod with a different GPU on the same network volume) start
without downloading again.

## 1. Image

The GitHub Actions workflow `.github/workflows/docker.yml` builds and pushes:

```
ghcr.io/alisson-anjos/kawarimi:latest        # main
ghcr.io/alisson-anjos/kawarimi:<branch>      # any other branch
ghcr.io/alisson-anjos/kawarimi:sha-<commit>  # every build
```

If the GHCR package is private, add a registry credential in RunPod
(**Settings → Container Registry Auth**): registry `ghcr.io`, your GitHub username
and a personal access token with `read:packages`. Select it in the template.
A public package needs no credential.

## 2. Create the template

RunPod → **My Templates → New Template** (type *Pod*):

| Field | Value |
|---|---|
| Container image | `ghcr.io/alisson-anjos/kawarimi:latest` |
| Container disk | 30 GB |
| Volume disk | 100 GB (Character); 130 GB with `fibo,sam2d` |
| Volume mount path | `/workspace` |
| Expose HTTP ports | `8188` (add `8189` to open ComfyUI too) |
| Expose TCP ports | `22` |

Environment variables (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `KAWARIMI_MODEL_PROFILES` | `character` | Comma list: `character`, `fibo`, `sam2d`, `sam3d`, `audio`, `motion10500`, `motion4500` |
| `HF_TOKEN` | — | Needed for private model repositories. Use a RunPod secret: `{{ RUNPOD_SECRET_hf_token }}` |
| `KAWARIMI_MODEL_OVERRIDES` | — | JSON that fills manifest entries, e.g. the private motion LoRAs (below) |
| `KAWARIMI_VLM_CLIP` | `qwen3.5_9b_w4a8_gptq.safetensors` | Prompt planner / VLM |
| `KAWARIMI_COMFY_ARGS` | `--lowvram` | Extra ComfyUI flags. On 80 GB GPUs try `--highvram` |
| `KAWARIMI_EXPOSE_COMFY` | — | `1` makes ComfyUI listen on `0.0.0.0:8189` for debugging |
| `PUBLIC_KEY` | — | RunPod injects your SSH key; enables `sshd` |

Private motion LoRAs, until they are published:

```json
{"motion10500":{"repo_id":"Alissonerdx/REPO","filename":"motion_10500.safetensors"},
 "motion4500":{"repo_id":"Alissonerdx/REPO","filename":"motion_tara_4500.safetensors"}}
```

Put that JSON in `KAWARIMI_MODEL_OVERRIDES`, add `motion10500,motion4500` to
`KAWARIMI_MODEL_PROFILES` and set `HF_TOKEN`. You can also drop a complete
manifest at `/workspace/kawarimi/model-repos.json`; it replaces the bundled one.

## 3. GPU

The image uses PyTorch 2.14 + CUDA 13.0, so the host driver must support CUDA 13
(driver ≥ 580). In the deploy screen, set the **CUDA version filter to 13.0+**.

- 32 GB VRAM works with `--lowvram` (RTX 5090 tested locally).
- 48 GB (L40S, RTX 6000 Ada) or 80 GB (A100, H100) give more headroom and speed.
- Prefer ≥ 64 GB system RAM: the H3 text encoder alone is 27 GB.

## 4. First boot

Watch **Logs**. The first boot downloads ≈ 63 GB for the Character profile
(H3 21 GB + H3 text encoder 27 GB + VAE 5 GB + Qwen3.5 planner 7 GB + Character
LoRAs 2.4 GB). When ComfyUI and the UI are up, open **Connect → HTTP 8188**
(`https://<pod-id>-8188.proxy.runpod.net`).

A model that cannot be downloaded (e.g. a private LoRA without a token) is
logged and skipped; the UI marks that mode unavailable instead of the pod
restarting in a loop.

## 5. Data layout on the volume

```
/workspace/kawarimi/
  models/            ComfyUI models (symlinked from /opt/ComfyUI/models)
  input/  output/    ComfyUI input/output
  state/jobs/        Kawarimi job history and artifacts
  huggingface/       HF cache
  model-repos.json   optional manifest override
```

Set `KAWARIMI_WORKSPACE=off` to keep everything inside the container instead.
