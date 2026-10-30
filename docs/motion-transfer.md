# Motion Transfer v1.0 — Guide Latents and TARA workflows

Four standalone ComfyUI workflows are provided, with one matching LoRA per conditioning method:

| Method / LoRA | Native H3 workflow, manual prompt | Shot Planner, automatic prompt |
| --- | --- | --- |
| Motion Transfer v1.0 / Guide Latents | [Native Guide Latents](../workflows/minimax_h3_motion_transfer_workflow_native_nodes_v1.0.json) | [Guide Latents + Planner](../workflows/minimax_h3_motion_transfer_workflow_planner_v1.0.json) |
| Motion Transfer TARA v1.0 / native Video 1 | [Native TARA](../workflows/minimax_h3_motion_transfer_tara_workflow_native_nodes_v1.0.json) | [TARA + Planner](../workflows/minimax_h3_motion_transfer_tara_workflow_planner_v1.0.json) |

These use the published Character Swap v1.1 workflows as a reference for model loading, native H3 conditioning,
and the BFS shot-loop contract. They use Motion Transfer prompts and the appropriate Motion Transfer LoRA.
No private Henge nodes or Henge server are required.

## References: any explicitly assigned combination of 1..N pictures

**You do not need a mandatory character picture plus a background picture.** The native examples connect
only Picture 1. Picture 2 is optional and disconnected. Add more consecutive reference-image slots when
needed (up to 9 in native H3); the Planner instead manages its own reference list, globally and per shot.

A picture can supply an identity, clothing, an object, an environment or style. Several pictures can describe
one character. Two pictures may depict two characters, two views of one character, or another requested
combination. Image count does not determine performer count. These workflows do not strip backgrounds automatically.

The **prompt assigns roles**. Examples:

- One picture: transfer the guide performance to the identity/outfit in Picture 1; keep the guide setting.
- Three character pictures: explicitly match each guide performer to its picture, including when it enters
  later, turns away or is occluded. Do not bind identities solely by current left/right screen position.
- Two views of one character: state that both pictures define the same identity, not two performers.
- Character + outfit + object: assign identity to Picture 1, clothing to Picture 2 and the object to Picture 3.
- A setting reference is also allowed, but changes the scene only when explicitly requested.

The guide supplies motion and timing. A reference still pose is not a replacement for the guide performance.
Review the prompt and rendered frames; reference binding is not guaranteed solely by a well-formed prompt.

## Dependencies and models

Use current ComfyUI with native MiniMax H3 nodes, **ComfyUI-BFSNodes main 1.115.33+**, and
VideoHelperSuite for the native workflow's video loader. Restart ComfyUI after updating custom nodes.
"Native" means native H3 conditioning, not zero custom nodes: a small BFS helper derives geometry and
frame counts; TARA uses the BFS model patch. The native examples do not require a prompt VLM or Planner.

