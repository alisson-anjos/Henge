# Run Henge on RunPod

**Video tutorial (4 min):** [both RunPod options step by step](https://www.youtube.com/watch?v=sthVq1_jPtM) ([download](https://github.com/alisson-anjos/Henge/releases/download/demo-v1/henge-runpod-tutorial.mp4)), from the network volume to a job on
Serverless.

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

## 2. Deploy the template

**Use the Henge template: [Deploy on RunPod](https://console.runpod.io/deploy?template=mnxax277c8&ref=8t518hht).** It has the image, disks, ports and environment below
already set. New to RunPod? [Create your account with our link](https://runpod.io?ref=8t518hht).

In the deploy screen pick a GPU with more than 32 GB and *Deploy Pod*; no variable needs changing. To keep the models
when the pod is deleted (and share them with a [Serverless](SERVERLESS.md) endpoint), first create a network volume
(*Storage → New volume*, 180 GB, in the datacenter of the GPU you want) and select it under *Region → Network
volume*. Without one, the models live on the pod's own volume and go away with the pod.

To build your own template instead, RunPod → **My Templates → New Template** (type *Pod*):

| Field | Value |
|---|---|
| Container image | `ghcr.io/alisson-anjos/henge:latest` |
| Container disk | 30 GB |
| Volume disk | 180 GB (default profiles incl. OmniRef and FIBO) |
| Volume mount path | `/workspace` |
| Expose HTTP ports | `8188` (add `8189` to open ComfyUI too) |
| Expose TCP ports | `22` |

Environment variables (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `HENGE_MODEL_PROFILES` | `character,motion,headswap,sharpness,omniref,fibo,klein,sam2d,sam3d,audio` | Comma list: `character`, `omniref` (+22 GB base), `fibo`, `sam2d`, `sam3d`, `audio`, `motion` (Motion Transfer v1.0, TARA v1.0, Combined), `solar` (~25 GB: SolarRenderer control alone, its 0.5 merges with Motion Transfer v1.0 and TARA v1.0, and the Solar 4-step turbo), `klein` (FLUX.2 Klein 4B first-frame editor) |
| `HF_TOKEN` | — | Not needed: every model is public. Only for an override that points at your own private repository |
| `HENGE_MODEL_OVERRIDES` | — | JSON that replaces a model URL or destination from the bundled manifest |
| `HENGE_VLM_CLIP` | `qwen3.5_9b_w4a8_gptq.safetensors` | Prompt planner / VLM |
| `HENGE_COMFY_ARGS` | `--lowvram` | Extra ComfyUI flags. Leave the default: ComfyUI's dynamic VRAM loads and offloads models as needed. Do not use `--highvram` or `--gpu-only`, even on 80 GB GPUs: they keep the 32B text encoder and the VLM on the GPU next to H3 and run out of memory. (`--normalvram` does not exist in this ComfyUI and stops it from starting.) |
| `HENGE_PASSWORD` | — | Optional login for the UI (user `HENGE_USER`, default `henge`). Unset: open to anyone with the pod URL until you turn a login on from the 🔓 button in the top bar (saved on the volume). The env value wins over the UI one |
| `HENGE_LIKENESS_FILTER` | `off` | `warn`: the plan warns when a reference picture looks like a real public figure (celebrity, politician, athlete...). `block`: such a job stops before generating. Checked by the planner VLM, one short question per picture; no names are asked or stored |
| `HENGE_EXPOSE_COMFY` | — | `1` makes ComfyUI listen on `0.0.0.0:8189` for debugging. ComfyUI has **no login**: anyone with the URL can run graphs on your GPU, so leave it off on shared pods |
| `PUBLIC_KEY` | — | RunPod injects your SSH key; enables `sshd` |

Every model Henge downloads is public (the Henge LoRAs, FFP and Solar included), so the template sets no token and
needs no RunPod secret. `HF_TOKEN` only matters for an override that points at your own private repository; store it
as a RunPod secret and set `HF_TOKEN={{ RUNPOD_SECRET_hf_token }}` under *Set overrides*. A reference to a secret your
account does not have is ignored.

To point an entry at another link without rebuilding, set
`HENGE_MODEL_OVERRIDES`, e.g.
`{"motion_transfer_tara_v1":{"url":"https://huggingface.co/USER/REPO/resolve/main/file.safetensors"}}`.
You can also drop a complete manifest at `/workspace/henge/model-repos.json`;
it replaces the bundled one.

## 3. GPU

The image uses PyTorch 2.14 + CUDA 13.0, so the host driver must support CUDA 13
(driver ≥ 580). In the deploy screen, set the **CUDA version filter to 13.0+**.

- 32 GB VRAM works with `--lowvram` (RTX 5090 tested locally).
- 48 GB (L40S, RTX 6000 Ada) or 80 GB (A100, H100) give more headroom and speed.
- Prefer ≥ 64 GB system RAM: the H3 text encoder alone is 27 GB.

## 4. First boot

Open **Connect → HTTP 8188**: the Henge setup screen lists every model with its progress and opens the studio by
itself when they are ready (about 10 minutes on RunPod's network). The first boot downloads ≈ 125 GB with the default profiles (H3 21 GB + H3 text encoder 27 GB + VAE
5 GB + Qwen3.5 planner 7 GB + OmniRef 22 GB + FIBO 14 GB + SAM ≈ 4 GB + the task, turbo and Motion Transfer LoRAs);
fewer profiles download less. When ComfyUI and the UI are up, open **Connect → HTTP 8188**
(`https://<pod-id>-8188.proxy.runpod.net`).

A model that cannot be downloaded (network error, a renamed file) is
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
(`fasth3_omniref_8step_pruned_int8_convrot`, 22 GB; with the default profiles use a 180 GB volume). Pick it in
**Advanced → Base model**; it is already distilled to 8 steps, so Turbo LoRA switches to
**None**. The task LoRAs (Character Swap, Head Swap, Motion) still load on top.

## Serverless (UI on your PC, GPU only while a job runs)

Full guide: [SERVERLESS.md](SERVERLESS.md).

Instead of a pod that stays on, the UI can drive a RunPod Serverless endpoint: each job stage (plan,
reference prep, every shot) becomes one request, a worker starts when needed and scales back to zero.

1. **Models on a network volume** (once): `scripts/runpod_volume.sh` creates a volume
   (`DATACENTER`, default `EU-RO-1`; `VOLUME_GB`, default 180) and fills it with a temporary pod from the
   Henge template, deleted when every model is installed. Workers read it at `/runpod-volume/henge/models`.
   Or in the console: deploy this template on a network volume, wait for the models, stop the pod.
2. **Endpoint**: `VOLUME_ID=<id> scripts/runpod_serverless.sh` creates the worker template (the full image
   with `HENGE_ROLE=worker`) and the endpoint (0 to 2 workers, RTX 5090, idle timeout 15 s), or follow the
   console steps in [SERVERLESS.md](SERVERLESS.md#or-in-the-runpod-console).
3. **UI**: `docker run -p 8188:8188 -v henge-state:/state -e HENGE_BACKEND=runpod -e RUNPOD_ENDPOINT_ID=<id>
   -e RUNPOD_API_KEY=<key> ghcr.io/alisson-anjos/henge-ui:latest`, then open http://localhost:8188.

The first request after an idle period waits for a cold start (ComfyUI start + model load from the volume).
Media of any size travel through the endpoint's volume in chunks. Model availability is learned from the first
finished request; until then every mode shows as available.
