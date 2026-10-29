# Motion Transfer workflows

| LoRA / conditioning | Native H3 / manual prompt | Planner / automatic prompt |
| --- | --- | --- |
| Motion Transfer v1.0 · Guide Latents | [Download JSON](minimax_h3_motion_transfer_workflow_native_nodes_v1.0.json) | [Download JSON](minimax_h3_motion_transfer_workflow_planner_v1.0.json) |
| Motion Transfer TARA v1.0 · native Video 1 + temporal alignment | [Download JSON](minimax_h3_motion_transfer_tara_workflow_native_nodes_v1.0.json) | [Download JSON](minimax_h3_motion_transfer_tara_workflow_planner_v1.0.json) |

**References are 1..N pictures with roles assigned by the prompt. A separate background image is not required.**
They can be multiple characters, multiple views of one identity, clothing, objects, scenery or style references.
Picture count does not imply performer count. No automatic background stripping is enabled.

See [setup, models, prompts and the modified Comfy Kitchen kernel](../docs/motion-transfer.md).
Native examples use native H3 conditioning, small public BFS helpers and VideoHelperSuite; no private Henge nodes.
Planner examples split long videos, generate prompts and join shots with crossfade disabled.
