# Run Kawarimi locally

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
git clone https://github.com/alisson-anjos/Kawarimi.git
cd Kawarimi
npm ci
cp .env.example .env.local
```

On PowerShell, use `Copy-Item .env.example .env.local`. Edit `.env.local`:

```dotenv
KAWARIMI_BACKEND_URL=http://127.0.0.1:8766
COMFY_BASE_URL=http://127.0.0.1:8189
COMFY_ROOT=/absolute/path/to/ComfyUI
KAWARIMI_DATA_DIR=/absolute/path/to/kawarimi-data
KAWARIMI_VLM_CLIP=qwen3.5_9b_w4a8_gptq.safetensors
```

Use your own absolute paths. On Windows, forward slashes such as
`C:/AI/ComfyUI` avoid backslash escaping. Keep `.env.local` out of Git.

## 2. Install the nodes and models

Install [BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes) into that
ComfyUI's `custom_nodes/bfsnodes`. Copy or symlink this repository's
`backend/comfy_nodes/kawarimi` folder to `ComfyUI/custom_nodes/kawarimi`.
Install BFSNodes' requirements using **the Python environment that runs ComfyUI**.
Restart ComfyUI after installing/updating either custom-node package.

Install the files from [the model guide](models-and-downloads.md), or configure
the manifest and run the downloader with your ComfyUI Python:

```sh
cp config/model-repos.example.json config/model-repos.json
python scripts/download_models.py --manifest config/model-repos.json --models-dir /absolute/path/to/ComfyUI/models --profiles character --dry-run
python scripts/download_models.py --manifest config/model-repos.json --models-dir /absolute/path/to/ComfyUI/models --profiles character
```

The default `character` profile downloads public weights. The private motion
profiles need configured repository/file entries or your local LoRA files.
No 4500 weight is made public by this setup. Optional FIBO, audio and SAM profiles
are documented in the Docker/model guides. The downloader never uploads models.

## 3. Start ComfyUI

From the ComfyUI folder, using its Python:

```sh
python main.py --listen 127.0.0.1 --port 8189 --lowvram --preview-method taesd
```

The H3 sampling preview needs `models/vae_approx/taeh3.safetensors`. The UI does
not need ComfyUI to be publicly exposed. If you use a custom-node whitelist,
include both `kawarimi` and `bfsnodes`.

## 4. Start the job bridge

In a second terminal, from Kawarimi, install/run using a Python environment with
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

From Kawarimi in a third terminal:

```sh
npm run build
npm run start -- --port 8188
```

Open **http://127.0.0.1:8188**. For development, use
`npm run dev -- --port 8188`. For an authorized remote pod, bind Next to
`0.0.0.0` and expose that port through your provider. Localhost working inside a
pod does not prove its public proxy is configured.

## Connection settings in the UI

The sidebar above Output has **Connection settings**. Enter the ComfyUI API
address and click **Test and save**. The bridge checks the API and required
Kawarimi nodes, then saves the connection in its data directory. Changing the
connection is blocked while jobs are active.

The address must be reachable **from the job bridge**, not just your browser.
`COMFY_ROOT` must point to the same ComfyUI files. For a separate machine or
container, input/output folders must be shared or synchronized. An API address
alone does not transfer those files. Saved UI connection settings override the
environment's URL on the next bridge restart; edit/remove `settings.json` in the
data directory if you deliberately want to reset that override.

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
   Original 10500 and TARA 4500 when those weights are installed. Both tasks can
   select Guide Latents or TARA; Guide remains the default.
3. Write the requested edit. Click **Generate** beside the prompt to analyze it,
   review the plan and approve generation. Anatomy adaptation is explained and
   can be accepted or disabled before generation.
4. When finished, view/download the result or the synchronized comparison with
   guide and labelled references.

**Export** beside the prompt shares a Kawarimi configuration, not a ComfyUI
workflow or video. **Import settings** in the sidebar restores the shared
request and generation options. Attach your own media again; it is not embedded
in the JSON. Community contains the prompt templates, rather than Studio.

## Validation and limitations

The existing native services completed short UI-to-backend renders using 10500
with Guide Latents and 4500 with TARA. These were two-step integration smokes,
not quality comparisons. Optional FIBO/2D/3D branches, full Docker startup and the
new live preview still need their own real GPU validation. CPU and build checks
must not be reported as full visual validation.