| Component | Filename / source |
| --- | --- |
| Base | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` — [Comfy-Org H3](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main) |
| H3 text encoder | `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` — Comfy-Org H3 |
| Video VAE | `minimax_h3_video_vae_fp16.safetensors` — Comfy-Org H3 |
| Turbo | `minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors` — [drbaph](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI/tree/main/experimental) |
| Guide Latents task | `minimax_h3_motion_transfer_v1.0_ref2va.safetensors` — [BFS LoRAs](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/tree/main/loras) |
| TARA task | `minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors` — BFS LoRAs |
| Planner prompt VLM | `qwen3.5_9b_w4a8_gptq.safetensors` — [Comfy-Org MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/tree/main/text_encoders); choose another compatible generation-capable VLM if preferred |

Place base weights in `models/diffusion_models`, encoders in `models/text_encoders`, VAE in `models/vae`,
and LoRAs in `models/loras`. Select the installed name if files live in a subfolder. The encoder used for
prompt writing is separate from H3's own text encoder. Load the turbo and the task LoRA at strength 1; the
training adapter the LoRAs were trained over only counters distillation during training and is not loaded. The examples use DMD 8-step, Euler/simple, CFG 1. Do not stack a second copy of a component
that is already merged into your chosen weights.

## Native workflow

Upload the guide and Picture 1, then edit the native H3 prompt. Attach additional pictures only when needed.
Default: 24 fps, source-derived aspect ratio, at most 0.4 MP and a short 107-frame initial test (~4.46 s).
Both VHS `frame_load_cap` and Prepare `max_frames` cap the input: change both to intentionally test longer clips.
A small frame-grid padding is trimmed after decode. Use the Planner versions for longer videos and cuts.

Guide Latents uses **MiniMaxH3AddGuide at frame 0**. It does not also send the entire guide through native
`ref_video_1`. TARA uses native **ref_video_1** plus **BFSMiniMaxH3NativeTemporal**, without a full-video Add Guide.
In TARA the patched MODEL must reach both the guider and scheduler. Disabling TARA alone does not turn
native reference conditioning into Guide Latents; use the separate matching workflow/LoRA.

Audio copies the source soundtrack; no dialogue/music is generated. Long/high-resolution media can exhaust
CPU RAM or VRAM before/after sampling. The geometry cap is not a promise that every source fits memory.

## Planner workflow

Upload the guide and your 1..N reference images inside **BFS Shot Planner**. Replace the placeholder names;
no example media are bundled. Write the intended role assignments in the request and inspect the generated prompts.
Auto Prompt is enabled with `motion_transfer:` and the six H3 sections. No saved descriptions, private filenames,
precomputed prompts, segmentation masks or identity assignments are carried over from Character Swap examples.

Default: camera-cut detection, max 4.5 seconds per shot, 0.4 MP, recursive processing and lossless shot cache.
Segmentation, masks, color guides and cropping are optional, not required for ordinary motion transfer.
The conditioning node's MODEL output reaches both guider and scheduler, including in TARA mode.
**BFS Shot Join is the output node:** it writes the final MP4 directly, with source audio and **crossfade 0**,
so no downstream video re-encode or extra Save Video is required. Camera-cut continuity is reset by the Planner.

## Comfy Kitchen works with TARA — use the modified temporal kernel

Guide Latents can use ordinary Comfy Kitchen attention. The TARA **one-pass Kitchen** implementation additionally
needs our modified temporal extension, consisting of both its binary library and Python API. Stock
`comfy-kitchen` alone does not contain that fused temporal operation.

The TARA examples default to **Flash partitions (no compile)** and PyTorch model attention, which does not
need the extension. To use Kitchen, select `comfy kitchen attention` in Model Attention Backend and
`comfy kitchen (experimental)` in the TARA node (native) or native-temporal backend (Planner conditioning).

With updated BFSNodes, supported Linux/Windows x86_64 NVIDIA setups can download and verify the pinned
extension automatically. A CUDA-13-capable driver is required; PyTorch itself may use CUDA 12.x.
Offline, unsupported or incompatible setups may retain a slower compatibility backend. Do not confuse a
successful import/render with confirmation of the fused kernel. Check the sampling console for:

```text
Kitchen ONE-PASS dense kernel ACTIVE
```

The separately supported Sol route reports `Kitchen ONE-PASS sol kernel ACTIVE`. These examples do not
add Sol, VSA or SLA patches. A binary for another GPU architecture is not a substitute for the matching build.

- [BFS setup, supported GPUs, limitations](https://github.com/alisson-anjos/ComfyUI-BFSNodes/blob/main/H3_NATIVE_TEMPORAL.md#kernel-downloads)
- [Manual Linux/Windows install](https://github.com/alisson-anjos/comfy-kitchen/blob/feat/h3-native-temporal/MANUAL_TEMPORAL_INSTALL.md)
- [Pinned release, manifest and SHA256 checksums](https://github.com/alisson-anjos/comfy-kitchen/releases/tag/temporal-native-0413d43878606425a84aa400f1e5da50ed9dcdad)

Published binaries passed build/ABI checks; not every GPU/OS combination has been validated with a full video.
Workflow structural/import validation is separate from generation-quality, memory and GPU-kernel validation.
