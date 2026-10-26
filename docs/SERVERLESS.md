# Henge on RunPod Serverless

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
| Setup | template, one click | volume + endpoint, two scripts |

## Requirements

- A RunPod account with credit and an API key (*Settings → API Keys*).
- [`runpodctl`](https://github.com/runpod/runpodctl) configured (`runpodctl doctor`).
- A Hugging Face token with read access while the motion LoRAs are private, stored as the RunPod
  secret `hf_token` (*Settings → Secrets*); the volume fill pod reads it.
- Docker on your computer for the UI.

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
| `motion10500`, `motion4500` | Motion Transfer | private LoRAs: need the `hf_token` secret |
| `solar` | Motion Transfer (Solar) | ~25 GB |
| `ffp` | Motion Transfer FFP: propagate an edited first frame (VFX Edit FFP + SolarRenderer 0.5, fro dyn99) | 220 MB, private: needs the `hf_token` secret |
| `headswap` | Head Swap | |
| `sharpness` | Sharpness (H3 + Little More Sharpness LoRA; 2K/4K with the H3 or NVIDIA RTX upscaler) | ~1 GB (LoRA + H3 latent upscaler), private LoRA: needs the `hf_token` secret |
| `omniref` | OmniRef base | +22 GB |
| `fibo` | Reference adaptation (FIBO 2 edit: animal to human-compatible pose, first-frame edits) | ~14 GB |
| `sam2d`, `sam3d` | Subject marks: SAM 3.1 tracking (2D colors, Mask, the assistant's find people) and SAM 3D Body + MoGe (3D) | ~4 GB |

The default, every profile above, needs roughly 125–135 GB: create the volume with 180 GB (`VOLUME_GB=180`).

### Option A: script

```sh
scripts/runpod_volume.sh                                       # new 180 GB volume, every profile
PROFILES=character,solar scripts/runpod_volume.sh              # only some profiles
VOLUME_ID=<id> scripts/runpod_volume.sh                        # top up an existing volume
```

- Creates the network volume (`DATACENTER`, default `EU-RO-1`; `VOLUME_GB`, default 180), unless
  `VOLUME_ID` is given.
- Starts the fill pod from `ghcr.io/alisson-anjos/henge:runpod-template` on the first GPU in stock
  (`FILL_GPUS`), with `HENGE_MODEL_PROFILES=$PROFILES` and `HF_TOKEN` from your RunPod secret `hf_token`.
- Prints the download progress every minute and deletes the pod when every model is installed.

A top-up skips the files that are already there: use it after an interrupted download or to add profiles.
If a download fails (usually the private LoRAs without a valid `hf_token`), the pod is kept so you can
open its setup screen; delete it with `runpodctl pod delete <pod id>` when done.

### Option B: RunPod console

1. *Storage* → *New Network Volume*: pick the datacenter (see below) and 180 GB.
2. *Pods* → *Deploy*, in the same datacenter, any GPU with CUDA 13 (it only downloads). Under the network
   volume, select the new volume. Use the image `ghcr.io/alisson-anjos/henge:runpod-template`, mount path
   `/workspace`, HTTP port `8188`, and the environment variables
   `HENGE_MODEL_PROFILES=<profiles>` and `HF_TOKEN={{ RUNPOD_SECRET_hf_token }}`.
3. Open the pod's port 8188: the Henge setup screen shows each model's download progress.
4. When every model is installed and the pod log says `model downloads finished`, **terminate the pod**.
   The volume keeps the files.

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

- a **serverless template**: the full Henge image (`ghcr.io/alisson-anjos/henge:runpod-template`)
  with `HENGE_ROLE=worker`;
- an **endpoint**: `GPU` (default RTX 5090), 0 to `WORKERS_MAX` workers (default 2),
  `IDLE_TIMEOUT` seconds kept warm after a request (default 15), execution timeout 1 h, with the
  volume attached.

`runpodctl` sets one GPU type. To add the RTX PRO 6000 as a fallback behind the 5090, edit the endpoint in the
RunPod console (*Serverless → endpoint → Edit*, GPU list in priority order). Idle workers are billed: keep the
idle timeout short.

It prints the endpoint id. To change settings later (new image, more workers):
`ENDPOINT_ID=<id> TEMPLATE_ID=<id> scripts/runpod_serverless.sh`.

## 3. Run the UI on your computer

The UI and its bridge need no GPU. Run them with Docker (A) or directly with Node and Python (B).

### A. With Docker

```sh
docker run -p 8188:8188 -v henge-state:/state \
  -e HENGE_BACKEND=runpod \
  -e RUNPOD_ENDPOINT_ID=<endpoint id> \
  -e RUNPOD_API_KEY=<your RunPod API key> \
  ghcr.io/alisson-anjos/henge-ui:runpod-template
```

Open http://localhost:8188 and use Henge as usual. The `henge-state` volume keeps your job
history between restarts. The API key stays on your machine: only the bridge uses it.

On Windows this is the simplest way: install Docker Desktop and run the same command in PowerShell
(write it on one line, or end the lines with a backtick instead of `\`).

### B. Without Docker

Needs Node 22.6+, Python 3.10+ and `ffmpeg` on the `PATH`.

**Linux, macOS or WSL:**

```sh
git clone -b runpod-template https://github.com/alisson-anjos/Henge.git && cd Henge
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

Open http://localhost:8188. Logs are in `.runtime/logs/`.

**Windows (PowerShell):** install the tools with
`winget install OpenJS.NodeJS.LTS Python.Python.3.12 Gyan.FFmpeg Git.Git`, open a new PowerShell, then:

```powershell
git clone -b runpod-template https://github.com/alisson-anjos/Henge.git; cd Henge
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
`cloudflared tunnel --url http://localhost:8188`, and set `HENGE_PASSWORD` first: every job runs on your
endpoint and is billed to your account.

## How a job runs

Every stage of a job is one request to the endpoint:

1. **Plan**: the VLM describes the pictures and writes the prompt (one request per question).
2. **Reference preparation**: background removal, and FIBO when enabled.
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
| `HENGE_ROLE` | image | `all` (default), `worker` or `ui` |
| `HENGE_WORKSPACE` | worker | volume mount, default `/runpod-volume` |
| `HENGE_COMFY_ARGS` | worker | extra ComfyUI flags; the endpoint script sets `--fast-disk` (keeps weights out of pinned RAM) |

Code: `docker/worker_handler.py` (worker), `backend/runpod_backend.py` (bridge side),
`docker/entrypoint.py` (roles), `scripts/runpod_volume.sh` and `scripts/runpod_serverless.sh`.
