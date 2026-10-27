# Standalone ComfyUI examples

Workflows you can open in ComfyUI without the Henge studio. Model files use their published names; no models, keys or
media are included.

| File | What it is |
|---|---|
| `minimax_h3_motion_transfer_v1.0_tara_workflow.json` | Motion Transfer v1.0 with **TARA**: the guide stays a native H3 video reference, aligned frame by frame (`BFSMiniMaxH3NativeTemporal`). |
| `minimax_h3_motion_transfer_v1.0_tara_auto_prompt_workflow.json` | The same, with automatic prompting: each reference picture and the guide frames are described with Generate Text and a final pass writes the H3 prompt; canvas and frame count come from the loaded video. See [`motion_transfer_tara_auto_prompt.md`](motion_transfer_tara_auto_prompt.md). |
| `minimax_h3_character_swap_v1.1_workflow.json` | The Character Swap v1.1 graph Henge's swap mode is built on (guide latents through Add Guide). |

## LoRAs

From [Alissonerdx/Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI), into `models/loras/`:
`minimax_h3_motion_transfer_v1.0_ref2va.safetensors` (or `…_tara_v1.0_ref2va`), and
`minimax_h3_ref2va_training_adapter_v2.safetensors` from
[ostris/minimax_h3_training_adapter](https://huggingface.co/ostris/minimax_h3_training_adapter).

**Training adapter V2.** The Motion Transfer LoRAs were trained on top of adapter V2 kept frozen. They usually work
without it, but the examples load the adapter first and the motion LoRA after it, which reproduces the training
conditions; compare both on your clips.

## TARA

**TARA-H3 — Temporally Aligned Reference Attention.** Native reference conditioning alone did not reliably reproduce the
timing of a source performance in H3, while aligned guide latents copy it frame by frame. TARA keeps the motion video as
native reference tokens (no Add Guide), translates its temporal RoPE coordinates so it shares the generated video's
clock, and adds a bounded temporal penalty only to generated-video queries attending to motion-reference keys. Image
references keep their native coordinates, and the attention change adds no learned layers. Technical report (v0.1.2,
experimental, not peer reviewed):
[TARA-H3 on GitHub](https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3).

Requirements: a current ComfyUI with native MiniMax H3 and Generate Text, VideoHelperSuite (`VHS_LoadVideo`) and
[ComfyUI-BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes) 1.115.21 or later. How the guide reaches H3 in
each method: [docs/conditioning.md](../../docs/conditioning.md).
