# Deploying Henge on RunPod: instructions for an AI agent

Give this file to a coding agent (Claude Code, Codex, Cursor and similar) together with the task, for example:
"Deploy Henge on RunPod Serverless following docs/AGENT_DEPLOY.md". It is written as steps an agent can run
and check. A human can follow it the same way.

## Rules

- **Ask the user before anything that costs money or is hard to undo**: creating a network volume, pod,
  template or endpoint, scaling workers up, deleting any RunPod resource. Say what it is and its cost
  (volume: per GB per month; pods and workers: per second of GPU).
- **Never print secrets.** Read the RunPod API key from `RUNPOD_API_KEY` or `~/.runpod/config.toml`
  (`apikey`), and the Hugging Face token from the RunPod secret `hf_token`. Do not echo them, put them in
  command output, commit them or paste them into logs.
- **Media go only through the endpoint and its network volume.** Do not add S3, R2 or any other storage.
- Do not change the GPU flags in `HENGE_COMFY_ARGS` to `--highvram` or `--gpu-only`: they run out of memory.
- Do not restart the user's running bridge or UI while `GET http://127.0.0.1:8766/jobs` lists a job that is
  `running` or `queued_*`.
- Report what you did and what you checked, with the ids you created. If a step failed, say so.

## What you are deploying

| Piece | Where | Image |
|---|---|---|
| Web UI (port 8188) and bridge (port 8766) | the user's computer (option C) or the pod (option B) | `ghcr.io/alisson-anjos/henge-ui` / `ghcr.io/alisson-anjos/henge` |
| ComfyUI with the Henge and BFS nodes | the pod (B) or the serverless workers (C) | `ghcr.io/alisson-anjos/henge` |
| Models (~125 GB with every profile) | the pod volume (B) or a RunPod network volume (C) | downloaded, never in an image |

Images are built by GitHub Actions on every push and tagged `latest` (the main branch), with the branch name and
`sha-<commit>`. Use a `sha-` tag for the serverless template so a later build does not change running workers.

## 0. Prerequisites (check, do not assume)

If the user has no RunPod account, give them this sign-up link: https://runpod.io?ref=8t518hht


```sh
runpodctl doctor                 # installed and configured with an API key
runpodctl datacenter list        # which GPUs each datacenter has in stock
```

Ask the user for:

- which option: **B** (one pod, everything inside) or **C** (UI on their computer, GPU on Serverless);
- whether the RunPod secret `hf_token` exists (*Settings → Secrets*). Without it only the experimental Motion
  Transfer FFP model is skipped (every other model is public);
- the datacenter (default `EU-RO-1`; it must have RTX 5090 in stock) and which model profiles they need
  (default: all of `character,motion,headswap,sharpness,omniref,fibo,klein,sam2d,sam3d,audio`).

## Option B: one pod

1. Use the published Henge pod template `mnxax277c8` (deploy link for the user: https://console.runpod.io/deploy?template=mnxax277c8&ref=8t518hht; with runpodctl,
   `--template-id mnxax277c8`). Only if the user wants their own: `scripts/runpod_template.sh` (read it first; `TEMPLATE_ID=<id>`
   updates an existing template). Settings: image `ghcr.io/alisson-anjos/henge:latest`, container
   disk 30 GB, volume 180 GB at `/workspace`, HTTP port 8188 (add `HF_TOKEN={{ RUNPOD_SECRET_hf_token }}` only for the private `ffp` profile).
2. With the user's approval, deploy a pod from it on a GPU with a CUDA 13 driver (RTX 5090 or larger).
3. Check: the pod log shows `model downloads finished`, then
   `curl -s https://<pod id>-8188.proxy.runpod.net/api/backend/health` returns `"online": true`.
4. Give the user the URL `https://<pod id>-8188.proxy.runpod.net`. If it will be shared, set `HENGE_PASSWORD`
   on the template first (or tell the user to turn on a login from the 🔓 button in the top bar). With a login on,
   the health check needs it too: `curl -u henge:<password> …`.

## Option C: Serverless

