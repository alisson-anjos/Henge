# Native H3 workflow: automatic prompts and video-derived dimensions

Requires BFSNodes **1.115.21+**, current ComfyUI native MiniMax H3 + Generate Text, and VideoHelperSuite. This is a standalone workflow, not Planner state. TARA remains opt-in; existing Planner defaults stay Add Guide.

The examples use the **native H3 reference conditioning contract**, with public BFS glue nodes for dynamic reference sets and geometry. They are not entirely Comfy core: VHS loads the video and BFS provides preparation, per-picture analysis, template assembly, reference-set encoding and the TARA MODEL patch. There is no private `H3BenchConditioning` dependency.

## Pipeline

1. **VHS Load Video** decodes/resamples the selected clip to 24 fps. Its default custom width/height are zero (source dimensions), no frame cap. Set its skip/cap explicitly when you want an interval.
2. **BFS H3 Prepare Native Video** reads the actual loaded NHWC tensor. Source dimensions determine portrait/landscape orientation; `output_scale` and `max_megapixels` determine output size, floored to multiples of 32. `reference_scale` independently reduces only the native video reference. Grid rounding may slightly change aspect ratio; this node resizes rather than adding black borders.
3. Source frame count at 24 fps determines `length`. Default `pad last frame` repeats the last frame only to reach `17n+5`; **ImageFromBatch after decoding trims the generated result to actual source duration**. `trim tail` is an explicit alternative. Metadata preview reports source/output/reference sizes, frame count, padding and any requested cap.
4. **BFS H3 Describe References** accepts 1..9 single images. It calls Comfy's **Generate Text** independently for each image and returns both the labelled inventory and the original image set. Reference analysis uses at most 1024px on its longest side by default; original images stay available to H3. No joint reference collage is used.
5. Native **Generate Text 1** sees a timestamped contact sheet of up to 12 evenly spaced guide frames (adjustable 2..32) and describes only the source performance. This is sampled visual evidence, not continuous tracking or audio understanding.
6. **BFS H3 Build Native Prompt** combines the user request, actual inventory, source observations and metadata using an editable, populated six-section H3 template. Mode fixes the required `motion_transfer:` or `body_swap:` prefix.
7. Native **Generate Text 2** writes the final English prompt. A preview exposes the actual string. Its default budget is 3072 tokens, deterministic sampling, thinking off and MTP off. Increase the budget if a selected VLM truncates the six sections. The prompt VLM is independent of H3's text encoder; choose a generation-capable model installed locally.
8. **BFS H3 Native Reference Set to Video** passes exactly that same image set, generated prompt and prepared `<Video 1>` to Comfy's native **MiniMax H3 Reference to Video**. It validates six nonempty sections, attached picture indices and video/frame-grid consistency. It never applies Add Guide. The separate TARA MODEL output goes to the guider/scheduler.

## Adding N references

The supplied visual graph starts with one connected LoadImage (Picture1); a second LoadImage is present but unconnected and marked optional. Connect additional LoadImage nodes to `ref_image_2` ... `ref_image_9` on **Describe References**. Only one connection per additional image is needed: that node returns the same set to the native encoder automatically. The inventory and template expand to the actual count. With one image, leave the default request using Picture1. If you want a background from Picture2, connect that second reference and explicitly request the scene change. The request itself must identify the intended roles; pictures do not prescribe an edit automatically.

Connect consecutive slots 1..N. Gaps are explicitly rejected: the current native H3 encoder numbers references in insertion order rather than preserving numeric gaps. Rejecting holes prevents silent Picture3→Picture2 identity errors. This standalone workflow does not reinterpret the separate UI's persistent sparse slot scheme.

Several reference pictures can describe a single identity, outfit or environment. Do not bind them to performers merely by count. The VLM template separates identity, outfit, scene, style and object roles and keeps the guide performance distinct. These instructions reduce ambiguity; they are not proof of correct visual bindings. Always inspect the inventory/final prompt when a result is wrong.

## Size, duration and memory

Defaults are source-derived output, maximum **0.4 MP**, reference scale **1.0**, and full loaded duration (`max_frames=0`). Thus resolution changes with each source; there is no fixed512×288 canvas. Use output_scale below1 or a smaller megapixel cap to reduce cost, and reference_scale0.75/0.5 only when the loss of guide detail is acceptable.

The VHS loader decodes the clip before these controls run. Long/high-resolution sources may exhaust **CPU RAM** even with a small output budget. Native reference attention and frame count can exhaust **VRAM** independently of output area. Start with a short clip on a5090, use VHS frame cap/trim for large files, and use the Planner/context-window workflow for long sequences. This standalone graph does not split or stitch shots automatically. The H3 core accepts up to3600frames in its schema; that is not a feasible-memory or trained-quality guarantee. Training coverage is narrower. FPS normalization/padding can only align timestamps, not guarantee generated motion or identity.

Output is silent24fps. No generated dialogue/music is inferred from visible mouth movement or piano playing. Audio conditioning and original-audio muxing require separate, aligned branches.

## Models and switching modes

The TARA example loads training adapter V2 and then Motion Transfer TARA v1.0, both at strength 1. Model filenames must be adapted to local inventory. Default prompt VLM is the development environment's generation-capable Qwen3VL4B; it can be replaced with a compatible installed VLM. H3 TE remains its own native encoder.

TARA does not load LoRAs or perform conditioning by itself. The wrapper retains native reference video latents; no Add Guide is present. Bypassing the TARA patch gives native-reference inference without temporal alignment, not Guide Latents. For Guide Latents, use the separate guide workflow; do not silently change contracts.

The default patch backend is Flash partitions. Optional Kitchen/sparse backends follow the existing TARA compatibility documentation. No GPU benchmarks or package installation occur when importing these helper nodes.

## Validation

CPU tests cover actual source dimensions, portrait/landscape, FPS conversion, grid trim/pad and final-duration trim count, explicit caps, independent per-image calls, ordering/gap rejection, prompt templating without recursive substitution, six-section checks and delegation of the same reference set to the native H3 encoder. Structural checks cover visual/API link consistency. These do not establish semantic caption quality or a successful5090 render. Local GPU and browser validation remain required.

The policy snapshot is `h3_native_prompt_policy.json`, copied from Henge's shared H3 policy at implementation time. It is packaged locally, so BFS does not require the UI repo or make a network request to load rules. Keep the snapshots in sync when intentionally changing prompt policy.

### Request/reference mismatch and saved workflows

Version1.115.21 checks requested Picture indices **before** per-image VLM generation, lists the exact attached set in the final writer instruction, and reports available slots in errors. Older saved examples may still contain `and the entire setting with <Picture 2>` in Prepare Native Video → request. With only Picture1 connected, remove that clause (or connect the intended second image), then regenerate. Updating the plugin does not overwrite a saved user request/template. Final instructions also separate source observations from target clothing and setting; source hoodies/pants must not override the assigned reference outfit. These are instruction improvements, not a guarantee of semantic correctness.

## New public workflow set

Use the [four Motion Transfer examples](../README.md) for matching Guide Latents/TARA LoRAs, native/manual and Planner/automatic variants. Reference slots are generic 1..N pictures, not a required character/background pair. See [Kitchen modified-kernel setup](../../docs/motion-transfer.md#comfy-kitchen-works-with-tara--use-the-modified-temporal-kernel).
