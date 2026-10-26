# Henge

An open studio for **motion transfer** and **video swaps**, designed around MiniMax H3 guide-latent conditioning.

## Modes

| Mode | What it does | Recipe |
|---|---|---|
| Character Swap | Replace the person in a video with a character picture | Character Swap v1.1 LoRA + turbo; v1.1 one-line `body_swap:` prompt; reference background removed (BiRefNet, #808080, 0.5 MP) |
| Motion transfer | Drive a new character with the guide's performance | Motion Transfer v1.0 LoRA (10500 steps) + training adapter V2; Guide Latents or TARA (experimental) |
| Head Swap | Replace only the head with a face picture | Head Swap v1.0 r32 + turbo; published `head_swap:` template |
| Sharpness | Sharpen an upload or one of your generations, optionally up to 2K/4K | MiniMax H3 + Little More Sharpness LoRA; for 2K/4K it sharpens at half size and doubles it with the H3 latent upscaler + a short H3 refine (tiled at 4K) or NVIDIA RTX Video Super Resolution; source video only |

Options: turbo LoRA (DMD 8-step, DMAD 4-step, pDMD 4/2-step, lightx2v 8/4-step or none), base model (MiniMax H3
ref2va or FastH3 OmniRef 8-step), CFG, Comfy Kitchen attention, auto-approve, and shots for long clips (cut at
camera cuts or at a fixed length, each shot playable before rendering and downloadable when done). **Subject
guidance**: mark people in the video and bind each to its pictures. *2D* paints each one with its color (solid
or translucent, with a live preview on the approval screen), *3D* draws a colored body with face, and *Mask*
regenerates only the area around them so the rest of the video stays pixel-identical. **FIBO** can redraw an
animal reference as an upright humanoid for a human performer. Each job can be downloaded as the exact ComfyUI
API graph it ran.

## How to run Henge

Henge has three parts: the **web UI** (port 8188), the **bridge** (port 8766, plans jobs, cuts and joins
video with ffmpeg) and **ComfyUI** (runs the MiniMax H3 graphs on a GPU). Pick where each one runs:

| | A. Local, your ComfyUI | B. RunPod, all in one pod | C. Local UI + RunPod Serverless |
|---|---|---|---|
| UI and bridge | your PC | the pod | your PC (no GPU needed) |
| ComfyUI / GPU | your PC (NVIDIA, 32 GB VRAM, 64 GB RAM) | the pod | RunPod workers, started per job |
| You pay | nothing extra | while the pod is on | per second while a job runs (+15 s idle) and the volume's storage |
| First result | immediate | after the first boot download | cold start of 1–3 min after idle |
| Live sampling preview | yes | yes | progress only |
| Best for | you have an RTX 5090 or similar | long sessions | occasional use, no local GPU |

All three need the models: about 125 GB with every profile (H3 base, text encoder, VAE, planner VLM and the
task LoRAs). [Models and download links](docs/models-and-downloads.md). The motion LoRAs are private for now:
their downloads need a Hugging Face token with read access (`HF_TOKEN`).

### A. Local, with your own ComfyUI

You need a working ComfyUI (PyTorch with CUDA 13, NVIDIA driver 580+), Node.js 22.6+, Python 3.10+ and
`ffmpeg`/`ffprobe` on the PATH.

1. Get Henge and the nodes:

   ```sh
   git clone https://github.com/alisson-anjos/Henge.git && cd Henge
   npm ci && npm run build
   ln -s "$PWD/backend/comfy_nodes/henge" /path/to/ComfyUI/custom_nodes/henge
   git clone https://github.com/alisson-anjos/ComfyUI-BFSNodes.git /path/to/ComfyUI/custom_nodes/bfsnodes
   /path/to/comfy/python -m pip install -r /path/to/ComfyUI/custom_nodes/bfsnodes/requirements.txt -r backend/requirements.txt
   ```

   On Windows, copy the `backend/comfy_nodes/henge` folder into `custom_nodes` instead of the link.
2. Download the models into ComfyUI (choose profiles; see the table in [SERVERLESS.md](docs/SERVERLESS.md#what-goes-on-it)):

   ```sh
   HF_TOKEN=<token> /path/to/comfy/python scripts/download_models.py \
     --manifest config/model-repos.example.json --models-dir /path/to/ComfyUI/models \
     --profiles character,headswap,sharpness,motion10500,fibo
   ```

3. Start ComfyUI on port 8189 (keep it on localhost):

   ```sh
   python main.py --listen 127.0.0.1 --port 8189 --preview-method taesd --fast-disk
   ```

4. Create `.env.local` in the Henge folder:

   ```dotenv
   COMFY_BASE_URL=http://127.0.0.1:8189
   COMFY_ROOT=/path/to/ComfyUI          # optional: enables the model checklist
   HENGE_DATA_DIR=/path/to/henge-data   # jobs, uploads and results
   ```

5. Start the bridge and the UI, then open http://127.0.0.1:8188:

   ```sh
   PYTHON=/path/to/comfy/python scripts/local_stack.sh start   # also: status, stop
   ```

   On Windows, run the two commands from [RUN_LOCAL.md](docs/RUN_LOCAL.md#4-start-the-job-bridge) in two
   terminals. The ComfyUI address can also be changed in the UI (**Connection settings**).

Details and troubleshooting: [docs/RUN_LOCAL.md](docs/RUN_LOCAL.md).

### B. RunPod, everything in one pod

One container runs the UI, the bridge and ComfyUI; models download on the first boot into the pod volume.

1. RunPod → **My Templates → New Template** (Pod): image `ghcr.io/alisson-anjos/henge:runpod-template`,
   container disk 30 GB, volume 180 GB at `/workspace`, HTTP port `8188`.
2. Environment: `HF_TOKEN={{ RUNPOD_SECRET_hf_token }}` (store the token as the secret `hf_token`), and
   optionally `HENGE_MODEL_PROFILES` to download fewer models and `HENGE_PASSWORD` to require a login (or turn it on later from the 🔓 button in the UI, see [Login](#login-optional)).
3. Deploy on a GPU with a CUDA 13 driver (set the CUDA filter to 13.0+). An RTX 5090 works; 48–96 GB GPUs
   reload models less often.
4. Watch the logs; the first boot downloads the models (the setup screen on port 8188 shows progress).
   Then open **Connect → HTTP 8188**.

Stop the pod when you are done: the volume keeps the models and your job history for the next one.
Details: [docs/RUNPOD.md](docs/RUNPOD.md).

### C. UI on your PC, GPU on RunPod Serverless

The UI and bridge run on your computer; each job stage (plan, FIBO, every shot) is one request to a
serverless endpoint, whose workers start on demand and stop 15 s after the last request.

1. Install [`runpodctl`](https://github.com/runpod/runpodctl) with your API key, and store your Hugging Face
   token as the RunPod secret `hf_token`.
2. Put the models on a network volume (once; a temporary pod downloads them and is deleted):

   ```sh
   VOLUME_GB=180 scripts/runpod_volume.sh            # prints the volume id
   ```

3. Create the endpoint (RTX 5090 first; RTX PRO 6000 only when no 5090 is free):

   ```sh
   VOLUME_ID=<volume id> scripts/runpod_serverless.sh   # prints the endpoint id
   ```

4. Run the UI on your computer and open http://localhost:8188:

   ```sh
   docker run -p 8188:8188 -v henge-state:/state -e HENGE_BACKEND=runpod \
     -e RUNPOD_ENDPOINT_ID=<endpoint id> -e RUNPOD_API_KEY=<api key> \
     ghcr.io/alisson-anjos/henge-ui:runpod-template
   ```

   Without Docker: clone Henge, `npm ci && npm run build`, install `backend/requirements.txt`, put
   `HENGE_BACKEND=runpod`, `RUNPOD_ENDPOINT_ID`, `RUNPOD_API_KEY` and `HENGE_DATA_DIR` in `.env.local`, then
   `scripts/local_stack.sh start`.

Media of any size go through the endpoint's volume; nothing uses S3 or another storage service.
Details, costs and troubleshooting: [docs/SERVERLESS.md](docs/SERVERLESS.md).

### Updating

- **A**: `git pull && npm ci && npm run build`, then `scripts/local_stack.sh start` and restart ComfyUI (the
  henge nodes changed).
- **B**: deploy a new pod from the template (the volume keeps the models).
- **C**: pull the new `henge-ui` image; for the workers, `ENDPOINT_ID=<id> TEMPLATE_ID=<id>
  IMAGE=ghcr.io/alisson-anjos/henge:sha-<commit> scripts/runpod_serverless.sh` switches the image and drains
  the old workers.

Images are built by GitHub Actions and published to GitHub Container Registry:
`ghcr.io/alisson-anjos/henge` (everything; the serverless worker uses it with `HENGE_ROLE=worker`) and
`ghcr.io/alisson-anjos/henge-ui` (UI and bridge only), tagged by branch and `sha-<commit>`.

### More guides

- [Instructions for an AI agent to deploy everything on RunPod](docs/AGENT_DEPLOY.md)
- [Run locally: ports, connection settings, Windows](docs/RUN_LOCAL.md)
- [Docker Compose on your own GPU machine](docker/README.md)
- [RunPod pod template](docs/RUNPOD.md) · [RunPod Serverless](docs/SERVERLESS.md)
- [Models and download links](docs/models-and-downloads.md) · [Guide conditioning](docs/conditioning.md)

## Login (optional)

The UI is open by default: anyone who reaches its address can start jobs on your GPU or your RunPod account. Before
you share it (a tunnel such as `cloudflared tunnel --url http://localhost:8188`, a Tailscale address, or a pod's
public port), turn on a login. You can do it in either of two ways:

- **From the UI:** click **🔓 Open** in the top bar, choose a user and a password (8+ characters) and press
  **Require login**. The browser asks for it right away. The login is saved as a scrypt hash in `access.json` in the
  bridge data folder (`HENGE_DATA_DIR`), so it survives restarts; the same button changes it or turns it off.
- **From the environment** (for pod templates and scripts), it overrides the UI setting:

  ```dotenv
  HENGE_PASSWORD=choose-one
  HENGE_USER=henge   # optional, default "henge"
  ```

The login covers every page and every `/api` route, including the assistant and its key settings. What stays behind
it:

| Service | Port | Protection |
|---|---|---|
| Henge UI | 8188 | the login above |
| Bridge (FastAPI) | 8766 | listens on `127.0.0.1` only; reached through the UI |
| ComfyUI | 8189 | listens on `127.0.0.1` only. `HENGE_EXPOSE_COMFY=1` opens it **without any login**: debugging only |
| RunPod Serverless worker | — | only callers with your RunPod API key; the key stays in the bridge's environment |

## Real people (optional filter)

Set `HENGE_LIKENESS_FILTER=warn` to have the planner warn when a reference picture looks like a real public figure,
or `block` to stop such jobs before they generate. It is `off` by default. Only generate real people with their
consent.

## Automatic prompts

Configure these server-only variables in `.env.local` and restart the server:

```dotenv
VLM_CHAT_URL=https://your-provider.example/v1/chat/completions
VLM_MODEL=your-vision-model
VLM_API_KEY=your-key-if-required
```

The endpoint must support vision chat messages with `image_url` data URLs and return `choices[0].message.content`. References are inspected independently; sampled guide frames are analyzed separately before the final prompt is composed. This is sampled-frame analysis, not full-video understanding or audio analysis. The browser tells you which media will be sent. Credentials stay on the server. The VLM is an optional dependency; choose a locally hosted open model for an entirely open-weights pipeline.

Automatic prompting in the editor and the backend planner shares `lib/h3-prompt-policy.json`. Enhanced outputs use the H3 six-section reference format, with `motion_transfer:` for motion mode and `body_swap:` for swap mode. References retain their exact indices and separate identity, outfit, object, style and environment roles. Requested scene replacements cover the entire environment while retaining the source performance and specified interaction props. Raw-prompt mode remains verbatim. See [prompt format and examples](docs/prompt-format.md).

## Reference contract

- Guide Latents is the default method. TARA (experimental) uses the native video-reference channel with temporal alignment instead. Both motion LoRAs can select either method. How each path feeds the guide to H3: [docs/conditioning.md](docs/conditioning.md).
- Up to eleven image slots correspond to native `<Picture N>` tokens.
- The editor uses `@PictureN`; export converts to `<Picture N>` without renumbering.
- Removing a reference leaves other slots intact. Reusing an empty slot intentionally replaces that slot's identity.
- `@Video1` converts to `<Video 1>`. Native video-reference latents are attached only when TARA is explicitly selected.

## Architecture and references

Next.js App Router + React + TypeScript, following the standalone client/server organization of [Comfy Cinematic Studio](https://github.com/Comfy-Org/comfy-cinematic-studio) and [Comfy Reshoot](https://github.com/Comfy-Org/comfy-reshoot). This implementation has its own interface and application code. The local bridge submits API workflows to ComfyUI; its address is configured server-side.

See [competition notes](docs/competition.md) and [implementation roadmap](docs/roadmap.md).

## License

MIT for this application code. Model weights, LoRAs, datasets and third-party services have their own licenses and are not included or relicensed by this repository. This project is independent of Higgsfield and Comfy Org.

## Audio and long videos

Audio conditioning can be enabled independently of the visual guide. Direction exports record whether guide-video audio should condition generation; the prompt VLM receives sampled visual frames only, not audio.

Selected intervals longer than 15 seconds automatically reveal Context Window controls and record short-segment processing settings: 4.5 seconds requested per shot by default, a configurable timeline FPS (24 by default), and H3's 17n+5 frame grid. The Auto cut card chooses how camera cuts split the shots (shot length ending at cuts, a new shot at every cut, or fixed length), and the approval screen shows every shot before rendering. The backend generates short segments, trims padding and joins the results in order. Context Window has no configured segment-count cap; GPU memory and upload size still have limits. The single guide upload is limited to 500 MB.

The interface applies the supplied Studio + History design: a dark canvas, green Swap and purple Motion accents, locally hosted fonts, responsive layouts and English, Portuguese and Spanish copy. An animated seal indicates actual automatic-prompt processing. Animations respect reduced-motion preferences. Remote development through the configured server IP is supported by `allowedDevOrigins`.

## Guide interval selection

Uploading a guide opens a modal with video preview, timeline thumbnails, draggable start/end handles, numeric time inputs and selected-range playback. Confirm the interval or choose Use full video. Canceling a new upload removes it; canceling a later edit preserves the previous interval. The scissors button reopens the editor.

The confirmed interval controls Context Window activation, duration estimates, source-preview playback boundaries and the frames sent to the prompt VLM. Export includes `start_seconds`, `end_seconds`, selected `duration` and `source_duration`. The original media is not re-encoded or physically trimmed in the browser; the workflow adapter must apply these boundaries to video and audio together. Thumbnail generation is local. Crop/reframing is not part of this milestone.

## Local direction history

Exporting a direction saves its prompt, settings and a source thumbnail in this browser (up to 30 entries). History supports reuse, deletion, direction ratings, feedback NDJSON export and shareable JSON presets. Reuse requires reattaching media; reference slot numbers are preserved. Ratings describe directions, not generated outputs. Preset downloads omit media and local filenames. Public Community publishing remains unconnected. Video generation uses the configured local bridge.

The Keep source audio setting is independent of audio conditioning and is recorded as `output_audio.keep_source`. Curated templates supply prompts for your own media. Uploaded files stay local except for resized previews explicitly sent with Build prompt.

Enhance prompt in the generation panel adapts the direction to H3 when enabled. When disabled, the editor text is sent verbatim, including whitespace, without binding text or FIBO annotations appended. The VLM still analyzes routing and reference roles; review the exact H3 prompt in the execution plan before generating.

## Development checks

```sh
python -m unittest discover -s backend/tests -q
npm run build
```

## Credits

The Sharpness 2K/4K H3 upscaler is copied, with small changes, from
[bbaudio-2025/Comfyui-MMH3-UltimateUpscale](https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale) (MIT):
the [LBH-123-AI](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) 3D latent upscaler and per-step
tiled diffusion for H3. We found the approach in
[ComfyUI-DaSiWa-Nodes](https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes). Details in THIRD_PARTY_NOTICES.md.
