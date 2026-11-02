# Motion Transfer workflows

| LoRA / conditioning | Native H3 / automatic or manual prompt | Planner / automatic prompt |
| --- | --- | --- |
| Motion Transfer v1.0 · Guide Latents | [Download JSON](minimax_h3_motion_transfer_workflow_native_nodes_v1.0.json) | [Download JSON](minimax_h3_motion_transfer_workflow_planner_v1.0.json) |
| Motion Transfer TARA v1.0 · native Video 1 + temporal alignment | [Download JSON](minimax_h3_motion_transfer_tara_workflow_native_nodes_v1.0.json) | [Download JSON](minimax_h3_motion_transfer_tara_workflow_planner_v1.0.json) |

**Native workflows** (Guide Latents and TARA, for the v1.0 LoRAs): built on the Character Swap v1.1 native graph (same models, controls, optional LMS
upscale second pass and comparison). Pictures 1-4 (2-4 start disabled: select a picture's nodes and press Ctrl+B), an
automatic prompt (Qwen 3.5 describes the guide from one frame per second, then writes the six-part motion_transfer prompt
from the pictures, deciding each picture's role and the setting: your request, else an environment picture, else the scene
a character picture shows, else the guide), a manual-prompt switch, and references at `ref_image_size = max` capped at 1 MP.
No training adapter node: it is merged into the motion LoRAs.


**References are 1..N pictures with roles assigned by the prompt. A separate background image is not required.**
They can be multiple characters, multiple views of one identity, clothing, objects, scenery or style references.
Picture count does not imply performer count. No automatic background stripping is enabled.

See [setup, models, prompts and the modified Comfy Kitchen kernel](../docs/motion-transfer.md).
Native examples use native H3 conditioning, small public BFS helpers and VideoHelperSuite; no private Henge nodes.
Planner examples split long videos, generate prompts and join shots with crossfade disabled.
