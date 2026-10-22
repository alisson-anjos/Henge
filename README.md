# Kagemane

An open studio for **motion transfer** and **video swaps**, designed around MiniMax H3 guide-latent conditioning.

## Current milestone

Kagemane connects its studio UI to a local FastAPI bridge and an isolated ComfyUI backend. It supports guide intervals, image references, subject/color bindings, optional prompt enhancement, reviewed execution plans, conditional FIBO image preparation, segmented generation, progress, cancellation, result comparison and server history.

The integration has passed TypeScript, production-build and CPU contract checks. End-to-end GPU generation and the quality of 2D/3D tracking still require validation. FIBO prepares a pose/appearance image; it does not perform full temporal skeleton retargeting. SAM 3D Body requires a human source.

## Run locally

Node.js 22.6 or newer:

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Open http://127.0.0.1:3000. No API key is required for manual prompting, local media previews or direction export.

## Automatic prompts

Configure these server-only variables in `.env.local` and restart the server:

```dotenv
VLM_CHAT_URL=https://your-provider.example/v1/chat/completions
VLM_MODEL=your-vision-model
VLM_API_KEY=your-key-if-required
```

The endpoint must support vision chat messages with `image_url` data URLs and return `choices[0].message.content`. It receives the short brief, labeled picture previews (up to 1024 pixels), and six timestamped frames from the guide (up to 768 pixels). This is sampled-frame analysis, not full-video understanding or audio analysis. The browser tells you which media will be sent. Credentials stay on the server. The VLM is an optional dependency; choose a locally hosted open model for an entirely open-weights pipeline.

The initial prompt template is in `lib/prompt.ts`. Replace it with the finalized OpenJutsu training/inference template as the model develops. It has separate motion-transfer and swap instructions. Provider inference is not exercised without configuration and explicit use of the Build prompt button.

## Reference contract

- The selected video interval supplies aligned guide latents. Its sampled frames can also enter Qwen/CLIP context without native video-reference latents.
- Up to eleven image slots correspond to native `<Picture N>` tokens.
- The editor uses `@PictureN`; export converts to `<Picture N>` without renumbering.
- Removing a reference leaves other slots intact. Reusing an empty slot intentionally replaces that slot's identity.
- `@Video1` converts to `<Video 1>` as a textual mention only. The adapter must not attach the guide as a native video reference because a token exists.

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

Exporting a direction saves its prompt, settings and a source thumbnail in this browser (up to 30 entries). History supports reuse, deletion, direction ratings, feedback NDJSON export and shareable JSON presets. Reuse requires reattaching media; reference slot numbers are preserved. Ratings describe directions, not generated outputs. Preset downloads omit media and local filenames. Public Community publishing and video generation remain unconnected.

The Keep source audio setting is independent of audio conditioning and is recorded as `output_audio.keep_source`. Curated templates supply prompts for your own media. Uploaded files stay local except for resized previews explicitly sent with Build prompt.

Enhance prompt in the generation panel adapts the direction to H3 when enabled. When disabled, the editor text is sent verbatim, including whitespace, without binding text or FIBO annotations appended. The VLM still analyzes routing and reference roles; review the exact H3 prompt in the execution plan before generating.

## Local ComfyUI backend

Run the bridge inside a Python environment compatible with the selected ComfyUI installation. FFmpeg and ffprobe must be on PATH.

```sh
python -m pip install -r backend/requirements.txt
export KAGEMANE_PYTHON=/path/to/comfy/python
export COMFY_ROOT=/path/to/isolated/ComfyUI
python scripts/start_backend.py
```

The startup helper uses loopback ports 8189 for ComfyUI and 8766 for the bridge. The Next.js server proxies `/api/backend/`; credentials remain on the server. Configure `.env.local`, `backend/extra_model_paths.yaml`, and model paths in `backend/workflows.py` for your installation. The checked-in paths describe the development machine, not bundled model files. Install the `backend/comfy_nodes/kagemane` directory as a ComfyUI custom-node package. Optional SAM, SAM 3D and MoGe dependencies/assets must be available for their selected branches. The original guide branch does not require those packages.

Model-download helpers and exported API graphs are in `scripts/` and `workflows/`. Local model weights, job uploads, generated videos and service logs are excluded from Git. The development launcher is not a production deployment configuration.

```sh
python -m unittest discover -s backend/tests -q
npm run build
```
