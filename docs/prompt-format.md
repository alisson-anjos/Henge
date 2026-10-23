# Kagemage H3 prompt format

The editor's Build prompt endpoint and the backend execution planner share one policy in `lib/h3-prompt-policy.json`. Enhanced output uses the six-section [MiniMax H3 full-reference format](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md). The application adds the task trigger used by its current LoRAs: `motion_transfer:` or `body_swap:`.

Plain instructions can still work with H3. This structure is the default for **generated/enhanced** prompts, not a claim that the model rejects ordinary text. When Enhance prompt is off, the application sends the user's editor text verbatim.

## Sections

1. `subject_definitions`: visible subjects, exact picture indices, distinct roles and guide-track bindings.
2. `summary`: requested output, scene/style edits and the role of the guide performance.
3. `retention_analysis`: the properties retained within each reference role and the performance transferred from the guide.
4. `detailed_description`: target scene, observable action progression, camera and interactions.
5. `overall_soundscape`: supported sound description, or `N/A` when unavailable.
6. `non_diegetic_music`: supplied/requested background music, or `N/A`.

The backend emits a picture-role inventory before composing its final prompt. Each reference is described separately. Picture count is not character count: several views can define one identity; clothing, environments and objects have their own roles. Supplied indices stay fixed, including when the setting is Picture 1 and the character is Picture 2. Color markers bind tracks and are not output skin or clothing colors.

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

The application and newly downloaded files use **Kagemage**. Existing browser storage keys, backend environment variables, ComfyUI class identifiers and repository URL are retained so that saved history and existing workflows remain usable.
