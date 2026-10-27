# AI-guided installation

Let a coding agent (Claude Code, Codex, Cursor, Gemini CLI…) install Henge for you. Open the agent in an empty
folder and paste this:

```text
Install Henge (https://github.com/alisson-anjos/Henge) for me by following
https://github.com/alisson-anjos/Henge/blob/runpod-template/docs/AI_GUIDED_INSTALL.md.
Read that file first, check my machine, then ask me which option I want before installing anything.
```

The rest of this file is written for the agent. A person can follow it the same way.

---

## Rules for the agent

- **Check, don't assume.** Run the checks in step 1 and report what you found before choosing.
- **Ask before** anything that costs money (RunPod volumes, pods, endpoints), downloads more than a few GB,
  or changes an existing ComfyUI (adding custom nodes, pip installs into its environment). Say the size or cost.
- **Never print secrets** (Hugging Face token, RunPod or Comfy API keys). Put them in `.env.local` or the
  settings screen; don't echo them, log them or commit them.
- Don't run two ComfyUI servers on the same port, and don't change ComfyUI's GPU flags to `--highvram` or
  `--gpu-only` (out of memory with H3).
- At the end, report what you installed, where, how to start and stop it, and anything that failed.

## 1. Check the machine

```sh
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv   # GPU, VRAM, driver
free -g; df -h .                                                        # RAM and free disk
node --version; python3 --version; ffmpeg -version | head -1; git --version
```

On Windows run these in PowerShell (use `Get-PSDrive` for disk). Also ask the user whether they already have
ComfyUI and where, and whether they have a RunPod account.

## 2. Choose an option with the user

| Option | Pick it when | Needs |
|---|---|---|
| **A. Local** | NVIDIA GPU with 32 GB VRAM (RTX 5090 or larger), 64 GB RAM, ~130 GB free disk | driver 580+ (CUDA 13), Node 22.6+, Python 3.10+, ffmpeg |
| **B. RunPod pod** | no suitable GPU, long sessions | RunPod account with credit |
| **C. Local UI + RunPod Serverless** | no suitable GPU, occasional use, pay per second | RunPod account, `runpodctl`; Docker or Node+Python locally |

Models are about 125 GB with every profile; fewer profiles download less (step A2). The motion LoRAs need a
Hugging Face token with read access (`HF_TOKEN`); ask the user for one if they want Motion Transfer.

## A. Local

Follow [README → A. Local](../README.md#a-local-with-your-own-comfyui); details in [RUN_LOCAL.md](RUN_LOCAL.md).
Steps and checks:

1. **ComfyUI.** If the user has none, install it from https://github.com/comfyanonymous/ComfyUI with PyTorch
   for CUDA 13 in its own venv. Remember that venv's Python as `COMFY_PY`.
2. **Henge, nodes, models.**
   ```sh
   git clone https://github.com/alisson-anjos/Henge.git && cd Henge && npm ci && npm run build
   ln -s "$PWD/backend/comfy_nodes/henge" <ComfyUI>/custom_nodes/henge        # Windows: copy the folder
   git clone https://github.com/alisson-anjos/ComfyUI-BFSNodes.git <ComfyUI>/custom_nodes/bfsnodes
   $COMFY_PY -m pip install -r <ComfyUI>/custom_nodes/bfsnodes/requirements.txt -r backend/requirements.txt
   HF_TOKEN=… $COMFY_PY scripts/download_models.py --manifest config/model-repos.example.json \
     --models-dir <ComfyUI>/models --profiles character,headswap,sharpness --dry-run   # show sizes, then without --dry-run
   ```
   Ask which modes the user wants; profiles: `character` (Character Swap), `motion10500`, `motion4500` (Motion
   Transfer), `headswap`, `sharpness`, `fibo`, `omniref`, `sam2d`, `sam3d`.
3. **Start ComfyUI** on 8189: `$COMFY_PY main.py --listen 127.0.0.1 --port 8189 --preview-method taesd --fast-disk`.
   Check `curl -s http://127.0.0.1:8189/object_info/HengeFindPeople` is not `{}` (the Henge nodes loaded).
4. **`.env.local`** in Henge: `COMFY_BASE_URL=http://127.0.0.1:8189`, `COMFY_ROOT=<ComfyUI>`,
   `HENGE_DATA_DIR=<a folder for jobs>`.
5. **Start Henge**: `PYTHON=$COMFY_PY scripts/local_stack.sh start` (Windows: the two commands in
   [RUN_LOCAL.md](RUN_LOCAL.md#4-start-the-job-bridge)).

## B. RunPod pod

Follow [AGENT_DEPLOY.md → Option B](AGENT_DEPLOY.md#option-b-one-pod). The user can also do it by hand from
[RUNPOD.md](RUNPOD.md).

## C. Local UI + RunPod Serverless

Follow [AGENT_DEPLOY.md → Option C](AGENT_DEPLOY.md#option-c-serverless): network volume with the models,
endpoint, then the UI on the user's computer. With Henge already running locally, the endpoint can also be set
on screen: gear in the top bar → **Connection → RunPod Serverless** (endpoint ID and API key, **Test** then
**Save and use**).

## Other backends (optional)

The same **Connection** screen offers **Comfy API · SDK**: Henge starts `comfy-api-proxy` in front of the user's
ComfyUI and talks to it with the official Comfy SDK, or uses a Comfy API URL / Comfy Cloud. Comfy Cloud must
have the Henge and BFS nodes and the models, so it is not a full install path yet.

## 3. Verify

```sh
curl -s http://127.0.0.1:8188/api/backend/health      # "online": true, and the models the user chose "available"
```

Open http://127.0.0.1:8188. On the first visit a short setup wizard opens (connection, assistant, login); every
step can be skipped. Then run one short test with the user: Character Swap, a 3–5 s clip, one picture, 480p.

## 4. Optional extras

- **Studio assistant**: gear → Assistant (Claude, OpenAI or a local model in LM Studio / Ollama).
- **Use the agent itself instead of the assistant**: register the Henge MCP server, [MCP.md](MCP.md).
- **Login** before exposing Henge on a network: gear → Login, or `HENGE_PASSWORD`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Health says `ComfyUI does not answer` | ComfyUI not running on the address in **Connection**, or still loading (first CUDA start can take minutes). |
| A mode shows "not installed" | Its model profile is missing: run `download_models.py` with that profile. |
| "the Henge nodes are missing" when testing the connection | The `henge` / `bfsnodes` folders are not in `custom_nodes`, or ComfyUI was not restarted, or a node whitelist excludes them. |
| Out of memory | Close other GPU apps; keep 480p for the first tests; don't use `--highvram`. |
| Motion Transfer missing | No `HF_TOKEN` with access to the motion LoRAs when downloading. |
