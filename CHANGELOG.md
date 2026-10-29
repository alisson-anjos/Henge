# Henge changelog

Newest changes first. Dates as `YYYY-MM-DD`.
This log starts with the 2026-10-28 updates; earlier commits remain in the Git history.

**Code published** means available on `main`. It does not mean the Docker image has finished building or that
Render and RunPod have been updated; each entry records those states separately. Test results are described with
their scope; CPU tests do not replace generation with the real models.

## 2026-10-29

### Full-video refiner: long videos are refined in chunks

- A 22 s Sharpness run (530 frames, 2K) with the segments → full-video refiner strategy killed the RTX 5090
  worker (`ComfyUI progress connection closed`) at the start of stage 2, after all seven first-pass segments had
  finished. Stage 2 held the first pass, the source guide at 1952×1088 and the decoded output in RAM at once,
  about 34 GB of frames on a 56 GB worker; the earlier validation used 124 frames.
- Videos longer than 243 frames (~10 s) now run stage 2 in chunks of at most 243 frames, cut at the joins between
  first-pass segments when possible, with context windows inside each chunk and no crossfade. Retry reuses the
  chunks already refined.
- **Component:** UI/bridge; no worker change.
- **Tests:** chunk planning (including the 22 s case), and a real-FFmpeg test that the chunked trim and join keep
  every frame in order and that Retry resumes. Not yet re-run on RunPod.

### Documentation in English; optional Portuguese guide

- All repository documentation is in English: README, changelog, temporal windows, Open-H3, RunPod and the
  visual guide (`docs/VISUAL-GUIDE.md`, formerly `docs/GUIA-VISUAL.md`).
- The in-app guide (**Tips**) is in English at `/guides/index.html`; the Portuguese version is kept as an option at
  `/guides/pt-BR/index.html` (and `docs/pt-BR/VISUAL-GUIDE.md`). The studio opens the Portuguese guide when the
  interface is in Portuguese. The guides no longer link to a fixed `localhost` address.
- **Component:** UI/bridge image (guide pages) and documentation.

### Default model profiles include `regenerate`

- The default Sharpness method (Open-H3 Refiner + LMS) now has its weights downloaded by default: `regenerate` was
  added to `HENGE_MODEL_PROFILES` in the Dockerfile, `scripts/runpod_template.sh`, `scripts/runpod_volume.sh` and the
  docs. It adds two files (the refiner LoRA and the native latent upscaler); DMAD and LMS come with `sharpness`.
- The live RunPod pod template was updated to the same list (it still listed `fibo`, removed from the defaults in
  `3aef7be`).
- **Component:** image defaults, pod template and docs. Existing pods and volumes keep their files; add the profile
  and restart to download it there.

### Refiner latent upscaler: base or Henge LMS v0.1

- The Open-H3 refiner stage can use our latent upscaler `h3_upscaler_lms_v0.1.safetensors` (LBH-123-AI base
  fine-tuned on the LMS data) instead of the base `minimax_h3_latent_upscaler_3d_conv_v1_bf16`. Default: base.
- Checked against ComfyUI's native loader: same detection keys, 12+12 blocks, 512 channels, temporal kernel 5.
  `/health` reports which refiner upscalers the backend has (`upscalers.refiner_upscalers`).
- **Component:** UI/bridge; the file is already in the `sharpness` profile (`latent_upscale_models/`).
- **Tests:** graph and option tests. Not yet compared visually against the base upscaler.

### Redo a shot with an adjusted prompt

- Redoing a shot opens an editor with the prompt it used, so that shot alone can be adjusted before generating
  again (e.g. "the camera is upside down: the character appears upside down"). Without a text change it redoes as
  before, only with a new seed. The other shots do not change.
- After a redo, the result, the comparison and the comparison with references are rebuilt and served fresh: the
  cached reference comparison is re-encoded when older than the result, and the download links carry a version.
- **Component:** UI/bridge (`GET /jobs/{id}/shots/{n}/prompt`; optional `prompt` in the redo); no worker change.
- **Tests:** reading the prompt, validation, and the new prompt in the redone shot's conditioning node.

### Sharpness: optional LMS in the Open-H3 refiner

- New switch **Add LMS on top of the refiner** (on by default, as before) and an LMS strength control in the
  refiner (0.1–1.5; default 1.0). Off, the second stage uses only the refiner and the turbo. It applies to the
  per-segment refiner and to the full-video refiner with context windows. First-stage LMS strength stays on the
  LoRA strength control.
- The switch and its strength slider sit together on one full-width row in the Sharpness panel; the slider is
  dimmed and disabled while the switch is off.
- **Component:** UI/bridge (builds the graphs); no worker change.
- **Tests:** graphs with and without LMS and the strength applied in both refiner paths. No visual comparison yet
  with LMS off or at reduced strength.

### Context windows — published and validated on Serverless

- Optional temporal processing for Character Swap, Motion Transfer, TARA, Head Swap and Sharpness.
- Pure windows evaluate overlapping segments at every step and combine the predictions before updating the global
  latent. Evaluations run one window at a time; predictions accumulate on CPU.
- Extra Sharpness strategy: normal segments with continuity in the first stage, assembly without crossfade, and the
  Open-H3 refiner over the full video with context windows in the second stage.
