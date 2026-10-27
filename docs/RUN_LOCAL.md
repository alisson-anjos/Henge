# Run Henge locally

For the Docker build/start commands and automatic model downloads, use
[the Docker guide](../docker/README.md). For individual weight files and licenses,
use [models and downloads](models-and-downloads.md).

## Components and ports

| Service | Default URL | Purpose |
| --- | --- | --- |
| Web UI | http://127.0.0.1:8188 | Open this in the browser |
| Job bridge | http://127.0.0.1:8766 | Coordinates plans, files and generation |
| ComfyUI | http://127.0.0.1:8189 | Executes the generated workflows |

A working ComfyUI installation with a compatible NVIDIA/PyTorch environment is
required for generation. Also install Node.js 22.6+, Python dependencies and
FFmpeg/ffprobe on PATH. The native setup and Docker build are distinct: the full
container image has not been built/tested on the current pod.

## 1. Get the UI

```sh
git clone https://github.com/alisson-anjos/Henge.git
cd Henge
npm ci
cp .env.example .env.local
```

On PowerShell, use `Copy-Item .env.example .env.local`. Edit `.env.local`:

```dotenv
HENGE_BACKEND_URL=http://127.0.0.1:8766
COMFY_BASE_URL=http://127.0.0.1:8189
COMFY_ROOT=/absolute/path/to/ComfyUI
HENGE_DATA_DIR=/absolute/path/to/henge-data
HENGE_VLM_CLIP=qwen3.5_9b_w4a8_gptq.safetensors
```

`COMFY_ROOT` is optional: set it when ComfyUI runs on the same machine to get the
model download checklist; a remote ComfyUI only needs `COMFY_BASE_URL`, since the
bridge moves files through the ComfyUI API. Use your own absolute paths. On Windows, forward slashes such as
`C:/AI/ComfyUI` avoid backslash escaping. Keep `.env.local` out of Git.

## 2. Install the nodes and models

Install [BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes) into that
ComfyUI's `custom_nodes/bfsnodes`. Copy or symlink this repository's
`backend/comfy_nodes/henge` folder to `ComfyUI/custom_nodes/henge`.
Install BFSNodes' requirements using **the Python environment that runs ComfyUI**.
Restart ComfyUI after installing/updating either custom-node package.

Install the files from [the model guide](models-and-downloads.md), or configure
the manifest and run the downloader with your ComfyUI Python:

```sh
cp config/model-repos.example.json config/model-repos.json
python scripts/download_models.py --manifest config/model-repos.json --models-dir /absolute/path/to/ComfyUI/models --profiles character --dry-run
python scripts/download_models.py --manifest config/model-repos.json --models-dir /absolute/path/to/ComfyUI/models --profiles character
```

The `character`, `motion`, `headswap` and `sharpness` profiles download their published weights automatically. Only
the experimental `ffp` profile currently needs a Hugging Face token with access.
Optional FIBO, audio and SAM profiles
are documented in the Docker/model guides. The downloader never uploads models.

## 3. Start ComfyUI

From the ComfyUI folder, using its Python:

```sh
python main.py --listen 127.0.0.1 --port 8189 --lowvram --preview-method taesd
```

The H3 sampling preview needs `models/vae_approx/taeh3.safetensors`. The UI does
not need ComfyUI to be publicly exposed. If you use a custom-node whitelist,
include `henge` and `bfsnodes`. The Sharpness 2K/4K upscalers are henge nodes; the NVIDIA one also needs
`pip install nvidia-vfx` and an RTX GPU on the ComfyUI machine. Its files come with the `sharpness` model profile.

## 4. Start the job bridge

In a second terminal, from Henge, install/run using a Python environment with
the bridge dependencies. This can be the ComfyUI environment:

```sh
python -m pip install -r backend/requirements.txt
cd backend
python -m uvicorn server:app --host 127.0.0.1 --port 8766 --env-file ../.env.local
```

