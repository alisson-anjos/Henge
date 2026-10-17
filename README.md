# OpenJutsu

An open studio for **motion transfer** and **video swaps**, designed around MiniMax H3 guide-latent conditioning.

## Current milestone

The interface supports one guide video, up to eleven reference pictures, stable `@Picture1` … `@Picture11` mentions, native H3 prompt conversion, a configurable multimodal prompt assistant, and JSON direction export. A source player previews your uploaded video. Text settings are saved locally; uploaded files must be reattached after reload.

**Video generation is not connected in this milestone.** Export produces a direction request, not a rendered video or an executable Comfy workflow. Quality choices are recorded in the request; they do not upscale the source. Multi-reference and motion-transfer controls describe the intended application contract, not a claim that existing Character Swap weights already support every requested edit.

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

- One video becomes guide latents in the future workflow adapter.
- Up to eleven image slots correspond to native `<Picture N>` tokens.
- The editor uses `@PictureN`; export converts to `<Picture N>` without renumbering.
- Removing a reference leaves other slots intact. Reusing an empty slot intentionally replaces that slot's identity.
- `@Video1` converts to `<Video 1>` as a textual mention only. The adapter must not attach the guide as a native video reference because a token exists.
- Workflow-specific triggers belong in the adapter. Existing Character Swap's `body_swap:` trigger is not automatically applied to the new motion-transfer mode.

## Architecture and references

Next.js App Router + React + TypeScript, following the standalone client/server organization of [Comfy Cinematic Studio](https://github.com/Comfy-Org/comfy-cinematic-studio) and [Comfy Reshoot](https://github.com/Comfy-Org/comfy-reshoot). This implementation has its own interface and application code. The next integration should submit API workflows through the Comfy Developer Platform, following the Reshoot deployment pattern.

See [competition notes](docs/competition.md) and [implementation roadmap](docs/roadmap.md).

## License

MIT for this application code. Model weights, LoRAs, datasets and third-party services have their own licenses and are not included or relicensed by this repository. This project is independent of Higgsfield and Comfy Org.
