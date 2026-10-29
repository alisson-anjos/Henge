# Henge on RunPod Serverless

**Video tutorial (4 min):** [both RunPod options step by step](https://www.youtube.com/watch?v=sthVq1_jPtM) ([download](https://github.com/alisson-anjos/Henge/releases/download/demo-v1/henge-runpod-tutorial.mp4)), from the network volume to a job on
Serverless.

Run the Henge UI on your own computer (no GPU needed) and pay for a GPU only while a job is
running. Each job stage is sent to a RunPod Serverless endpoint; workers start on demand and
scale back to zero when idle.

```
your PC                                   RunPod
┌──────────────────────────┐   /run       ┌──────────────────────────────────────┐
│ henge-ui (Docker)        │ ───────────► │ Serverless endpoint                  │
│  web UI :8188            │   /status    │  worker = henge image, HENGE_ROLE=worker
│  bridge (jobs, ffmpeg,   │ ◄─────────── │   ComfyUI + Henge/BFS nodes          │
│  planning, joining)      │   /cancel    │   docker/worker_handler.py           │
└──────────────────────────┘              │  models: network volume              │
                                          │   /runpod-volume/henge/models        │
                                          └──────────────────────────────────────┘
```

The default setup is unchanged: one pod running UI, bridge and ComfyUI together
([RUNPOD.md](RUNPOD.md)). Serverless is an alternative for occasional use.

## When to use it

| | Pod (default) | Serverless |
|---|---|---|
| GPU billing | whole time the pod is on | only while a request runs (plus idle timeout) |
| First result after idle | immediate | cold start, about 3 min |
| Clip length | any | any (large media go through the volume in chunks) |
| Live sampling preview | yes | progress only |
| Setup | template, one click | volume + endpoint: in the console (about 10 min) or two scripts |

## Requirements

- A RunPod account with credit and an API key (*Settings → API Keys*). New to RunPod? [Create your account with our link](https://get.runpod.io/z4bz8o1va7a7).
- For the scripts only: [`runpodctl`](https://github.com/runpod/runpodctl) configured (`runpodctl doctor`).
  Everything can also be done in the RunPod console (option B of each step).
- For the UI: Docker, or Node + Python (step 3).

## 1. Put the models on a network volume (once)

Serverless workers **never download models**: a worker that downloaded ~100 GB on its first request would
bill GPU time for it, hit the request timeout, and race other workers writing the same files. The models
go once onto a RunPod **network volume** (persistent storage); every worker mounts it read-only at
`/runpod-volume` and reads `/runpod-volume/henge/models`.

A temporary pod fills the volume: it runs the same Henge image with the volume at `/workspace`, its
downloader puts everything in `/workspace/henge/models` (the same folder the workers see), and the pod is
deleted afterwards. You pay a few minutes of that pod plus the volume's monthly storage.

### What goes on it

Choose the model profiles (comma list), as on a normal pod:

| Profile | Mode | Notes |
|---|---|---|
| `character` | Character Swap | base H3, text encoder, VAE, VLM planner; always needed |
| `motion` (or `motion_transfer`, `motion_transfer_tara`) | Motion Transfer | public, BFS Motion Transfer license |
| `solar` | Motion Transfer (Solar merges, experimental) | ~25 GB |
| `ffp` | Motion Transfer FFP: propagate an edited first frame (VFX Edit FFP + SolarRenderer 0.5; dyn99 and the lighter dyn95). Part of `motion` | 0.3 GB |
| `headswap` | Head Swap | |
| `sharpness` | Sharpness (H3 + Little More Sharpness LoRA; 2K/4K with the H3 or NVIDIA RTX upscaler) | ~1 GB (LoRA + H3 latent upscaler) |
| `regenerate` | Sharpness default: Ref2VA + DMAD + rank-16 refiner + LMS + native upscale | Optional install; top up the volume and update the worker; no FL2VA |
| `audio` | Generated audio and audio conditioning (H3 audio VAE) | ~0.3 GB |
| `omniref` | OmniRef base | +22 GB |
| `klein` | First-frame edits with FLUX.2 [klein] 4B (Black Forest Labs, Apache-2.0): replace, remove or add, optionally only in a painted area; also used for reference preparation | ~12 GB |
| `klein3` | Optional: FLUX.3 [image klein], used instead of FLUX.2 [klein] when installed. **Gated**: accept the FLUX Kommunity License at [black-forest-labs/flux-3-image-klein-comfy](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy) and set `HF_TOKEN` | ~5 GB |
| `sam2d`, `sam3d` | Subject marks: SAM 3.1 tracking (2D colors, Mask, the assistant's find people) and SAM 3D Body + MoGe (3D) | ~4 GB |

The default profiles (excluding optional additions such as `regenerate` and `klein3`) need roughly 125–135 GB: create the volume with 180 GB (`VOLUME_GB=180`).

### Option A: script

```sh
scripts/runpod_volume.sh                                       # new 180 GB volume, every profile
PROFILES=character,motion scripts/runpod_volume.sh             # only some profiles
VOLUME_ID=<id> scripts/runpod_volume.sh                        # top up an existing volume
```

- Creates the network volume (`DATACENTER`, default `EU-RO-1`; `VOLUME_GB`, default 180), unless
  `VOLUME_ID` is given.
- Starts the fill pod from `ghcr.io/alisson-anjos/henge:latest` on the first GPU in stock
  (`FILL_GPUS`), with `HENGE_MODEL_PROFILES=$PROFILES` .
- Prints the download progress every minute and deletes the pod when every model is installed.

A top-up skips the files that are already there: use it after an interrupted download or to add profiles.
If a download fails, the pod is kept so you can
open its setup screen; delete it with `runpodctl pod delete <pod id>` when done.

### Option B: RunPod console

1. *Storage* → *New volume*: pick the datacenter (see below), a name and 180 GB → *Create network volume*.
2. Open the [Henge pod template](https://console.runpod.io/deploy?template=mnxax277c8). Under
   *Region*, choose *Network volume* and select the new volume; pick a GPU with more than 32 GB of RAM in that
   datacenter (it is a normal Henge pod, so you can also use it right away) → *Deploy Pod*. To download only some
   profiles, set `HENGE_MODEL_PROFILES` in *Set overrides*.
3. *Connect* → *HTTP 8188*: the Henge setup screen shows each model's download progress (about 10 minutes on
   RunPod's network) and opens the studio when the models are ready.
4. **Stop or terminate the pod**. The volume keeps the files; the same volume serves the endpoint below and
   any later pod.

### Datacenter

The volume and the endpoint must be in the same datacenter, so choose it by the GPU you want for the
endpoint: `runpodctl datacenter list` shows which GPUs each one has in stock. Henge needs a CUDA 13
driver. The RTX 5090 (32 GB) is the default and costs about half of an RTX PRO 6000 (96 GB) per second; the
endpoint lists the 5090 first and falls back to the RTX PRO 6000 only when no 5090 is free. Workers run
ComfyUI with `--fast-disk`, so the ~56 GB of RAM of a 5090 worker is enough.

## 2. Create the endpoint

```sh
VOLUME_ID=<volume id> scripts/runpod_serverless.sh
```

This creates:

- a **serverless template** in your account: the full Henge image (`ghcr.io/alisson-anjos/henge:latest`)
  with `HENGE_ROLE=worker` and `HENGE_COMFY_ARGS=--fast-disk`. RunPod does not allow public serverless templates,
  so there is no shared one to pick; in the console, *Serverless → New Endpoint → Import from Docker Registry*
  with that image and those variables is the same;
- an **endpoint**: `GPU` (default RTX 5090), 0 to `WORKERS_MAX` workers (default 2),
  `IDLE_TIMEOUT` seconds kept warm after a request (default 15), execution timeout 1 h, with the
  volume attached.

`runpodctl` sets one GPU type. To add the RTX PRO 6000 as a fallback behind the 5090, edit the endpoint in the
RunPod console (*Serverless → endpoint → Edit*, GPU list in priority order). Idle workers are billed: keep the
idle timeout short.

It prints the endpoint id. To change settings later (new image, more workers):
`ENDPOINT_ID=<id> TEMPLATE_ID=<id> scripts/runpod_serverless.sh`.

### Or in the RunPod console

RunPod does not allow public serverless templates, so the endpoint is created from the image:

1. *Serverless* → *New endpoint* → *Deploy from a Docker image*.
2. Container image `ghcr.io/alisson-anjos/henge:latest`; *Container configuration* → container disk 40 GB;
   *Environment variables* → `HENGE_ROLE=worker` and `HENGE_COMFY_ARGS=--fast-disk` → *Next*.
3. Name the endpoint, tick the **32 GB** (RTX 5090) and **96 GB** (RTX PRO 6000) GPU tiers, max workers 2.
4. *Advanced settings*: idle timeout 15 s, execution timeout 3600 s, *Network volumes* → your volume, *Allowed
   CUDA versions* → 13.0 and newer → *Deploy*.
5. On the endpoint page, copy the **Endpoint ID** and, under *Quick start*, *Generate key*: the API key is shown
   only once (or create one in *Settings → API Keys*).

## 3. Run the UI on your computer

The UI and its bridge need no GPU. Run them with Docker (A) or directly with Node and Python (B).

### A. With Docker

```sh
docker run -p 8188:8188 -v henge-state:/state \
  -e HENGE_BACKEND=runpod \
  -e RUNPOD_ENDPOINT_ID=<endpoint id> \
  -e RUNPOD_API_KEY=<your RunPod API key> \
  ghcr.io/alisson-anjos/henge-ui:latest
```

Open http://localhost:8188 and use Henge as usual. The `henge-state` volume keeps your job
history between restarts. The API key stays on your machine: only the bridge uses it.

On Windows this is the simplest way: install Docker Desktop and run the same command in PowerShell
(write it on one line, or end the lines with a backtick instead of `\`).

### B. Without Docker

Needs Node 22.6+, Python 3.10+ and `ffmpeg` on the `PATH`.

**Linux, macOS or WSL:**

```sh
git clone https://github.com/alisson-anjos/Henge.git && cd Henge
npm ci && npm run build
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
```

Create `.env.local` in the repository root (both the bridge and the UI read it):

```dotenv
HENGE_BACKEND=runpod
RUNPOD_ENDPOINT_ID=<endpoint id>
RUNPOD_API_KEY=<your RunPod API key>
HENGE_DATA_DIR=/absolute/path/to/henge-data
# HENGE_PASSWORD=choose-one   # optional, see the README
```

Start, check and stop:

```sh
PYTHON=.venv/bin/python scripts/local_stack.sh start
scripts/local_stack.sh status
scripts/local_stack.sh stop
```

Open http://localhost:8188. Logs are in `.runtime/logs/`. If 8188 or 8766 are taken (another Henge), pick other
ports: `UI_PORT=8288 BRIDGE_PORT=8866 PYTHON=.venv/bin/python scripts/local_stack.sh start` (use the same
variables for `status` and `stop`).

You can leave `RUNPOD_API_KEY` out of `.env.local` and paste it in the first-run screen instead (*RunPod
Serverless* → API key → *Test connection* → *Save and use*); the bridge stores it and never sends it back to the
browser.

**Windows (PowerShell):** install the tools with
`winget install OpenJS.NodeJS.LTS Python.Python.3.12 Gyan.FFmpeg Git.Git`, open a new PowerShell, then:

```powershell
git clone https://github.com/alisson-anjos/Henge.git; cd Henge
npm ci; npm run build
py -3.12 -m venv .venv; .venv\Scripts\pip install -r backend\requirements.txt
```

Create `.env.local` as above (use a Windows path such as `HENGE_DATA_DIR=C:/henge-data`), then start the
bridge and the UI in two PowerShell windows, both from the `Henge` folder:

```powershell
cd backend; ..\.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8766 --env-file ..\.env.local
```

```powershell
npx next start --hostname 127.0.0.1 --port 8188
```

Close both windows to stop.

### Sharing the UI

To let someone else use it, open a tunnel to port 8188, e.g.
`cloudflared tunnel --url http://localhost:8188`, and turn on a login first (🔓 in the top bar, or `HENGE_PASSWORD`):
every job runs on your endpoint and is billed to your account. The worker itself needs no extra password: RunPod only
accepts requests signed with your API key, and that key lives only in the bridge's environment, never in the browser.

## How a job runs

Every stage of a job is one request to the endpoint:

1. **Plan**: the VLM describes the pictures and writes the prompt (one request per question).
2. **Reference preparation**: background removal, and FLUX Klein when enabled.
3. **Each shot**: one H3 render. The bridge cuts the guide into shots, sends each one with its
   references, and joins the results.

The bridge does the cheap work locally (ffmpeg, planning logic, joining, comparisons). Workers
only run ComfyUI graphs. Between stages of the same job the worker is usually still warm, thanks
to the idle timeout.

Measured on an RTX PRO 6000 (480p, 3 s Character Swap, 8 steps):

| | Time |
|---|---|
| Cold start (worker start, ComfyUI, model listing) | ~170 s |
| Whole job with a warm worker (plan + background removal + render) | ~250 s |

## Limits

- **Media size: no limit.** Small media travel inside the requests. When a request would pass
  RunPod's ~10 MB cap, the bridge writes the media to the endpoint's network volume in 6 MB chunks
  (small `put` requests that any worker can serve, since they all mount the volume) and reads large
  results back the same way. Only the endpoint and its volume are used. Transfer files older than
  two days are removed by the workers.
- **No live preview.** The UI shows the stage and sampler steps, not the intermediate frames.
- **Model list.** The UI learns which models the worker has from its first reply. Before that,
  every mode is shown as available.
- **Cold start.** The first request after an idle period waits for a worker to start. Set
  `--workers-min 1` on the endpoint to keep one always warm (billed continuously).

## Costs

- **Network volume**: billed per GB per month while it exists (180 GB volume).
- **Workers**: billed per second while running, including the idle timeout after each request.
- **Fill pod**: a few minutes of GPU time, once.

Remove everything when you no longer need it:

```sh
runpodctl serverless delete <endpoint id>
runpodctl template delete <template id>
runpodctl network-volume delete <volume id>
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Job waits a long time in "Waiting for a serverless worker" | Cold start, or no GPU of that type free in the datacenter. Check `runpodctl serverless get <id>`; recreate the endpoint with another `GPU`. |
| `Serverless job failed: ... out of memory` | GPU too small, or `HENGE_COMFY_ARGS` set to `--highvram`/`--gpu-only` on the template. Leave it unset. |
| Worker log: `no models at /runpod-volume/henge/models` | The volume is empty or not attached: run `scripts/runpod_volume.sh` and check the endpoint's network volume. |
| Refiner + LMS is visible but disabled | Update the worker image, top up the volume with `PROFILES=regenerate`, then run a short Henge job with another method to refresh the bridge inventory. See the upgrade steps below. |
| A mode shows "not installed" | The worker's model list does not have it: top up the volume with `VOLUME_ID=<id> scripts/runpod_volume.sh`. |

Worker logs: RunPod console → *Serverless* → your endpoint → *Workers* → *Logs*.

## Testing the worker locally

The worker can run against a local ComfyUI with RunPod's local API server, and the bridge can talk
to it like a real endpoint:

```sh
# worker: simulates /run and /status on :8010 (needs `pip install runpod`)
COMFY_ROOT=/path/to/ComfyUI COMFY_BASE_URL=http://127.0.0.1:8189 \
  python docker/worker_handler.py --rp_serve_api --rp_api_port 8010

# bridge in serverless mode, pointed at it
HENGE_BACKEND=runpod RUNPOD_ENDPOINT_ID=local RUNPOD_API_BASE=http://127.0.0.1:8010 \
  python -m uvicorn server:app --port 8767   # from backend/
```

## Reference

| Variable | Where | Meaning |
|---|---|---|
| `HENGE_BACKEND=runpod` | UI image | run graphs on a serverless endpoint instead of a ComfyUI URL |
| `RUNPOD_ENDPOINT_ID` | UI image | endpoint id |
| `RUNPOD_API_KEY` | UI image | RunPod API key |
| `RUNPOD_API_BASE` | UI image | override the API URL (local testing) |
| `HENGE_PASSWORD` | UI image | optional UI password (user `HENGE_USER`, default `henge`); unset means open |
| `HENGE_LIKENESS_FILTER` | UI image | `off` (default), `warn` or `block` for reference pictures of real public figures |
| `HENGE_ROLE` | image | `all` (default), `worker` or `ui` |
| `HENGE_WORKSPACE` | worker | volume mount, default `/runpod-volume` |
| `HENGE_COMFY_ARGS` | worker | extra ComfyUI flags; the endpoint script sets `--fast-disk` (keeps weights out of pinned RAM) |

Code: `docker/worker_handler.py` (worker), `backend/runpod_backend.py` (bridge side),
`docker/entrypoint.py` (roles), `scripts/runpod_volume.sh` and `scripts/runpod_serverless.sh`.

## Enable Refiner + LMS on an existing endpoint

The Sharpness dropdown selects **Open-H3 Refiner + LMS** by default, but disables execution until
its native nodes and all five weights appear in the worker inventory. Updating the UI alone is not enough.
The `regenerate` model profile is optional and is not included in the default profile list.

1. Wait for the GitHub **Docker image** workflow to publish the updated full `henge` image.
2. Top up the **same network volume attached to the endpoint**, using a temporary fill pod:

   ```sh
   VOLUME_ID=<existing-volume-id> DATACENTER=<volume-datacenter> \
     PROFILES=regenerate IMAGE=ghcr.io/alisson-anjos/henge:latest \
     scripts/runpod_volume.sh
   ```

   Existing files are reused; other profiles already on the volume are kept. This downloads the common
   dependencies plus DMAD, LMS, the rank-16 refiner and the native latent upscaler. It reuses Ref2VA;
   **FL2VA is not required**. The temporary fill pod consumes GPU time and is deleted on success.
   Alternatively, use the console fill-pod procedure above with the existing volume and
   `HENGE_MODEL_PROFILES=regenerate`, then terminate that temporary pod after downloads complete.
3. After active jobs finish, update the endpoint's worker template to the newly published
   `ghcr.io/alisson-anjos/henge:latest` (or its `sha-<commit>` tag). Preserve the attached volume,
   `HENGE_ROLE=worker` and existing ComfyUI settings. Recycle old workers to load the new image.
   To use the repository's update script with its standard settings:

   ```sh
   ENDPOINT_ID=<endpoint-id> TEMPLATE_ID=<worker-template-id> \
     IMAGE=ghcr.io/alisson-anjos/henge:latest scripts/runpod_serverless.sh
   ```

   The script drains workers by scaling to zero and then restores its worker limit. Do not run it
   during an active generation. It sets the standard worker environment rather than preserving
   custom template environment overrides.
4. Run a short job through Henge using an already available method, such as Sharpness with **H3**.
   The worker response refreshes the **bridge's cached inventory**. Reload the Studio page afterwards.
   Routine health checks and **Test connection** do not wake a worker to refresh that inventory.
5. Select **Open-H3 Refiner + LMS**, choose **1080p or 2K**, and review the optional refiner prompt
   in the main creation panel. An empty prompt requests an automatic scene description.

**Setting `HENGE_MODEL_PROFILES=regenerate` only on a Serverless worker does not download anything.**
The download profile belongs on the fill pod; workers only read the populated volume.
The bridge does not need reinstalling. If the UI is on Render, update `henge-ui` separately;
see [RENDER.md](RENDER.md).

For required filenames and native nodes, see [Open-H3 setup and limits](open-h3-regenerate.md).
If the option remains disabled, inspect `regenerate.missing_nodes` and `regenerate.missing_models`
in the bridge's `/health` response (through the UI: `/api/backend/health`). An old inventory can report
missing dependencies even after the volume has been updated.

## Bridge restarts between shots

“The bridge restarted during this job” is written when the UI/bridge starts and finds an unfinished
job. It does not by itself establish a GPU failure: compare the saved RunPod request status with
Render's service logs/events. A completed worker request followed by a bridge restart can mean the
failure happened while downloading, joining or exporting its result. Check Render for OOM/SIGKILL
and deployment/restart events before assigning a cause.

Shot joining now reads only the overlapping frames as thumbnails (longest side at most 256 pixels)
to select the hard seam. Colours are preserved; no colour matching is applied. FFmpeg streams the
full-resolution frames. The join
keeps the existing frame counts, removes the overlap once, and uses no crossfade. It verifies both
temporary output files before replacing the original pieces. This avoids keeping entire RGB shots
and several full-video float copies in the bridge's RAM.

This fix belongs to the **Render UI/bridge image**, not the RunPod GPU worker. Deploy the updated UI
image after active jobs finish. Updating only the RunPod template does not change bridge-side joining.
A Retry reuses an existing plan but can submit render graphs again; do not assume every completed
GPU request will be recovered automatically after a bridge restart.

## Pure temporal windows

The optional temporal-processing control requires the updated UI/bridge and a worker image containing
`HengeH3PureWindows`. No extra model downloads or profiles are needed. Update/recycle workers after active
jobs finish and refresh the bridge inventory as above. `temporal_windows_ready` in `/health` reports node
availability. See [controls, conditioning and validation limits](temporal-windows.md).
