# Henge

An open studio for **motion transfer** and **video swaps**, designed around MiniMax H3 guide-latent conditioning.

## Modes

| Mode | What it does | Recipe |
|---|---|---|
| Character Swap | Replace the person in a video with a character picture | Character Swap v1.1 LoRA + turbo; v1.1 one-line `body_swap:` prompt; reference background removed (BiRefNet, #808080, 0.5 MP) |
| Motion transfer | Drive a new character with the guide's performance | Motion 10500 or TARA 4500 LoRA + training adapter V2; Guide Latents or TARA |
| Head Swap | Replace only the head with a face picture | Head Swap v1.0 r32 + turbo; published `head_swap:` template |
| Sharpness | Sharpen an upload or one of your generations, optionally up to 2K/4K | MiniMax H3 + Little More Sharpness LoRA; for 2K/4K it sharpens at half size and doubles it with the H3 latent upscaler + a short H3 refine (tiled at 4K) or NVIDIA RTX Video Super Resolution; source video only |

Options: turbo LoRA (DMD 8-step, DMAD 4-step, lightx2v 8/4-step or none), base model (MiniMax H3 ref2va or
FastH3 OmniRef 8-step), CFG, Comfy Kitchen attention, auto-approve, and segmented processing with
continuity frames for long clips. **Latent mask** (Character Swap): mark the person in the video; SAM 3.1
tracks them and only a box (or outline) around them is regenerated, the rest stays pixel-identical. The
plan shows a mask preview to adjust before generating. Each job can be downloaded as the exact ComfyUI
API graph it ran.

## Setup guides

- [Run locally: UI, bridge, ComfyUI and connection settings](docs/RUN_LOCAL.md)
- [Build/run with Docker and configure automatic downloads](docker/README.md)
- [Run on RunPod: template, GPU choice and private models](docs/RUNPOD.md)
- [Run on RunPod Serverless: UI on your PC, GPU only while a job runs](docs/SERVERLESS.md)
- [Models and download links](docs/models-and-downloads.md)

## Run locally

Node.js 22.6 or newer:

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Open http://127.0.0.1:3000. No API key is required for manual prompting, local media previews or direction export.

See [models, download links and backend setup](docs/models-and-downloads.md).

## Password (optional)

The UI is open by default. To share it beyond your machine (a tunnel such as
`cloudflared tunnel --url http://localhost:8188`, or a pod's public port), set a password and
restart the UI; the browser then asks for it:

```dotenv
HENGE_PASSWORD=choose-one
HENGE_USER=henge   # optional, default "henge"
```

It covers every page and API route. Anyone with the password can start jobs on your GPU.

## Automatic prompts

Configure these server-only variables in `.env.local` and restart the server:

```dotenv
VLM_CHAT_URL=https://your-provider.example/v1/chat/completions
VLM_MODEL=your-vision-model
VLM_API_KEY=your-key-if-required
```

The endpoint must support vision chat messages with `image_url` data URLs and return `choices[0].message.content`. References are inspected independently; sampled guide frames are analyzed separately before the final prompt is composed. This is sampled-frame analysis, not full-video understanding or audio analysis. The browser tells you which media will be sent. Credentials stay on the server. The VLM is an optional dependency; choose a locally hosted open model for an entirely open-weights pipeline.

Automatic prompting in the editor and the backend planner shares `lib/h3-prompt-policy.json`. Enhanced outputs use the H3 six-section reference format, with `motion_transfer:` for motion mode and `body_swap:` for swap mode. References retain their exact indices and separate identity, outfit, object, style and environment roles. Requested scene replacements cover the entire environment while retaining the source performance and specified interaction props. Raw-prompt mode remains verbatim. See [prompt format and examples](docs/prompt-format.md).

Henge was previously developed as OpenJutsu, Kagemane and Kawarimi. ComfyUI nodes (`Henge*`), environment variables (`HENGE_*`), model folders (`loras/henge`) and browser storage keys now all use the Henge name.

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

Selected intervals longer than 15 seconds automatically reveal Context Window controls and record short-segment processing settings: 4.5 seconds requested per shot by default, a configurable timeline FPS (24 by default), and H3's 17n+5 frame grid. The displayed shot count is an estimate from the source duration; the generation panel optionally detects camera cuts. The backend generates short segments, trims padding and joins the results in order. Context Window has no configured segment-count cap; GPU memory and upload size still have limits. The single guide upload is limited to 500 MB.

The interface applies the supplied Studio + History design: a dark canvas, green Swap and purple Motion accents, locally hosted fonts, responsive layouts and English, Portuguese and Spanish copy. An animated seal indicates actual automatic-prompt processing. Animations respect reduced-motion preferences. Remote development through the configured server IP is supported by `allowedDevOrigins`.

## Guide interval selection

Uploading a guide opens a modal with video preview, timeline thumbnails, draggable start/end handles, numeric time inputs and selected-range playback. Confirm the interval or choose Use full video. Canceling a new upload removes it; canceling a later edit preserves the previous interval. The scissors button reopens the editor.

The confirmed interval controls Context Window activation, duration estimates, source-preview playback boundaries and the frames sent to the prompt VLM. Export includes `start_seconds`, `end_seconds`, selected `duration` and `source_duration`. The original media is not re-encoded or physically trimmed in the browser; the workflow adapter must apply these boundaries to video and audio together. Thumbnail generation is local. Crop/reframing is not part of this milestone.

## Local direction history

Exporting a direction saves its prompt, settings and a source thumbnail in this browser (up to 30 entries). History supports reuse, deletion, direction ratings, feedback NDJSON export and shareable JSON presets. Reuse requires reattaching media; reference slot numbers are preserved. Ratings describe directions, not generated outputs. Preset downloads omit media and local filenames. Public Community publishing remains unconnected. Video generation uses the configured local bridge.

The Keep source audio setting is independent of audio conditioning and is recorded as `output_audio.keep_source`. Curated templates supply prompts for your own media. Uploaded files stay local except for resized previews explicitly sent with Build prompt.

Enhance prompt in the generation panel adapts the direction to H3 when enabled. When disabled, the editor text is sent verbatim, including whitespace, without binding text or FIBO annotations appended. The VLM still analyzes routing and reference roles; review the exact H3 prompt in the execution plan before generating.

## Local ComfyUI backend

Run the bridge inside a Python environment compatible with the selected ComfyUI installation. FFmpeg and ffprobe must be on PATH.

```sh
python -m pip install -r backend/requirements.txt
export HENGE_PYTHON=/path/to/comfy/python
export COMFY_ROOT=/path/to/isolated/ComfyUI
python scripts/start_backend.py
```

The startup helper uses loopback ports 8189 for ComfyUI and 8766 for the bridge. The Next.js server proxies `/api/backend/`; credentials remain on the server. Configure `.env.local`, `backend/extra_model_paths.yaml`, and model paths in `backend/workflows.py` for your installation. The checked-in paths describe the development machine, not bundled model files. Install the `backend/comfy_nodes/henge` directory as a ComfyUI custom-node package. Optional SAM, SAM 3D and MoGe dependencies/assets must be available for their selected branches. The original guide branch does not require those packages.

Model-download helpers and exported API graphs are in `scripts/` and `workflows/`. Local model weights, job uploads, generated videos and service logs are excluded from Git. The development launcher is not a production deployment configuration.

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
