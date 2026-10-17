# Implementation roadmap

## Initial interface

Implemented: motion-transfer/swap selectors, local guide playback, 11 reference slots, mention insertion, H3 token conversion, manual prompting, server VLM route with an initial template, sampled guide frames, draft text persistence, direction JSON export, responsive UI.

## Workflow integration

Export the validated H3 API workflow and map guide video, ordered reference slots, prompt, LoRA, seed, resolution and duration. The guide must reach Add Guide as latents. Confirm the trained checkpoint's actual multi-reference and mode support. Wire submit, job progress, output retrieval and cancellation to a Comfy Developer Platform deployment. Do not infer inference compatibility from the UI's reference capacity.

## Subsequent milestones

- Finalize and evaluate both VLM prompt templates against the training prompt contract.
- Persist projects and media, job history, output comparison and reproducible retries.
- Add explicit in/out clip selection and then optional per-shot planning.
- Integrate sharpness and upscale passes after evaluating actual output quality; LTX integration is a separate candidate, not an implemented capability.
- Prepare reproducible deployment instructions, original demo assets and competition submission.
