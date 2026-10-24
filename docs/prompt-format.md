# Kawarimi H3 prompt format

The editor's Build prompt endpoint and the backend execution planner share one policy in `lib/h3-prompt-policy.json`. Enhanced output uses the six-section [MiniMax H3 full-reference format](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md). The application adds the task trigger used by its current LoRAs: `motion_transfer:` or `body_swap:`.

Plain instructions can still work with H3. This structure is the default for **generated/enhanced** prompts, not a claim that the model rejects ordinary text. When Enhance prompt is off, the application sends the user's editor text verbatim.

## Sections

1. `subject_definitions`: visible subjects, exact picture indices, distinct roles and guide-track bindings.
2. `summary`: requested output, scene/style edits and the role of the guide performance.
3. `retention_analysis`: the properties retained within each reference role and the performance transferred from the guide.
4. `detailed_description`: target scene, observable action progression, camera and interactions.
5. `overall_soundscape`: supported sound description, or `N/A` when unavailable.
6. `non_diegetic_music`: supplied/requested background music, or `N/A`.

The backend and editor automatic-prompt endpoint now use the same staged sequence as the recent BFS native workflows: one isolated image per reference-description call, a guide-only analysis call, then a text-only H3 composition call. The backend runs a separate text-only runtime-routing call afterward; it cannot overwrite the composed execution prompt. Each reference is described separately. Picture count is not character count: several views can define one identity; clothing, environments and objects have their own roles. Supplied indices stay fixed, including when the setting is Picture 1 and the character is Picture 2. Color markers bind tracks and are not output skin or clothing colors.

A requested environment replaces the entire source setting, including incompatible room walls, floor and ceiling. Keep only the specified interaction props and contacts. Preserve performance timing and source camera behavior unless the user explicitly changes the camera. Avoid blanket preservation instructions that contradict a requested background or style change. Prompt structure cannot guarantee model compliance or compensate for inadequate conditioning.

## Example: pianist, creature and beach

This example follows the user's described references; it is not a claim that the application inspected these assets.

```text
motion_transfer:
subject_definitions: <Subject 1> is the bald humanoid creature with sunken eyes, a bulbous nose, tattered brown loincloth and arm wraps from <Picture 2>. <Subject 2> is the sandy beach environment with gentle ocean waves, distant snow-capped mountains and a coastal cityscape from <Picture 1>. <Video 1> supplies the original pianist's performance, action timing and camera trajectory.
summary: [reference generation] Animate <Subject 1> with the pianist's performance from <Video 1>, using <Subject 2> as the complete target setting. Retain the piano and the performer's interaction with it.
retention_analysis: <Subject 1>: fully_preserved - keep the referenced identity, body appearance and clothing stable throughout the clip. <Subject 2>: fully_preserved - retain the beach setting and its distinctive landscape elements as the target environment. <Video 1>: attribute_transfer - transfer the action order, timing, gestures, head motion and visible mouth performance without retaining the old stage.
detailed_description: [Shot 1] <Subject 1> occupies the original performer's place at the piano in the beach setting defined by <Subject 2>. Match the original piano-playing gestures, hand contact with the keys, body movement, head turns and visible singing mouth shapes with the same timing. Adapt the motion to the creature's anatomy while maintaining its reference appearance. Preserve the source camera movement and framing. Replace the entire stage environment with the beach, including any incompatible walls, ceiling and floor. Integrate the performer and piano with coherent daylight, shadows and perspective. Keep the reference-to-subject and reference-to-setting assignments fixed throughout the video.
overall_soundscape: N/A
non_diegetic_music: N/A
```

The prompt writer only receives visual samples in the current application, so it does not invent dialogue, lyrics, notes or sound effects. Source audio reuse and audio conditioning are separate runtime options.

Generated prompts are checked for the task trigger, all six nonempty sections in order, and unattached picture references. These checks validate format and slot existence; they do not prove that a VLM described each image correctly. The execution plan exposes its picture-role inventory and exact H3 prompt for review.

