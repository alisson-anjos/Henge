# Henge

**Swap · Motion · Transform.** An open-source video studio on ComfyUI and MiniMax H3: give it one guide video and a
few pictures, and it swaps characters, transfers motion, swaps heads or sharpens the video — locally, on a RunPod pod
or on RunPod Serverless.

<video src="https://github.com/alisson-anjos/Henge/releases/download/demo-v1/henge-teaser.mp4" controls muted
  poster="docs/images/demo/demo_poster.jpg" title="Henge feature reel"></video>

[Play the 50-second feature reel](https://github.com/alisson-anjos/Henge/releases/download/demo-v1/henge-teaser.mp4)
· [Download the complete 4-minute demo](https://github.com/alisson-anjos/Henge/releases/download/demo-v1/henge-demo.mp4)
· [Competition cut — 1:58](https://github.com/alisson-anjos/Henge/releases/download/demo-v1/henge-demo-under-2min.mp4)

| Character Swap | Motion Transfer |
|---|---|
| ![A hiker becomes a goblin](docs/images/demo/swap.webp) | ![A character performs the guide's motion on a rooftop](docs/images/demo/motion.webp) |
| **Head Swap** | **Sharpness** (Swap result, 480p → 1080p) |
| ![Only the head changes](docs/images/demo/headswap.webp) | ![Detail restored and upscaled](docs/images/demo/sharpness.webp) |

Left: guide · right: Henge. All four ran on RunPod Serverless at 480p (Sharpness to 1080p), started from the
[MCP server](docs/MCP.md).

**Multi-character swap.** Both fighters swapped at once across camera cuts, 30 s rendered as three shots at 480p: the
studio assistant found the fighters, marked each one with its color (SAM 3.1 tracking) and generated.

| Result (guide inset) | The assistant marking the fighters |
|---|---|
| ![Two fighters swapped at once](docs/images/demo/multi_character.webp) | ![The assistant marks each fighter by color](docs/images/demo/assistant_marks.jpg) |

Fight footage: TEKKEN DADDY (YouTube), Tekken 8 © Bandai Namco — used here as a test clip.

### Not just an interface

- **One trained LoRA per mode**, not plain H3 with a prompt: Character Swap v1.1, Motion Transfer v1.0 and TARA v1.0,
  Head Swap v1.0 and Little More Sharpness v1.0 (+ an H3 latent upscaler). They come from the BFS LoRA collection,
  all trained by Alisson Anjos ([alissonerdx](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI)).
- **Guide-latent training**, a method inherited from LTX's guide-latent IC-LoRAs and brought to MiniMax H3: the
  guide's VAE latents share the output's frame grid, so frame N is built on frame N of the guide. Pose, camera and
  timing stay locked, with no desync ([how the guide reaches H3](docs/conditioning.md)).
- **TARA-H3 (Temporally Aligned Reference Attention)**, our method: keeps the guide as a native video reference, puts it
  on the generated video's temporal clock and biases each output moment to attend to the matching guide moment, with no
  extra trained layers ([technical report](https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3)).
- **Any length, shot by shot**: long clips are split at camera cuts or at a fixed length, with context frames carried
  between shots; each shot can be previewed, redone alone and downloaded.
- **Subject guidance**: mark people (SAM 3.1 tracking) and bind each to its pictures, as 2D color marks, a 3D body or a
  latent mask that keeps the rest of the frame untouched.
- **A studio assistant** that operates everything (Claude, OpenAI or a local model), or **your own AI client through
  MCP**; a **first-run wizard** for the backend; every job downloads as the exact ComfyUI graph it ran.

| Studio | Setup wizard | Assistant |
|---|---|---|
| ![Studio with source and result](docs/images/demo/studio.jpg) | ![First-run wizard, RunPod Serverless](docs/images/demo/wizard.png) | ![The assistant marks people and generates](docs/images/demo/assistant.jpg) |

Demo footage: [Pexels](https://www.pexels.com/license/) videos and original AI-generated characters.
Project references and community acknowledgements, including crinklypaper's moving-plate contribution, are collected
in [docs/REFERENCES.md](docs/REFERENCES.md).

## Modes

| Mode | What it does | Recipe |
|---|---|---|
| Character Swap | Replace the person in a video with a character picture | Character Swap v1.1 LoRA + turbo; v1.1 one-line `body_swap:` prompt; reference background removed (BiRefNet, #808080, 0.5 MP) |
| Motion transfer | Drive a new character with the guide's performance | Motion Transfer v1.0 or TARA v1.0 LoRA + training adapter V2; Guide Latents or TARA (experimental) |
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

> **Quickest way:** give [docs/AI_GUIDED_INSTALL.md](docs/AI_GUIDED_INSTALL.md) to a coding agent (Claude Code, Codex, Cursor); it checks your machine, asks which option you want and installs it.

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
task LoRAs). [Models and download links](docs/models-and-downloads.md). The Motion Transfer LoRAs are public in [Alissonerdx/Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI) (BFS Motion Transfer license); only the experimental FFP model is private:
its download needs a Hugging Face token with read access (`HF_TOKEN`).

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
     --profiles character,motion,headswap,sharpness,fibo,sam2d
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
   terminals. The backend (ComfyUI address, Comfy SDK or RunPod Serverless) can also be set in the UI: gear in the top bar → **Connection**.

Details and troubleshooting: [docs/RUN_LOCAL.md](docs/RUN_LOCAL.md).

### B. RunPod, everything in one pod

One container runs the UI, the bridge and ComfyUI; models download on the first boot into the pod volume.

1. **[Deploy the Henge template on RunPod](https://console.runpod.io/deploy?template=mnxax277c8&ref=8t518hht)** — image, disks, ports and environment are already set
   (new to RunPod? [create your account with our link](https://runpod.io?ref=8t518hht)).
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

1. [Create a RunPod account](https://runpod.io?ref=8t518hht) if you have none, install [`runpodctl`](https://github.com/runpod/runpodctl) with
   your API key, and store your Hugging Face token as the RunPod secret `hf_token`.
2. Put the models on a network volume (once; a temporary pod downloads them and is deleted):

   ```sh
   VOLUME_GB=180 scripts/runpod_volume.sh            # prints the volume id
   ```

3. Create the endpoint from the Henge serverless template (RTX 5090 first; RTX PRO 6000 only when no 5090 is free):

   ```sh
   VOLUME_ID=<volume id> scripts/runpod_serverless.sh   # prints the endpoint id
   ```

4. Run the UI on your computer and open http://localhost:8188:

   ```sh
   docker run -p 8188:8188 -v henge-state:/state -e HENGE_BACKEND=runpod \
     -e RUNPOD_ENDPOINT_ID=<endpoint id> -e RUNPOD_API_KEY=<api key> \
     ghcr.io/alisson-anjos/henge-ui:latest
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
`ghcr.io/alisson-anjos/henge-ui` (UI and bridge only), tagged `latest` (main), by branch and `sha-<commit>`.

### More guides

- **[AI-guided installation](docs/AI_GUIDED_INSTALL.md)**: paste one prompt into Claude Code, Codex or Cursor and it installs Henge for you
- [Use Henge from your own AI client through MCP](docs/MCP.md) (instead of the built-in assistant)
- [References and acknowledgements](docs/REFERENCES.md)
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

All task LoRAs Henge runs are by Alisson Anjos ([alissonerdx](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI),
BFS collection): Character Swap v1.1, Motion Transfer v1.0, Motion Transfer TARA v1.0 and Combined, Head Swap v1.0,
and Little More Sharpness (LMS) v1.0 — the sharpness LoRA used to push results further, alone in Sharpness mode or as a
second pass on any generation — plus the H3 latent upscaler LMS v0.1 (initialized from LBH-123-AI's upscaler).
TARA-H3 is also ours ([technical report](https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3)).

Third-party models: MiniMax H3 ([MiniMaxAI](https://huggingface.co/MiniMaxAI/MiniMax-H3), ComfyUI weights by
[Comfy-Org](https://huggingface.co/Comfy-Org/MiniMax-H3)), the training adapter V2
([ostris](https://huggingface.co/ostris/minimax_h3_training_adapter)), the turbo LoRAs
([drbaph](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI), [Kijai](https://huggingface.co/Kijai/MiniMax-H3-experimental),
[lightx2v](https://huggingface.co/lightx2v/Minimax-h3-Turbo)), SAM 3.1, BiRefNet, FIBO (Bria) and the Qwen3.5 planner.

The Sharpness 2K/4K H3 upscaler is copied, with small changes, from
[bbaudio-2025/Comfyui-MMH3-UltimateUpscale](https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale) (MIT):
the [LBH-123-AI](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) 3D latent upscaler and per-step
tiled diffusion for H3. We found the approach in
[ComfyUI-DaSiWa-Nodes](https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes). Details in THIRD_PARTY_NOTICES.md.
