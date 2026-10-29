# Third-party notices

Project structure and configuration reference: Comfy Cinematic Studio and Comfy Reshoot, MIT licensed, copyright (c) 2026 Comfy Org.

The initial TypeScript configuration and Next.js type declarations were adapted from Cinematic Studio. Its license is reproduced below. Application source and visual design were authored for Henge (formerly Kawarimi and OpenJutsu).

MIT License

Copyright (c) 2026 Comfy Org

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


## Fonts

Bricolage Grotesque, Geist and Geist Mono are bundled locally from Google Fonts under the SIL Open Font License 1.1. The full copyright and license notices are in `public/fonts/*-OFL.txt`.

The Studio + History visual reference and its supplied artwork were provided by the project owner in the Claude Design export.

The optional moving-plate workflow was inspired by a community script shared by **crinklypaper** in the Banodoco
Discord. Henge's implementation was rewritten for automatic per-shot tracking. See
[`docs/REFERENCES.md`](docs/REFERENCES.md) for project-wide references and acknowledgements.

- Sharpness 2K/4K upscalers (`backend/comfy_nodes/henge/upscale.py`): copied with small changes from
  [bbaudio-2025/Comfyui-MMH3-UltimateUpscale](https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale)
  (MIT, Copyright (c) 2026 bbaudio-2025): `nodes/h3_latent_upscaler.py` (the MiniMax H3 3D latent upscaler from
  [LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler), MIT)
  and `nodes/tiled_diffusion.py` (per-step tiled diffusion with global window positions, a port of
  [shiimizu/ComfyUI-TiledDiffusion](https://github.com/shiimizu/ComfyUI-TiledDiffusion)). Changes: log prefixes,
  no `io.ComfyNode` wrappers, Henge node classes. The approach was found through
  [darksidewalker/ComfyUI-DaSiWa-Nodes](https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes) (GPLv3), whose code is
  not used. NVIDIA RTX Video Super Resolution runs through NVIDIA's `nvidia-vfx` package (NVIDIA proprietary
  license), installed in the Docker image.

## Pika H3 Flex model adapter

The optional Pika Ref2VA Comfy adapter is downloaded from [Pika-Labs/Pika-H3-Flex](https://huggingface.co/Pika-Labs/Pika-H3-Flex)
under the [MiniMax H3 Community License Agreement](https://huggingface.co/Pika-Labs/Pika-H3-Flex/blob/main/LICENSE),
not this application's MIT license. Its model weights are not distributed in this source repository. The download
manifest preserves the upstream license and notice files alongside the installed model.
[Pika's NOTICE](https://huggingface.co/Pika-Labs/Pika-H3-Flex/blob/main/NOTICE) attributes MiniMax H3 to MiniMax and
the FL2VA/Ref2VA adapters to Mellis, Inc. (2026). See [integration details](docs/pika-h3-flex.md).