1. **Network volume with the models** (once, about 10–30 min; read `scripts/runpod_volume.sh` first):

   ```sh
   DATACENTER=EU-RO-1 VOLUME_GB=180 scripts/runpod_volume.sh
   ```

   It prints the volume id, starts a temporary fill pod, prints progress every minute and deletes the pod when
   every model is installed. Check the last line says `ready`. If it says `failed <ids>`, the pod is kept:
   report the ids (usually a missing `hf_token`) and ask before deleting it (`runpodctl pod delete <pod id>`).
   To add profiles later: `VOLUME_ID=<id> PROFILES=<list> scripts/runpod_volume.sh`.

2. **Endpoint** (read `scripts/runpod_serverless.sh` first):

   ```sh
   VOLUME_ID=<volume id> scripts/runpod_serverless.sh
   ```

   It creates a worker template in the user's account from the public image `ghcr.io/alisson-anjos/henge:latest`
   (`HENGE_ROLE=worker`, `HENGE_COMFY_ARGS=--fast-disk`; RunPod does not allow public serverless templates) and the
   endpoint: RTX 5090, 0–2 workers, idle timeout 15 s, execution timeout 1 h. It prints the endpoint id. To add the RTX PRO 6000
   as a fallback behind the 5090, edit the endpoint's GPU list in the RunPod console (5090 first).

3. **UI on the user's computer**:

   ```sh
   docker run -d --name henge -p 8188:8188 -v henge-state:/state -e HENGE_BACKEND=runpod \
     -e RUNPOD_ENDPOINT_ID=<endpoint id> -e RUNPOD_API_KEY="$RUNPOD_API_KEY" \
     ghcr.io/alisson-anjos/henge-ui:latest
   ```

   Without Docker: clone the repository, `npm ci && npm run build`, install `backend/requirements.txt` in a
   Python 3.10+ venv, write `.env.local` with `HENGE_BACKEND=runpod`, `RUNPOD_ENDPOINT_ID`, `RUNPOD_API_KEY`
   and `HENGE_DATA_DIR`, then `PYTHON=.venv/bin/python scripts/local_stack.sh start`.

4. **Check**:

   ```sh
   curl -s http://127.0.0.1:8188/api/backend/health    # "online": true
   curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" https://api.runpod.ai/v2/<endpoint id>/health
   ```

   The first job waits for a cold start (1–3 min). The model list in the UI is learned from the first finished
   request; before that every mode shows as available.

## Updating the workers to a new image

After a push, wait for the GitHub Actions run to finish (`gh run list --branch main`), then:

```sh
ENDPOINT_ID=<id> TEMPLATE_ID=<id> IMAGE=ghcr.io/alisson-anjos/henge:sha-<commit> scripts/runpod_serverless.sh
```

It scales the endpoint to zero, waits until the old workers are gone and scales it back. Ask first if a job is
running: it would be interrupted.

## Cleaning up (only when the user asks)

```sh
runpodctl serverless delete <endpoint id>
runpodctl template delete <template id>
runpodctl network-volume delete <volume id>     # deletes the models; next time they download again
```

## Troubleshooting

| Symptom | What to do |
|---|---|
| A job waits long in "Waiting for a serverless worker" | No RTX 5090 free in the datacenter. Check `runpodctl datacenter list`; add a fallback GPU or wait. |
| `ComfyUI progress connection closed`, worker exit code -9 | Out of RAM. Check the template has `HENGE_COMFY_ARGS=--fast-disk`. |
| `RunPod /status/... HTTP 500` | A RunPod API hiccup; the bridge retries for about 3 minutes. If it persists, check RunPod's status page. |
| A mode shows "not installed" | Its models are not on the volume: top up with `VOLUME_ID=<id> PROFILES=<profile> scripts/runpod_volume.sh`. |
| `invalid api key` | The key in `~/.runpod/config.toml` or `RUNPOD_API_KEY` is wrong or revoked; ask the user for a new one. |

More detail: [SERVERLESS.md](SERVERLESS.md), [RUNPOD.md](RUNPOD.md).
