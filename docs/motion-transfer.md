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
| Edit task (First Frame) | `minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors` — [BFS LoRAs](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/loras/minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors): the VFX Edit first-frame LoRA ×1.0 + SolarRenderer control ×0.5, rank concat with per-module SVD keeping 99% of the Frobenius energy |
| Turbo for the Edit task | `solarrenderer/solarrenderer_4step_comfy.safetensors` — [BFS LoRAs](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/tree/main/loras/solarrenderer): SolarRenderer 4-step, ComfyUI H3 keys (5.9 GB) |
| Planner prompt VLM | `qwen3.5_9b_w4a8_gptq.safetensors` — [Comfy-Org MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/tree/main/text_encoders); choose another compatible generation-capable VLM if preferred |

Place base weights in `models/diffusion_models`, encoders in `models/text_encoders`, VAE in `models/vae`,
and LoRAs in `models/loras`. Select the installed name if files live in a subfolder. The encoder used for
prompt writing is separate from H3's own text encoder. Load the turbo and the task LoRA at strength 1; the
training adapter the LoRAs were trained over only counters distillation during training and is not loaded. The examples use DMD 8-step, Euler/simple, CFG 1. Do not stack a second copy of a component
that is already merged into your chosen weights.

## Motion Transfer FFP v1.0 and the First Frame

**FFP is First Frame Propagate.** You edit one frame of the guide — any frame, not only the first — and that image becomes
frame 0 of what the model renders; the model then rebuilds every frame after it around your image while the guide keeps the
motion, timing and camera. It is not image-to-video: the clip is regenerated with your frame inside it, so the edit does not
have to be re-applied frame by frame and does not drift back to the original look halfway through. In the studio the FFP
card is the control for that: choose a frame, edit it (by hand or with the frame editor), and the picture enters the job as
a native reference with its role named in the prompt
(`<Picture N> is the edited first frame of the video: propagate its changes through the whole clip while keeping the
original motion, timing and camera`).

Not every Motion model was trained for that, so the model picker carries **tags** instead of guesses:

| Tag | Meaning | Which model |
| --- | --- | --- |
| **FFP ✓** | trained for First Frame Propagate: an edited frame carries through the clip without drifting | Motion Transfer v1.0, Motion Transfer FFP v1.0 |
| **FFP ⚠** | takes an edited frame, but FFP is not what it was trained for: it can change more of the clip than the frame you edited | Motion Transfer TARA v1.0 |
| **multi-reference** | takes several reference pictures at once, each with its own job: person, place, look | Motion Transfer v1.0, Motion Transfer TARA v1.0 |
| **multi-reference · weaker** | trained with a single reference picture: it does take more than one, and how well they land is up to your prompt | Character Swap v1.1 |
| **one reference** | it works from a single reference picture | Head Swap v1.0 |
| **first frame only** | made only for a clip that starts from an edited first frame: it needs one | Motion Transfer SolarRenderer FFP v1.0 |

**Motion Transfer FFP v1.0** is our first-frame model: the VFX Edit first-frame LoRA (rank 128, trained to carry a
painted frame through a video) merged with SolarRenderer control at ×0.5 — rank concatenation, then a per-module SVD that
keeps 99% of the Frobenius energy (`minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors`, 220 MB). It runs with Guide
Latents and with TARA, and it is the model the studio picks by default when a First Frame is attached, because it is the one
merge here that carries SolarRenderer control. The merge already carries that control, so it does not stack the SolarRenderer step-
distillation turbo on top: it samples on the standard **DMAD 4-step** turbo (Kijai) like every other model, and any other
turbo stays selectable under Advanced.

**Motion Transfer SolarRenderer FFP v1.0** is SolarRenderer control on its own:
[Enderfga/SolarRenderer](https://huggingface.co/Enderfga/SolarRenderer)'s control LoRA (Apache-2.0) converted to ComfyUI
H3 keys, public in our repository as `loras/solarrenderer/solarrenderer_control_comfy.safetensors` (5.9 GB, model
profiles `ffp` and `solar`). `HengeSolarLoraLoader` also loads the release as published (diffusers names). It is always listed
but only for a clip that starts from an edited first frame: the studio and the bridge refuse to generate with it until a
First Frame is attached, and attaching one still selects Motion Transfer FFP v1.0 by default.

It runs on **SolarRenderer's own conditioning and sampler**, ported into the Henge nodes (`HengeSolarConditioning`,
`HengeSolarModel`), not on Henge's H3 conditioning:

