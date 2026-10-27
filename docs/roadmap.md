# Roadmap

## Done

- Four modes on MiniMax H3, each with its own trained LoRA: Character Swap v1.1, Motion Transfer v1.0 / TARA v1.0 /
  Combined, Head Swap v1.0 and Little More Sharpness (2K/4K with the H3 latent upscaler or NVIDIA RTX VSR).
- Guide Latents and TARA-H3; the guide shown to the text encoder can be Latents + CLIP or latents only.
- Unlimited length: shots at camera cuts or fixed length, context frames between shots, redo one shot.
- Subject guidance with SAM 3.1 (tracked scene by scene across cuts): 2D color marks, 3D body, latent mask.
- Generated audio per shot, audio conditioning, new background that follows the camera (moving plate).
- Backends: local ComfyUI, Comfy SDK (API v2), RunPod pod template and RunPod Serverless; first-run wizard.
- Studio assistant (Claude, OpenAI, local models) and an MCP server for any AI client.
- Public LoRAs with their own licenses, AI-guided installation, Docker images.
- Henge nodes on the Comfy Registry ([`comfyui-henge`](https://registry.comfy.org/nodes/comfyui-henge)).

## Next

- Several positive and negative points per person when marking, for people standing close together.
- Moving plate controls per shot (parallax, push-in, particles) in the studio.
- Community: a unified system (accounts, uploads, moderation) so people can share their own examples; today the tab
  ships a fixed set.
- Mobile-friendly studio.