`requests`, `python-dotenv`, FastAPI, multipart uploads, aiohttp and Pillow are
included in the bridge requirements. The bridge uses FFmpeg/ffprobe for selected
intervals, joining and comparison videos. Its data folder keeps uploads, job
state, evidence, output videos and saved connection settings.

`scripts/start_backend.py` is the historical pod launcher with pod-specific
paths and a dependency overlay. Prefer the explicit commands above for a new
local setup, or the Docker entrypoint. Do not run two ComfyUI servers on the same
port accidentally.

## 5. Start the web UI

From Henge in a third terminal:

```sh
npm run build
npm run start -- --port 8188
```

Open **http://127.0.0.1:8188**. For development, use
`npm run dev -- --port 8188`. For an authorized remote pod, bind Next to
`0.0.0.0` and expose that port through your provider. Localhost working inside a
pod does not prove its public proxy is configured.

## Connection settings in the UI

The gear in the top bar opens **Settings → Connection** (it also opens as the first step of the setup wizard on
the first visit, and from the "offline" banner). Pick where workflows run:

- **ComfyUI**: the address of a ComfyUI with the Henge nodes.
- **Comfy API · SDK**: Henge starts `comfy-api-proxy` in front of your ComfyUI and talks to it through the
  official Comfy SDK, or uses a Comfy API URL or Comfy Cloud. Cloud execution requires Henge's custom nodes and
  models to be included in Comfy Cloud's managed catalog; publishing a package in the Registry alone does not make
  it available there. Users cannot directly install custom nodes on Cloud. See
  [Comfy's custom-node policy](https://support.comfy.org/articles/6791455062-custom-nodes-on-cloud).
- **RunPod Serverless**: endpoint ID and API key.

**Test connection** checks the API and the Henge nodes; **Save and use** stores the choice in `connection.json`
in the bridge's data folder and switches to it immediately. Keys never come back to the browser. Environment
variables (`HENGE_BACKEND`, `RUNPOD_ENDPOINT_ID`, `RUNPOD_API_KEY`, `HENGE_COMFY_SDK_*`, `COMFY_API_KEY`) win
over the screen and show there as read-only.

The address must be reachable **from the job bridge**, not just your browser. Files move through ComfyUI's own
upload and view API, so a ComfyUI on another machine works without shared folders.

Check these endpoints from the machine running the UI/bridge:

```sh
curl http://127.0.0.1:8189/system_stats
curl http://127.0.0.1:8766/health
curl http://127.0.0.1:8188/api/backend/health
```

The final health response should show `online: true`. `tara_ready` confirms the
TARA node is registered; it is not proof a GPU kernel was benchmarked.

## Using the studio

1. Select Character Swap or Motion Transfer, then attach a guide and references.
2. Select model/method in the sidebar. Character Swap uses v1.1; motion offers
   Motion Transfer v1.0 and Motion Transfer TARA v1.0 when installed. Both tasks can
   select Guide Latents or TARA; Guide remains the default.
3. Write the requested edit. Click **Generate** beside the prompt to analyze it,
   review the plan and approve generation. Anatomy adaptation is explained and
   can be accepted or disabled before generation.
4. When finished, view/download the result or the synchronized comparison with
   guide and labelled references.

**Export** beside the prompt shares a Henge configuration, not a ComfyUI
workflow or video. **Import settings** in the sidebar restores the shared
request and generation options. Attach your own media again; it is not embedded
in the JSON. Community contains the prompt templates, rather than Studio.

## Validation and limitations

The existing native services completed short UI-to-backend renders using Motion Transfer
v1.0 with Guide Latents and Motion Transfer TARA v1.0 with TARA. These were two-step integration smokes,
not quality comparisons. Optional FIBO/2D/3D branches, full Docker startup and the
new live preview still need their own real GPU validation. CPU and build checks
must not be reported as full visual validation.