- Configurable window/overlap, initially 107/22 frames. Experimental options, off by default.
- An old worker keeps the option unavailable; unsupported combinations are validated explicitly.
- **Publishing:** code on `main`, commit `d1672fd`. Docker image published; Serverless worker on
  `henge:sha-d1672fd` and Render UI/bridge on `henge-ui:sha-d1672fd` (ComfyUI `35060f0`, BFS `6df4276`).
- **Tests:** logic tests, UI with Playwright and a reduced H3 on CPU passed, including the TARA wrapper on Flex.
  Real generation on RunPod Serverless, seed 42, all finished without errors:
  - Two-stage Sharpness (LMS per segment → Open-H3 refiner with 73/22 windows over the full video): 124 frames,
    1952×1088 output.
  - Refiner with windows over an existing Character Swap result: 124 frames, character, pose and background kept.
    Also completed through the normal UI flow on Render, with the comparison in the history.
  - Motion Transfer and Motion Transfer TARA, standard × 39/5 windows on 56 frames (two windows): same identity and
    motion; TARA with windows took 107 s against 227 s in this test.
  - No seam between windows: the largest jump in the overlap zone matched the version without windows (0.9–1.4×
    the median frame-to-frame change), below the clip's own motion peaks.
  - 22 s Character Swap (portrait, extreme close-ups, upside-down camera) with 107/22 windows in five shots:
    identity and motion held; the upside-down shot needed a prompt fix, which led to redo with a prompt.
- **Limits:** short clips for the measured comparisons (2.3–5.2 s); the timing comparison is a single run and peak
  VRAM was not measured.
- [Controls, how it works and limits](docs/temporal-windows.md).

### Shot joins and bridge restarts

- The bridge no longer loads both whole shots as RGB plus float copies in memory. Only the overlap is analysed, on
  thumbnails; FFmpeg processes the full frames by streaming.
- The direct cut, the duration and the single removal of duplicated frames are kept. No crossfade.
- The automatic colour adjustment was removed as well: each shot keeps its own colours.
- Both temporary outputs are checked before replacing the shot files.
- Recovered a test whose two shots finished on RunPod but whose bridge restarted after generation; the assembly was
  completed without repeating inference. Running out of RAM is a suspicion backed by the earlier join's usage; the
  restart cause was not confirmed by the Render logs.
- **Publishing:** commits `1ec3192` and `8dbff80` on `main`. The fix needs the **UI/bridge image on Render**; it
  does not need a GPU worker change.
- **Tests:** 145 tests on the stable version, 1 skipped; real FFmpeg coverage for duration, colour preservation,
  encode failure and overlap. Assembly of the recovered shots and a test with longer shots completed.
- [Diagnosis and update](docs/SERVERLESS.md#bridge-restarts-between-shots).

### Sharpness / Open-H3 and Motion Transfer workflows

- Selecting Open-H3 Refiner + LMS presets the first stage to DMAD, 4 steps and CFG 1; refiner steps stay separate.
- Fixed the layout of the Sharpness controls outside the Advanced section.
- Traditional per-segment refinement is capped at 107 frames to bound memory on long clips.
- Published four ComfyUI workflows: native and Planner for Motion Transfer Guide Latents and for TARA. References
  can have varied roles; one person picture plus one background picture is not required.
- Requirements aligned with the public BFS release. Documented the modified Comfy Kitchen temporal kernel needed by
  the matching TARA implementation.
- [Workflows](workflows/README.md) · [Motion Transfer](docs/motion-transfer.md) · [Open-H3](docs/open-h3-regenerate.md).

## 2026-10-28

### Open-H3 Refiner + LMS

- Added the upscale with Kijai's rank-16 refiner, the native latent upscaler and LMS loaded separately.
- Kept the existing Ref2VA base; no FL2VA dependency was added.
- Add Guide uses the original video to drive the second pass. Refiner + LMS became the default Sharpness upscale,
  with 1080p/2K output.
- Optional refiner prompt exposed in the main panel. Without a manual description, the flow can ask for an
  automatic scene description.
- Fixed the creation of the isolated Molmo environment in Docker and the RunPod Click dependency resolution.
- Documented downloads on the Serverless volume and the inventory refresh: updating the UI does not install
  nodes/weights on the worker; setting profiles on the worker does not fill the volume automatically.

### Characters, shots and interface

- Recommended TARA with its matching LoRA for colour marks. Character Swap can work with multiple characters, but
  depends especially on how the references are described and bound in the prompt.
- Improved per-shot identity binding when characters change position or appear later.
- Exposed seed controls to compare generations with reproducible settings.
- Kept the assembly without crossfade after a favourable visual comparison.
- Added the visual guide, tips with Playwright screenshots and instructions to update the UI on Render.
- [Visual guide](docs/VISUAL-GUIDE.md).

## Keeping this log

- For each relevant change, record the date, the changed behaviour and the reason.
- Say which component it affects: UI/bridge, worker, models, workflows or documentation.
- Distinguish code on `main`, published image, completed deploy and completed test.
- Update the entry when a pending test or deploy finishes, with the result and limitations.
- Reference commits and documentation; never include credentials, tokens or private job data.
- Write entries in English.