- the prepared guide is the structure video `<Video 1>` and the edited frame is `<Video 2>`, held still; both are shown
  to H3's text encoder at 2 fps and laid over the target from frame 0 as keyframes (the guide over every frame);
- its four-step LoRA under the control LoRA, `lcm` on its shift-12 four-step grid with a `BasicGuider`, and the
  soundtrack held at H3's encoded silence, as SolarRenderer was trained (the Turbo, Method and CFG settings do not apply);
- its six-part prompt: `subject_definitions`, `summary` (your request), `retention_analysis`, `detailed_description`
  (the planner describes the edited frame's look and the action, 350-500 words), soundscape and music. A live-action
  guide is not one of its six trained structure types, so it is described with SolarRenderer's form for an untrained
  structure;
- shots are at most 158 frames (its training length). A continuing shot starts from the rendered frame where it begins;
  a shot after a camera cut has the structure only.

Motion Transfer TARA can also take a First Frame, and it often tracks it well — it is the multi-subject model, and it is
multi-reference like Motion Transfer — but it was trained for binding several subjects, not for FFP: the clip can come out
changed beyond the frame you edited. When the clip should start from an edited frame (typically the guide frame with
the character already replaced), that is the Motion Transfer FFP model, and the prompt is a single sentence rather than
the six-section one.

Whenever a **First Frame** is attached — a picture of the clip edited in advance, by hand or with the frame editor
(FIBO 2.0 by default, Qwen-Image 2.1 Turbo or FLUX Klein if installed) — the studio explains the picture's role in the prompt
and warns when the selected model is not tagged FFP. Removing the First Frame leaves the model choice as it is; picking
another model by hand is respected.

The guide stays the frame-by-frame tracing reference and enters as latents only, without the guide's frames reaching the
text encoder, so nothing of the original performer leaks back (see [conditioning paths](conditioning.md)).

The comparison LoRAs used while tuning this model — the dyn95 mixes and SolarRenderer control alone, kept under
`loras/experimental/` — were removed from the Hugging Face repository. A job rendered with them re-renders only where
those files are still installed.

## Writing the prompt

The studio puts example sentences under the prompt box, and they change with the model picked in the Motion dropdown.
They are deliberately narrow, because each model does exactly one job: **Motion Transfer** takes only the performance
from the guide and gets the people, the place and the look from up to 11 reference pictures, so the video is never a
copy of the guide; **Motion Transfer TARA** has the same goal through the experimental path and is the one to pick when
several people, objects or vehicles have to keep their identity, so its sentences name what each picture supplies;
**Motion Transfer FFP** names the edited first frame (`@PictureN`), who is replaced and what of the guide
stays. Clicking one drops it in, then **Improve** writes the full caption.

**Copying a performance** (Motion Transfer, Motion Transfer TARA). One English line saying what to take from the guide
is enough — `Improve` expands it into the six-part H3 caption the model was trained on (`subject_definitions`,
`summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`), and the plan shows
that caption for review before rendering:

```text
The target video follows the frame-by-frame structure and motion of @Video1: the same performance, timing and camera.
```

Name the picture that performs (`@Picture1`), say what changes (setting, style, wardrobe) and what stays (identity,
framing, camera path). With **Exact text** the same line is sent verbatim, so write it in the six-part form yourself in
that case.

**Starting from an edited first frame** (Motion Transfer FFP). Prompt it with one English sentence that names the
frame by its Picture tag, says who is replaced and what of the guide stays — no subject definitions, because the First
Frame already says who and where:

```text
Replace the character with the one in @Picture2, the edited first frame, keeping the guide's pose, motion, timing,
framing, lighting and background.
```

Henge adds the model's trigger itself and appends the First Frame clause naming `<Picture N>`, so the sentence only
carries the edit. Never ask to preserve the very thing being edited — a style change that says
“keep the lighting and colours” fights itself.

**The frame you edit is the strongest control there is.** Render starts from it and keeps its materials, colours and
light, so the edit must keep the guide's camera, layout, character positions, poses and facing, and change only the
look — Henge's frame editor states exactly that in its instruction, and an uploaded frame should follow the same rule.
A frame that moved the camera or the performer fights the guide latents. The upstream
[SolarRenderer prompt guide](https://github.com/Enderfga/SolarRenderer/blob/main/docs/prompts.md) documents the same
six-part form and the same first-frame rules, and its captioning skill is worth borrowing when a clip is stubborn.

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