## Branding compatibility

The application and newly downloaded files use **Kawarimi**. Existing browser storage keys, backend environment variables, ComfyUI class identifiers and repository URL are retained so that saved history and existing workflows remain usable.

## Staged VLM evidence (updated pipeline)

`lib/h3-prompt-policy.json` is synchronized to the BFS native workflow policy v3,
including explicit preservation of the observed source background when the user
does not request a setting change. `lib/h3-vlm-stages.json` shares the reference,
guide, composition context and final consistency-check wording across Python
and the editor endpoint. No token/embedding-weight feature is part of this change.

The backend resizes each analysis reference independently to at most 1024px,
without changing the original generation reference. Up to 12 labelled guide
frames from the selected interval form a separate contact sheet. Reference
pictures never appear in that guide sheet. Composition receives descriptions,
guide observations, request/bindings, exact Picture indices and video metadata;
it receives no combined media collage. No audio is sent to the visual planner.

A plan retains `prompt_evidence` and stage-specific `.txt` / `.api.json` files
for review. Runtime species/FIBO/prop decisions remain separate from prompt
writing. Enhancement OFF skips composition and preserves the exact user string.
Guide Latents remains the existing generation path; this prompt update does not
silently enable TARA or change LoRA profiles.

Local calls use `thinking=false`, independent descriptions with a 384-token
budget, guide analysis 1024 and final composition 3072, matching the recent BFS
workflow budgets. Optional `KAWARIMI_VLM_CLIP` selects an installed local VLM
checkpoint (for example the user's `qwen3.5_9b_w4a8_gptq.safetensors`); the existing
4B filename remains the default. The VLM's actual weights/model matter too: this
pipeline change alone does not prove equal outputs across different VLMs.
Restart the backend and rebuild/restart the frontend after updating; running
services do not hot-load these Python changes.

## UI conditioning choice

The generation panel now offers **Guide Latents** (unchanged default) and
**TARA · experimental** when the connected ComfyUI registers the BFS TARA node.
TARA routes native Video 1 conditioning and the patched MODEL to both guider and
scheduler, with no Add Guide call. Native reference scale can be reduced
independently of output resolution. Native Qwen video context uses its standard
2fps; the Guide-only CLIP FPS control is disabled while TARA is selected.

Guide continuity retains its existing overlap guide. TARA continuity appends the
previous generated last frame as a native image, never as a latent head guide.
Its shot-level prompt annotation is included only with enhancement enabled;
raw prompt text remains unchanged. Native audio conditioning uses the guide
video's native audio-reference channel; output soundtrack reuse remains separate.
These branches are CPU-contract tested; real UI/GPU evidence is collected in the
integration test report rather than assumed from static tests.

ComfyUI must load BFSNodes alongside the Kawarimi custom nodes for TARA. The
launcher whitelist now includes `bfsnodes`; install/symlink that plugin under the
same name or adapt the whitelist to your real folder name. Do not keep duplicate
BFS copies. Existing LoRA profile paths/defaults were not changed by this option.

### Reference preparation review

Reference preparation is automatic by default, with an off switch under Advanced.
The planner recommends adaptation when an animal reference needs to follow a
human guide (or another supported anatomy mismatch). A normal human-to-human
swap, unusual hair, wardrobe or makeup does not activate it automatically.
After analysis, the execution plan explains the recommendation and offers
**Adapt reference** or **Use original image** before approval. FIBO prepares an
additional image; it never overwrites the uploaded original. This is a pose and
appearance aid, not a guarantee of anatomical or temporal alignment.

### Tasks and motion models

**Character Swap** uses the published v1.1 LoRA without a model selector.
**Motion Transfer** offers Original 10500 and TARA-trained 4500. Either motion
LoRA can use Guide Latents (default) or TARA (experimental), independently of how
it was trained. The method selector is visible for both tasks. Reference scale, seed and
sampling controls are under Advanced. These combinations are wired and covered by CPU contracts; visual
quality still requires real inference checks.
