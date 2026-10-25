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
  secret `hf_token` (used by the Henge pod template).
- Docker on your computer for the UI.

## 1. Put the models on a network volume (once)

```sh
scripts/runpod_volume.sh
```

- Creates a network volume (`DATACENTER`, default `EU-RO-1`; `VOLUME_GB`, default 150).
- Starts a temporary pod from the Henge pod template with the volume at `/workspace`. It downloads
  the `HENGE_MODEL_PROFILES` models exactly like a normal pod.
- Waits until every model is installed, then deletes the pod. The volume keeps the files.

To top up an existing volume (new models, or a download that was interrupted), run it with
`VOLUME_ID=<id>`. Files that are already there are skipped.

Choose the datacenter by the GPU you want for the endpoint: the volume and the endpoint must be in
the same datacenter. `runpodctl datacenter list` shows which GPUs each one has in stock. Henge
needs 80 GB or more of VRAM and a CUDA 13 driver: RTX PRO 6000 (96 GB), A100 80 GB, H100.

## 2. Create the endpoint

```sh
VOLUME_ID=<volume id> scripts/runpod_serverless.sh
```

This creates:

- a **serverless template**: the full Henge image (`ghcr.io/alisson-anjos/henge:runpod-template`)
  with `HENGE_ROLE=worker`;
- an **endpoint**: `GPU` (default RTX PRO 6000), 0 to `WORKERS_MAX` workers (default 2),
  `IDLE_TIMEOUT` seconds kept warm after a request (default 120), execution timeout 1 h, with the
  volume attached.

It prints the endpoint id. To change settings later (new image, more workers):
`ENDPOINT_ID=<id> TEMPLATE_ID=<id> scripts/runpod_serverless.sh`.

## 3. Run the UI on your computer

```sh
docker run -p 8188:8188 -v henge-state:/state \
  -e HENGE_BACKEND=runpod \
  -e RUNPOD_ENDPOINT_ID=<endpoint id> \
  -e RUNPOD_API_KEY=<your RunPod API key> \
  ghcr.io/alisson-anjos/henge-ui:runpod-template
```

Open http://localhost:8188 and use Henge as usual. The `henge-state` volume keeps your job
history between restarts. The API key stays on your machine: only the bridge uses it.

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

- **Network volume**: billed per GB per month while it exists (150 GB volume).
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
| `HENGE_ROLE` | image | `all` (default), `worker` or `ui` |
| `HENGE_WORKSPACE` | worker | volume mount, default `/runpod-volume` |
| `HENGE_COMFY_ARGS` | worker | extra ComfyUI flags; leave unset |

Code: `docker/worker_handler.py` (worker), `backend/runpod_backend.py` (bridge side),
`docker/entrypoint.py` (roles), `scripts/runpod_volume.sh` and `scripts/runpod_serverless.sh`.
