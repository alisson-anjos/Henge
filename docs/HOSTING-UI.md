# Hosting only the UI

Optional. With option C in the README the GPU runs on RunPod Serverless, so the UI and bridge need no GPU and can
live on any host that runs a Docker image. This page lists what the image needs and a few places to run it.

## What the `henge-ui` image needs

| | |
| --- | --- |
| Image | `ghcr.io/alisson-anjos/henge-ui:latest` (or a pinned `:sha-<commit>`) |
| Port | `8188` (HTTP) |
| Persistent disk | mounted at `/state`: jobs, results and history. Without it, a restart loses them |
| Variables | `HENGE_BACKEND=runpod`, `RUNPOD_ENDPOINT_ID`, `RUNPOD_API_KEY` |
| Login | set `HENGE_PASSWORD` (user `HENGE_USER`, default `henge`) on any public address |
| Always on | the bridge runs the jobs in its own process: an instance that sleeps or scales to zero stops the running job |
| RAM | the bridge joins shots and builds comparisons with FFmpeg; long 2K jobs need more than a minimal instance |

Optional: `VLM_API_KEY`/`VLM_CHAT_URL`/`VLM_MODEL`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` for automatic prompts
and the assistant (they can also be set in the UI's settings).

Redeploying or restarting restarts the bridge: wait until no job is running.

## Render

See [Hosting the UI on Render](RENDER.md).

## Your own server (VPS) with Docker

Any Linux VM with Docker:

```sh
docker run -d --name henge-ui --restart unless-stopped -p 8188:8188 -v henge-state:/state \
  -e HENGE_BACKEND=runpod -e RUNPOD_ENDPOINT_ID=<endpoint id> -e RUNPOD_API_KEY=<api key> \
  -e HENGE_PASSWORD=<password> ghcr.io/alisson-anjos/henge-ui:latest
```

Put a reverse proxy with HTTPS in front of port 8188 (for example Caddy: `reverse_proxy 127.0.0.1:8188`).
To update: `docker pull ghcr.io/alisson-anjos/henge-ui:latest`, then remove and start the container again (the
`henge-state` volume keeps the jobs).

## Fly.io

`fly.toml`:

```toml
app = "<app name>"

[build]
  image = "ghcr.io/alisson-anjos/henge-ui:latest"

[http_service]
  internal_port = 8188
  force_https = true
  auto_stop_machines = "off"   # a stopped machine would stop the running job
  min_machines_running = 1

[mounts]
  source = "henge_state"
  destination = "/state"
```

Create the volume (`fly volumes create henge_state`), set the secrets (`fly secrets set HENGE_BACKEND=runpod
RUNPOD_ENDPOINT_ID=... RUNPOD_API_KEY=... HENGE_PASSWORD=...`) and run `fly deploy`. Run `fly deploy` again to
pick up a new `latest` image.

## Railway

New project → **Deploy a Docker image** → `ghcr.io/alisson-anjos/henge-ui:latest`. Add a volume mounted at
`/state`, set the variables above, and expose port `8188` as the public HTTP port. Redeploy the service to pick up
a new `latest` image.

## Other hosts

Any service that runs a Docker image with a persistent volume and keeps the instance running works the same way.
Avoid hosts that only offer an ephemeral filesystem, sleep idle instances or throttle CPU outside HTTP requests.
