# References and acknowledgements

Everything Henge builds on, in one place. Exact downloadable weights, destinations and profiles are in
[`config/model-repos.example.json`](../config/model-repos.example.json). License texts for code copied into this repository are in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Our work

- **Task LoRAs (BFS collection)** by Alisson Anjos ([alissonerdx](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI)):
  Character Swap v1.1, Motion Transfer v1.0, Motion Transfer TARA v1.0 and Combined, Head Swap v1.0, Little More Sharpness
  (LMS) v1.0 — the sharpness LoRA used to push results further — and the H3 latent upscaler LMS v0.1. Licenses:
  [Character Swap](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/LICENSE_CHARACTER_SWAP.md),
  [Motion Transfer](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/LICENSE_MOTION_TRANSFER.md).
- **TARA-H3 — Temporally Aligned Reference Attention**:
  [technical report](https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3), node
  `BFSMiniMaxH3NativeTemporal` in [ComfyUI-BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes).
- **ComfyUI-BFSNodes** (shot planner, TARA, H3 tools) by Alisson Anjos.

## Community ideas and code

- **crinklypaper** (Banodoco Discord), *Anime Recast with H3*: the two scripts behind Henge's **moving plate** (a new
  background that follows the original camera: Lucas-Kanade tracking on the background + a RANSAC similarity per frame)
  and **per-shot generated audio** (each shot's H3 soundtrack laid at its cut), plus the advice of two or three
  positive SAM points per person. Henge made the moving plate automatic per camera shot (`backend/moving_plate.py`) and lays
  the per-shot audio on its own shot timeline (`backend/server.py`). Thank you, crinklypaper.
- **Sharpness 2K/4K upscaler**: copied with small changes from
  [bbaudio-2025/Comfyui-MMH3-UltimateUpscale](https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale) (MIT): the
  [LBH-123-AI](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) 3D latent upscaler and per-step tiled
  diffusion for H3; found through [ComfyUI-DaSiWa-Nodes](https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes).
- **Guide-latent training**: the method follows LTX's guide-latent IC-LoRAs; H3 training through
  [ostris/ai-toolkit](https://github.com/ostris/ai-toolkit) and
  [ComfyUI-AIToolkit-MiniMaxH3](https://github.com/ostris/ComfyUI-AIToolkit-MiniMaxH3).

## Models

- MiniMax H3 — [MiniMaxAI](https://huggingface.co/MiniMaxAI/MiniMax-H3); ComfyUI weights, text encoder, VAEs and the
  Qwen3.5 9B planner by [Comfy-Org](https://huggingface.co/Comfy-Org/MiniMax-H3).
- Training adapter V2 — [ostris/minimax_h3_training_adapter](https://huggingface.co/ostris/minimax_h3_training_adapter).
- Turbo LoRAs — [drbaph](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI) (DMD 8-step),
  [Kijai](https://huggingface.co/Kijai/MiniMax-H3-experimental) (DMAD, pDMD),
  [lightx2v](https://huggingface.co/lightx2v/Minimax-h3-Turbo),
  [Pika H3 Flex](https://huggingface.co/Pika-Labs/Pika-H3-Flex) (Ref2VA Comfy adapter and six-step workflow).
- FastH3 OmniRef — [FastVideo](https://huggingface.co/FastVideo/FastH3-Omni-Comfy).
- SAM 3.1 and SAM 3D Body (Meta), BiRefNet, MoGe 2, FIBO (Bria), NVIDIA RTX Video Super Resolution (`nvidia-vfx`).
- TAEH3 (live previews only) is derived from madebyollin's temporal autoencoder work.

## Software

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI), the Comfy SDK and comfy-api-proxy (Comfy Org).
- Project structure adapted from Comfy Cinematic Studio / Comfy Reshoot (MIT, Comfy Org).
- Next.js, FastAPI, FFmpeg, OpenCV, the MCP Python SDK, RunPod and `runpodctl`.

## Demo media

- Videos from [Pexels](https://www.pexels.com/license/); reference characters are original AI-generated pictures.
- Multi-character fight: footage from TEKKEN DADDY (YouTube), Tekken 8 © Bandai Namco, used as a test clip.
- Demo music: original, synthesized for the video.
