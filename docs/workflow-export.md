# Re-run a Henge shot in ComfyUI

Use **Workflow (ComfyUI)** in History, the result download menu, or the `{ }` link on a finished shot.
The download is a ZIP containing:

- `workflow.json`: the editable ComfyUI workflow, with explicit reference connections and fixed seed controls.
- `workflow.api.json`: the same portable graph in API format.
- `original.api.json`: the graph originally submitted by Henge, for inspection.
- `input/`: the shot, continuity clip and prepared reference images used by that graph.
- `custom_nodes/henge/`: the runtime node code from the exporting Henge installation.
- `README.md`: installation steps, ComfyUI/BFS revisions, model names and download links.

Follow the included README, install the same model weights, copy the packaged inputs and Henge nodes into
ComfyUI, restart ComfyUI, then open **workflow.json**. Model weights are not inside the ZIP. Existing weights
with an older filename can be selected in their loader; the exported names match the public downloads.

The normal API graph remains available from `/jobs/{id}/workflow`. Do not use an API JSON import as a substitute
for opening the visual workflow: some frontend versions drop dynamic reference sockets or change seed controls
when importing API graphs.

## What is preserved

The exporter replaces the internal `HengeLoadShot` with a video loader with an upload button, and uses standard
**Load Image** nodes for references. The video loader keeps Henge's FFmpeg decoding, scaling, padding and frame
count; other video decoders can produce slightly different pixels.

`HengeH3Conditioning` expands into the native MiniMax H3 reference/guide nodes. The BFS Guide 0 CLIP Context node
is used when the guide also conditions the text encoder, or when more references are needed than the native
node advertises. TARA video references, continuity frames, audio conditioning, reference order and sampling
settings remain connected. Some guidance, masking and sampling nodes still require the included Henge code.

Each package reproduces **one stage**, not the complete multi-stage job. A later shot includes the continuity
clip that originally conditioned it. Re-running that shot does not generate its previous shots again.

Legacy graphs using unavailable/custom node types are rejected explicitly rather than exported with missing
connections. Their original API graphs remain in **Everything (.zip)** for inspection.

The same inputs, seed and settings do not guarantee pixel-identical results across GPU, driver, model weight
revisions or dependency versions. Use the versions in the README when comparing outputs.

## Validation and maintenance

The visual layouts in `config/workflow-node-layouts.json` describe the supported node sockets and widget order;
they contain no model inventories or machine-specific settings. When a supported node changes its inputs or
outputs, update its layout and verify a frontend import/export round trip before publishing.

Validation covers native prompt acceptance including the generated output, exact loader decode parity, fixed
seeds, dynamic references, input containment and exclusion of session notes from packaged node files. Frontend
round trips are checked without submitting inference. These checks establish graph/input preservation, not
cross-device numerical identity of a full model render.
