# Henge changelog

Newest changes first. Dates as `YYYY-MM-DD`.
This log starts with the 2026-10-28 updates; earlier commits remain in the Git history.

**Code published** means available on `main`. It does not mean the Docker image has finished building or that
Render and RunPod have been updated; each entry records those states separately. Test results are described with
their scope; CPU tests do not replace generation with the real models.

## 2026-11-01

### Character Swap takes a First Frame too, and a First Frame now opens the guide
- The **FFP card** now shows in Character Swap. Its frame editor opens in a **Swap character** mode: pick any guide
  frame, press **Segment the characters (SAM 3.1)**, hover to highlight a segment and click the one to replace; it is
  painted magenta on the frame. The image editor then gets "replace the character marked in magenta with the
  character from image 2" (the chosen character Picture) or, with no picture, with the character described in the
  text box, keeping pose, gaze and scene, and removing the marker. Changing the frame drops the segments: segment
  again. Without segments you can name who to replace instead, and *Upload edited image* still takes a frame you
  swapped elsewhere. *Describe* stays for any other change.
- The prompt the image editor gets is shown in the modal, in English, built from those choices (`GET
  /frame-edit/instruction`), and can be rewritten; a rewritten prompt is sent as is (`prompt` field) until *Reset to
  default*. This works in every edit mode, not only Swap character.
- In Character Swap the edited frame is **not a Picture**: it is sent as its own file (`first_frame`, request flag
  `guide_first_frame`), so all reference pictures stay available for the character.
- **Use the frame as** (FFP card, Character Swap and Motion): **Guide frame 0 (first latent)**, the default, or
  **Reference only**. Frame 0 means `HengeH3Conditioning` replaces the first frame of the guide the model reads with
  the edited image (cover-fitted), so the guide's first latent is that image and the render follows it. It happens
  inside the conditioning node, after `HengeGuide`, so SAM tracking and 2D/3D marks still run on the source frames.
  Works in Guide Latents and TARA, first shot only. Motion keeps its First Frame Picture as well (the FFP LoRAs were
  trained with it as a reference); *Reference only* is the previous Motion behaviour. In Character Swap, *Reference
  only* sends the frame as the Picture after the character pictures. The swap prompt gets one sentence saying the
  guide opens on the edited frame (or naming that Picture).
- **The assistant offers it.** New studio tool `swap_first_frame` (time, swaps: [{character, picture | description,
  optional English prompt}], use_as): it segments the frame with SAM 3.1 and swaps every listed character in one call,
  each edit made on the previous result with that character painted magenta, then sets the frame as Character Swap's
  first frame and starts the interval there. `find_people` takes `kind: character` to show the same numbering. The
  system prompt tells the assistant to offer this when configuring a Character Swap and to use it for one or several
  characters; `get_studio_state` reports `first_frame`. MCP `create_job` takes `first_frame` (path of an already
  swapped frame, Character Swap) and `first_frame_mode`.
- Building blocks for the assistant, so it is not limited to that recipe: `edit_frame` (source = a guide time, an
  earlier edit or a Picture; op swap/replace/remove/add/free; optional character number painted magenta, reference
  Pictures, its own English prompt and editor; edits chain by id), `use_frame` (an edit or Picture as Character Swap's
  guide first frame, Motion's First Frame, or a new Picture; latent or reference) and `clear_first_frame`.
- `HengeFindPeople` has a third output, a label map (red = subject number), and a `character` kind (person + animal,
  overlapping duplicates dropped). `/assistant/people` returns it with `labels=1`.
- **Workers need a new image** (`HengeH3Conditioning.first_frame`, the label map); an old worker refuses the
  `first_frame` input and the editor falls back to naming the subject.
- Validation: contract tests (requests, prompts, graph, edit instructions), TypeScript, a CPU check that the node
  replaces only frame 0 of the guide tensor. **Not yet run** in the real UI (Playwright) or with a real SAM 3.1 /
  editor / H3 render.

### The model picker says what each model was trained for
- The Motion dropdown now shows **tags** on every model, taken from the backend (`MODELS[..]['tags']`) so the studio
  never claims a capability the LoRA does not have: **Motion Transfer v1.0** `multi-reference`, `FFP ✓`;
  **Motion Transfer TARA v1.0** `multi-reference`, `FFP ⚠`; **Motion Transfer FFP v1.0** `FFP ✓`; Character Swap v1.1
  `multi-reference · weaker`; Head Swap v1.0 `one reference`. `multi-reference · weaker` is the honest version of
  "one reference": those LoRAs were trained with a single picture, they do take more than one, and how well that works
  is up to your prompt. Tags that mark a limitation (the ⚠ tags and the weaker reference tags) are amber instead of
  accent, and hovering a tag gives the reason.
- The selected model's tags are spelled out in full under the picker. The wording lives in `lib/model-tags.json`, in
  English, Portuguese and Spanish, and a test fails if the backend names a tag that any language does not explain.
- **FFP = First Frame Propagate** is now explained where it is used, in the FFP card and in
  [docs/motion-transfer.md](docs/motion-transfer.md): you edit one frame of the guide, that image becomes frame 0 of
  the render, and the model rebuilds every frame after it around your image while the guide keeps motion, timing and
  camera. It is not image-to-video — the clip is regenerated with your frame inside it, so the edit is not re-applied
  frame by frame.
- TARA keeps its First Frame behaviour but is labelled honestly: it propagates an attached frame, it was not trained
  for FFP, and it can change more of the clip than the frame you edited. Motion Transfer v1.0 and Motion Transfer FFP
  are the two trained for it, and the merge with SolarRenderer control stays the model an attached First Frame selects
  by default.


### A dropped progress feed no longer kills a running render
- The live feed from ComfyUI (`/ws`) is now **reconnected** when it drops: a reverse proxy restart, a sleeping
  laptop, a hosted gateway closing an idle socket or ComfyUI's own websocket timeout used to end the job with
  "ComfyUI progress connection closed" even though ComfyUI was still rendering. Samples, step counts, previews and
  the ETA come back after the reconnect; messages missed during the gap are skipped, and the two-second history poll
  finishes the render either way.
- The job says "the live feed from ComfyUI dropped; reconnecting (the render continues)" once per drop.
- Giving up is now explicit and conservative: after 4 minutes without the feed the bridge asks ComfyUI whether the
  prompt is still running or queued. It reports a restart only when ComfyUI says the prompt left its queue
  ("ComfyUI restarted during this render"), and reports the backend as unreachable only after 10 minutes with both
  the feed and the API down. A ComfyUI that is merely slow, or an API call that fails once, never fails the render.

### The model becomes Motion Transfer FFP, and the prompt examples follow the model
- **Renamed.** *Motion Transfer / Edit Anything v1.0* is now **Motion Transfer FFP v1.0**, and it is talked about as
  what it is: the first-frame model. `Edit Anything` is dropped from the label and from the copy — the way to use this
  model is to **change a frame** (draw on it, restyle it, add or remove something in the picture) and attach it as the
  First Frame; the model propagates that frame through the clip. The prompt then describes the change in one sentence,
  it does not do the editing. The profile key (`motion_mix_dyn99`) and the LoRA file stay, so old jobs and settings
  resolve.
- **Examples follow the model.** The sentences under the prompt box used to be identical for every Motion model. They
  now change with the model picked in the dropdown: **Motion Transfer** gets "follow the frame-by-frame structure and
  motion of @Video1" lines, **Motion Transfer TARA** gets sentences naming the picture that replaces each performer
  (`Replace the man with @Picture1, keeping ... the camera of @Video1`), and **Motion Transfer FFP**
  gets edit sentences — the change first, then what has to survive it. The hint under them explains the form in your
  language, and the block disappears for models with no recipe of their own.

### Put FIBO 2.0 back as the image editor, with Qwen-Image 2.1 as an optional fast one

- Frame and picture edits use **FIBO 2.0 edit turbo** by default again. **Qwen-Image 2.1** is an optional editor you
  pick per edit in the First Frame modal, and **FLUX.2 [klein]** / **FLUX.3 [image klein]** stay as fallbacks with
  FLUX.3 last. `HENGE_FRAME_EDITOR=fibo|qwen21|klein|klein3` moves one editor to the front.
- Why FLUX.3 stopped being the default: its graph feeds the frame in as multi-reference conditioning
  (`ReferenceMultiLatent` at about one megapixel) and samples an **empty** latent at `denoise=1`, so it re-draws the
  shot instead of editing it, and the first-frame model carries that re-drawing through every later frame. FIBO 2.0
  (`TextEncodeFibo2`) samples the latent of the frame it is given and conditions positive *and* negative on it, and
  Qwen-Image 2.1 (`TextEncodeQwenImage21`) returns a latent at the first reference's size — Henge passes
  `resolution=0`, so the result keeps the guide frame's own size and stays pixel aligned.
- Editors are now a registry (`frame_editors()`, `frame_editor_choices()`, `EDITOR_GRAPHS`): `/frame-edit` accepts an
  `editor` field and rejects one this ComfyUI does not have, the hidden frame-edit job records which editor produced
  it, the reference-adaptation cache key changes with the editor, and `/health` reports the default plus every editor
  with its install state. A serverless worker that has not listed its files yet assumes the editors of its image
  instead of hiding the frame edit.
- Qwen-Image 2.1 speed: the 7.3 GB **Turbo** checkpoint is used when installed (8 steps, CFG 1, `deis_2m`/`simple`);
  otherwise the 335 MB `p_q_image_2.1_5_steps_v0.1_comfyui_bf16.safetensors` LoRA puts the full checkpoint on the same
  5-step CFG 1 schedule, and only an install with neither samples 24 steps at CFG 2.5. The `qwen21` download profile
  carries the checkpoint, its Qwen3-VL 8B encoder, its VAE and that LoRA; the default profiles now ship `fibo` in
  place of `klein`.
- The First Frame modal names the installed editors as chips and says what each is good at, instead of assuming FLUX
  Klein everywhere.
- **Components:** editor registry and graphs, request defaults, adaptation cache, download manifest and profiles,
  First Frame modal, studio copy, health contract, RunPod/serverless tables and model documentation.
- **Validation:** 241 CPU tests passed, 4 skipped; `tsc --noEmit` and `npm run build` passed; two Playwright tests
  pass against the local stack, and that run now performs a real FIBO 2.0 frame edit through the backend and uses the
  result as the first frame. Both editor graphs also ran on a real ComfyUI (1276×718 guide frame: FIBO 2.0 in 57 s,
  Qwen-Image 2.1 with the 5-step LoRA in 49 s). Per-edit visual quality on your own clips still needs a look in the
  interface.
- **Release:** code published on `main` as `v2026.11.01`; the tag triggers the Docker image build.
  Image publication and deployment are pending.

## 2026-10-31

### Surface the first-frame edit model as Motion Transfer FFP v1.0

- The Motion model dropdown now offers exactly three models: **Motion Transfer v1.0**, **Motion Transfer TARA v1.0**
  and **Motion Transfer FFP v1.0**. The dyn95/dyn99 comparison mixes, the older First Frame profile and the
  SolarRenderer-only profiles are no longer offered, while their profile keys still resolve for saved jobs and shared
  settings. The Edit model keeps the internal key `motion_mix_dyn99` and now points at
  `minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors`, promoted from `loras/experimental/` in the Hugging Face
  repository; the two combined mixes and the rest of `loras/experimental/` were deleted there.
- Attaching a **First Frame** selects the Edit model: the studio, the backend request defaults and the assistant
  (`set_first_frame`, which can also edit a guide frame with FLUX Klein first) all converge on it, and the model is
  discovered through its `ffp` flag instead of a hard-coded name.
- Turbo defaults are now per model: `DEFAULT_TURBO` is `dmad4`, and the Edit model declares `turbo_default`, so the
  first-frame merge samples on **DMAD 4-step (Kijai)** like every other model instead of stacking SolarRenderer control
  twice. SolarRenderer 4-step remains an optional speed LoRA under Advanced → Turbo LoRA, and the download manifest
  keeps offering it with the First Frame model.
- The prompt box now teaches the two prompt shapes: example sentences that drop straight in (copy the motion / change
  the setting / restyle it, or, for an edit, the change first and then what must survive it), a first-frame-aware
  placeholder, and a frame-editor instruction that locks camera, framing, placement, size, outline, pose and facing so
  an edited frame does not fight the guide latents. `docs/motion-transfer.md` gained a *Writing the prompt* section
  covering the one-line-plus-Improve flow and the `vfx_edit:` sentence form.
- **Fix:** removing an earlier reference picture closed the gap everywhere — First Frame mark, subject bindings,
  `@PictureN` tags in the prompt, recommended slots and the persisted first frame — instead of leaving the edited frame
  marked as `Picture 3` and failing with “reference indices cannot be silently renumbered”.
- **Recent edits** shown in the First Frame modal can be deleted: `DELETE /api/backend/frame-edits` removes the stored
  frame-edit records, edited pictures and staged inputs without touching normal generations.
- **Components:** model profiles and manifests, request defaults, studio model picker and prompt coaching, First Frame
  modal, assistant tools, download manifest, legacy alias table, documentation and tests.
- **Validation:** 236 CPU tests passed, 4 skipped; `tsc --noEmit` and `npm run build` passed; two Playwright tests pass
  against the local stack — the health contract exposes exactly the three Motion models with the FFP flag and the
  `dmad4` turbo default, and the picker offers them, follows an attached/uploaded First Frame to the Edit model, keeps a
  manual choice, and switches the prompt coaching to the edit examples. CPU validation does not replace generation with
  the real models.
- **Release:** code published on `main` as `v2026.10.31.3`; the tag triggers the Docker image build.
  Image publication and deployment are pending.

### Offer official and Kijai Pika Ref2VA adapters

- Pika now downloads and selects the official full-rank Comfy BF16 adapter from Pika-Labs/Pika-H3-Flex,
  pinned to revision `0ddf55ad7067ca1e76812253bd7b4600df87f759` with the official SHA256 checksum.
  The reduced adapter remains a separate selection explicitly labeled Kijai (`pika6_kijai`).
  Both use the Pika sampling preset, with independent installation detection and no file alias.
- **Components:** download manifest, workflow model selection, model availability and documentation.
  Existing official files are reused; installations containing only the reduced adapter must install the
  approximately 1.96 GB official file. Sampling settings are unchanged.
- **Validation:** 18 CPU tests passed for Pika sampling/download contracts, model installation, requirements
  and workflow export; TypeScript `tsc --noEmit` and `git diff --check` passed. No GPU generation validated.
- **Release:** code published on `main` as `v2026.10.31.2`; the tag triggers the Docker image build.
  Image publication and deployment are pending.

### Match BFS planner Mask only segmentation

- Mask only now regenerates the per-frame SAM silhouette, grown by Expand, on the full frame, matching
  the BFS planner's `generation_mask` / `grow_blur` behavior. It no longer replaces the segmentation with
  a fixed bounding box around the subject's travel. Preview and generation use the same mask path.
- Removed box/margin controls from the mask settings and approval preview. Legacy `shape: box` and
  padding values remain accepted for saved requests, but use the silhouette too. Increase Expand when
  a replacement needs more room. Molmo pointing, cache, subject bindings and point tracking are unchanged.
- **Components:** ComfyUI mask preparation, studio controls, request validation.
- **Validation:** 95 CPU tests passed, one existing test skipped, covering mask movement/expansion,
  legacy box settings, point tracking, Molmo backend/cache/pointing, bindings, contracts and workflow export.
  TypeScript `tsc --noEmit` and `git diff --check` passed. No live SAM/H3 generation validated for this change.
- **Release:** prepared for `v2026.10.31.1`; Docker image publication and deployment pending.

### Keep the point-prompted mask before mask-only refinement

- Explicit subject marks use one SAM point-decoder pass. SAM3_Detect's next refinement pass omits the point prompt;
  on a reproduced input it erased a valid initial mask completely, leaving no seed for video tracking.
- **Component:** ComfyUI point tracking. **Validation:** a live GPU comparison at 800×480 produced a nonempty mask
  containing the marked point with one pass and an entirely empty mask with two passes. A separate 362-frame
  tracking graph seeded with the one-pass mask completed. CPU checks: 29 passed, one existing test skipped.
- **Release:** `v2026.10.31`; image build and deployment pending. No complete H3 generation validated.
- **Deployment:** the previous `v2026.10.30.1` image was published and selected for the Serverless worker template;
  old workers were drained with no queued or running jobs. That image still contains the two-pass refinement.

## 2026-10-30

### Explicit subject marks seed SAM segmentation

- Subject marks now go directly to SAM's point decoder instead of only selecting among text-detected people or
  animals. The resulting mask initializes video tracking forward and backward from the marked frame, stopping at
  camera cuts. Coordinates follow the same fit-and-pad transform as the source video.
- Shots without an explicit mark retain the existing continuity selection. If SAM cannot segment an explicit mark,
  mask preparation reports it before conditioning and sampling instead of passing an empty mask to generation.
- **Component:** ComfyUI guide nodes. **Validation:** 29 CPU tests passed, one existing look-recognition test skipped;
  point seeding, propagation in both directions, camera-cut boundaries, letterboxing, failed marks, guide integration
  and workflow exports covered. SAM calls are mocked in these tests; no live GPU generation completed.
- **Release:** `v2026.10.30.1`; worker image publication and deployment pending.

### Windows model paths survive input normalization

- The bridge preserves the exact model names resolved from ComfyUI's loader lists, including Windows backslashes.
  Previously, staged-input normalization changed `henge\...` model names to forward slashes after resolution,
  causing Character Swap LoRA validation to fail. Legacy staged video and image paths still use forward slashes.
- **Component:** bridge (`posix_inputs`). **Validation:** seven CPU tests passed, covering Windows and POSIX loader
  names and ComfyUI file handling. **Limitations:** no live Windows generation tested.
- **Publishing:** local changes only; no push, image publication or deployment performed.

### Motion Transfer runs without the training adapter

- The Motion Transfer LoRAs were trained over ostris' training adapter V2, which only counters the base model's
  distillation while training. Generation no longer loads it: Henge's Motion profiles, the seven published Motion
  workflows and the default downloads drop it (base, turbo, task LoRA). Tested by hand without the adapter for a long
  time; the extra file only added load time and VRAM.
- **Component:** UI/bridge (graphs), workflows, model manifest, docs. **Tests:** Motion graphs without the adapter, with
  and without a turbo; workflow link integrity after removing the node.

### Models on another drive (extra_model_paths.yaml)

- With `COMFY_ROOT` set, Henge only looked in `COMFY_ROOT/models` and reported models kept on another drive (mapped
  through ComfyUI's `extra_model_paths.yaml`) as missing. A model now counts as installed when ComfyUI lists it in a
  loader, wherever it lives; `HENGE_MODELS_DIR` chooses where Settings → Models downloads go. Reported by a user,
  whose workaround was leaving `COMFY_ROOT` empty (which also hid the checklist).
- **Component:** bridge and docs (RUN_LOCAL.md, .env.example). **Tests:** an empty models folder with every file
  listed by ComfyUI makes the modes ready; model-name extraction from ComfyUI's loader lists.

### Local setup: what the bridge is, and the HTTP 503 message

- `docs/RUN_LOCAL.md` says the job bridge is Henge's own server (not ComfyUI), how to start it with the UI
  (`scripts/local_stack.sh start` or steps 4 and 5) and has a "The bridge does not answer (HTTP 503)" section. The
  Settings message names the bridge, the command and that page. `.env.example` paths are clearly placeholders.
- **Component:** UI and docs. **Tests:** Playwright with a simulated 503 from the bridge.

### Images are built per release tag

- Docker images are built only for a pushed `v*` tag (or a manual run), no longer for every commit on `main`; a newer
  release cancels a build still running. Each release publishes `latest`, the release tag and `sha-<commit>`, so
  Render's "Deploy latest reference" works as before. The update notice compares with the newest successful build.
- **Component:** CI and docs (README, RENDER.md); bridge update check.
- GHCR keeps the three newest tagged versions of each image (with their platform and attestation manifests) plus
  `latest`; older versions are deleted after each build (about 1,200 removed in the first run).
- **Publishing:** image `sha-8624cc2` (all changes up to the interval-label fix) built; the Serverless worker template
  now uses `henge:latest` (workers recycled at 16:14 UTC, same env and limits). Each release recycles the workers so
  they pull the new `latest`.

### Source video: the interval label no longer covers the play button

- The selected-interval label moved from the bottom-left corner of the source video, over the player's play button
  and time, to the top-right corner.
- **Component:** UI. **Tests:** Playwright on desktop and 420 px: no player control is covered.

### Molmo2 analysis reused for the same clip

- Molmo2's description of the guide and its answer to the planner's guide question are saved by clip content
  (hash of the video), interval, question and Molmo2 settings, so a new generation from the same clip does not watch
  it again (each run costs GPU time on the backend worker). **Re-analyze the guide with Molmo2** (Advanced, next
  generation only) asks again and replaces the saved answer.
- **Component:** UI/bridge. **Tests:** same clip under another file name reuses the answer; refresh replaces it;
  another interval or question asks again. Playwright: the option shows when Molmo2 is available and is not stored.

### Motion Transfer TARA is the default

- The studio opens in Motion Transfer with the Motion Transfer TARA model and the TARA method. Character Swap and
  Head Swap use Guide Latents unless TARA is picked by hand; switching modes and New follow the same rule. Saved
  browser settings move once to these defaults. Motion jobs without a model (assistant, MCP) get Motion Transfer TARA,
  with the TARA method when the worker has the TARA node.
- **Component:** UI/bridge. **Tests:** Playwright: first open, switching Character Swap / Head Swap / Motion, New.

### Default sampling: DMAD at 8 steps; New resets the settings

- The default turbo is DMAD at 8 steps, CFG 1, sampler Auto; Sharpness keeps its Open-H3 first pass (DMAD at 4
  steps). The bridge applies the same default to jobs without a turbo (assistant, MCP).
- Saved browser settings move once to this default: earlier defaults and experiments (Pika with er_sde at 4 steps)
  stayed in browsers and were reused by every generation. Choices made afterwards are kept.
- **New** now also returns the generation settings to the current mode's defaults (Sharpness: DMAD at 4 steps and
  pure temporal windows); mode and language stay. It used to keep the settings.
- Models used lists Molmo2 (describes the guide video) when it runs locally or on the backend worker.
- **Component:** UI/bridge. **Tests:** Playwright: new browser, a saved Pika/er_sde/4-step setting, a later manual
  choice, the Sharpness preset, and New after a custom setting in Character Swap and in Sharpness.

## 2026-10-29

### Molmo2 on the Serverless worker; assistant keeps the original guide

- Without a local Molmo2, the bridge runs Molmo2 tasks (find people from photos, point at targets, questions about
  the video, split points) on the generation backend through the `HengeMolmo` node, as hidden jobs. The assistant
  gets its Molmo video tools whenever either place is available. The first backend request downloads the ~14 GB
  checkpoint to the volume.
- The assistant keeps the original guide by default, also with several people: it marks performers to bind them
  and suggests a color guide only when asked or after identities got mixed up; it never switches to mask by itself.
- **Component:** UI/bridge; the worker image already has the node (`sha-750cf58`). **Tests:** task file staging,
  backend routing and availability. Not yet run against the live worker.

### Character Swap prompts: cleaner reference descriptions and the guide's style

- Reference descriptions no longer carry the checklist echoes a VLM returns for attributes that do not apply ("no
  collars, no sleeves, no buttons, no zippers…"), nor the positive words a comma split made of "no beard, mustache or
  other facial hair" or "no … such as tattoos, scars…". Real details after a negation ("bare skin") are kept;
  ordinary descriptions are unchanged.
- The description instruction starts a creature or animal with what it is instead of "Male/Female" and skips
  categories that do not apply.
- The multi-character prompt asks to keep the guide's visual style (game, animation or live action) and render the
  replacements in it; it used to keep only background, lighting and camera.
- **Component:** UI/bridge (planner prompts). **Tests:** description cleanup on two real creature answers and an
  ordinary one. Not yet re-rendered; for creatures Motion Transfer TARA remains the recommended mode.

### DMAD 4-step is the default turbo

- Character Swap, Motion Transfer/TARA, Head Swap and the Sharpness first pass default to DMAD 4-step (4 steps,
  CFG 1). While the backend does not list the DMAD file, the studio and the bridge use DMD 8-step. Saved browser
  settings with the old untouched default (DMD 8-step, 8 steps) move to DMAD once; other saved choices are kept. Jobs
  that never stored a turbo keep DMD 8-step on Retry. Pika stays optional.
- **Component:** UI/bridge. **Tests:** Playwright with DMAD installed and missing (new browser, old saved default,
  manual choice, Sharpness preset). No new render.

### Assistant: temporal windows, references and Pika

- "Temporal" / "pure temporal window" requests now enable the processing strategy (`temporal_windows`) and keep the
  mode, pictures, marks and prompt; the assistant had cleared marks and tried to generate without references.
- The assistant no longer removes pictures or clears marks unless the user asks; on a picture-numbering error it
  fixes the prompt or asks the user instead of deleting references. Its notes now say windows are the Sharpness
  default.
- Images attached in the assistant chat fill Picture 1, 2, 3… in order; they could land after empty slots expected
  by a restored prompt, which the bridge then rejected.
- **Component:** UI/bridge (assistant prompt, studio). **Tests:** Playwright: two chat images load as Picture 1 and 2.
  Assistant behaviour itself not re-run with a live model.

### Pika H3 Flex stays optional

- Reverted making Pika the default turbo: Character Swap, Motion Transfer/TARA and Head Swap default to DMD 8-step
  again, and the Sharpness Refiner + LMS first pass to DMAD 4-step. Pika remains selectable with its 6-step preset.
- **Component:** UI/bridge.
### Fix: Pika 6-step with TARA or temporal windows

- Jobs combining Pika's 6-step preset with TARA, pure temporal windows or regional attention failed with
  `ManualSigmas.execute() got an unexpected keyword argument 'model'`: the patched model was also wired into the
  fixed-sigma node. It now goes to the guider only (and to the scheduler when it is a normal BasicScheduler).
- **Component:** UI/bridge (graph building). **Tests:** Pika graphs with TARA, windows and both.

### Pika H3 Flex: Kijai's reduced Ref2VA adapter

- The Pika turbo now downloads Kijai's `pika_h3_flex_ref2va_v1_avg_rank_55_bf16` (dynamic rank, sv_fro 0.99 from
  384; 553 MB instead of 1.96 GB). Checked against Pika's Ref2VA adapter: the same 208 modules. Pinned revision and
  SHA256 in the manifest; Pika's license and notice files are still installed. Existing installs of the full file
  keep using it without a new download.
- **Component:** model manifest and bridge (LoRA name). **Tests:** Pika graph and manifest tests. No render yet
  with the reduced file.

### Sharpness defaults to pure temporal windows

- Entering Sharpness selects **Pure temporal windows** (107/22) when the worker supports them; leaving Sharpness
  restores Standard unless the strategy was chosen by hand. The bridge applies the same default to Sharpness jobs
  that omit the option (assistant, MCP, API). Other modes keep Standard until they are compared with windows.
- With Open-H3 Refiner + LMS and pure windows, Sharpness shots are capped at 243 frames (~10 s), also in Single
  mode, because the frames held in RAM still grow with the shot.
- **Component:** UI/bridge. **Tests:** shot planning, Playwright on the mode switch (default, restore, manual
  choice kept). No new render.

### Settings → Models and version status

- **Settings → Models** lists the GitHub-backed model catalog (cached five minutes, bundled fallback offline) and
  the installed files. **Install model** downloads explicitly into the local ComfyUI (`COMFY_ROOT`) or, through the
  existing RunPod Serverless endpoint, straight into its shared volume, with progress, cancel and resumable retry;
  no temporary pod. Installs and generations block each other. Older workers need one image update.
- The footer shows the running version, **What's new** and a notice when a newer version is published. The notice
  compares with the newest commit whose Docker images finished building (GitHub Actions) and ignores commits that
  only change documentation; it used to point at main's latest commit, even while its image was still building.
- Docs: [Install models and check updates](docs/models-and-updates.md); the in-app guide has a Models section.
- **Components:** UI/bridge and worker image (model-install request). **Tests:** installer, install API and update
  checks; Playwright on desktop and 420 px (Settings gear, Models tab, footer) with downloads blocked. No real
  download was run.
- After an inventory refresh answered by a worker without model installs, the tab says so instead of only
  "Worker inventory updated".
- **Publishing:** Serverless worker template updated to `henge:sha-750cf58` (same env, 0–2 workers, 15 s idle).
  After one inventory refresh the hosted bridge reported install support and the Install button became available.

### Pika H3 Flex turbo and H3 sampler controls

- Added the pinned Ref2VA Comfy adapter plus upstream license/notice files to default model downloads. The selected
  default turbo is unchanged; Pika is an optional choice and is enabled once the worker reports its weight.
- Selecting Pika presets six steps, CFG 1, the Ref2VA base and Auto/LCM. Six steps use the published Comfy workflow's
  manual sigmas; custom counts use the normal model scheduler. Advanced exposes H3 sampler overrides.
- Preserved existing Euler/profile schedules and independent Open-H3 stage-2 sampling; H3 latent refinement keeps
  its own partial-denoise scheduler. Sampler settings survive exports/imports, Retry, assistant and MCP calls.
- Documented the Pika model license separately from MIT application code in the README, notices and setup guides.
- **Validation:** 197 backend tests and 23 subtests passed (4 optional skips); TypeScript and production build passed.
  Playwright with simulated backend replies checked preset selection, sampler overrides, custom-step feedback,
  assistant visibility and saved settings. Downloader dry-run includes Pika for standard profiles. Verified the
  upstream workflow schedule and pinned notice files; no weights were loaded and no quality render was performed.
- **Deployment:** code on main; UI/bridge deployment and a model-volume top-up are still required for an existing
  Serverless installation. Workers do not download models. Existing native sampler nodes can run the new graph;
  publishing a new full image makes the default-download manifest available to new download pods.
- [Sampling, download and license details](docs/pika-h3-flex.md).

### README feature and deployment review

- Updated the mode table, multi-subject TARA recommendation, opt-in mask guidance, fixed-seed controls and modified
  Kitchen setup. Documented the default Open-H3 Refiner + LMS path, separate sampling passes and output limits.
- Explained the built-in planner/assistant, optional Molmo, in-chat mode selection, MCP settings and portable exports.
- Clarified hard shot joins, experimental window strategies, memory limits, model placement and separate UI/worker
  updates. Removed absolute length/alignment promises and obsolete storage/startup estimates.
- **Validation:** compared behavior with the implementation and feature guides; all 57 local README link/image
  targets exist and the Markdown diff passes whitespace checks. Documentation only; no services or GPU models started.

### README introduction

- Moved the workflow export link into the feature list so the README opens with Henge's introduction and demo.
- **Validation:** checked the Markdown diff and relative documentation link. Documentation only; no runtime or deployment change.

### TARA profile in the replacement choice

- The recommended choice is explicitly Motion Transfer TARA for multiple people and objects. Selecting it applies
  both the `motion_tara` LoRA profile and the `tara` conditioning method, rather than only changing the mode.
- Updated the assistant, MCP instructions and localized guidance consistently; Character Swap remains a people-only
  alternative. An explicitly requested Guide Latents workflow is not overridden.
- **Validation:** production build, TypeScript and 11 assistant tests passed. Playwright checked the effective
  profile/method after selection, people-only eligibility and cancellation. No generation was started.
- **Deployment:** code on main; hosted UI/bridge deployment is required. No worker change.

### Replacement mode choice in the assistant

- The assistant recommends Motion Transfer for multiple replacement subjects, including people, objects and vehicles,
  because its LoRAs were trained for that task. Character Swap is offered only as an alternative for people.
- Ambiguous replacement requests use an in-chat choice card: wait for the user, apply their selected mode, or stop
  on cancellation. An explicit mode choice in the current request does not need another question.
- Updated MCP instructions and localized color-guide recommendations with the same subject restrictions.
- **Validation:** TypeScript and production build passed; 11 assistant tests passed. Playwright with simulated model
  replies verified waiting, both mode choices, people-only eligibility and cancellation without generation.
- **Deployment:** code on main; hosted UI/bridge needs deployment. Worker images and running jobs are unchanged.

### Live assistant configuration and MCP controls

- Updated assistant guidance: Original is the default for ordinary edits, including vehicles; masks are opt-in
  and require marks. Removed outdated TARA color-guide restrictions and added temporal-window preflight guidance.
- Optional Molmo tools are exposed only when configured; stale calls are rejected with a frame-inspection fallback.
- Studio state now includes generation values, window readiness and blockers. Nested option patches preserve
  sibling values; unknown option keys are rejected, and mask selection without marks fails before submission.
- Added backend configuration tools to the assistant and MCP. MCP now reports live window/Molmo capabilities,
  supports frame inspection without Molmo, and exposes guide, processing, audio and first-frame job controls.
- **Deployment:** source changes only; hosted UI/bridge must be redeployed and external MCP clients restarted.
  Existing running jobs and worker images are unchanged. MCP does not modify a browser's local draft.
- **Validation:** 189 backend tests and 23 subtests passed (4 optional skips); 3 MCP contract tests passed in an
  isolated SDK environment. TypeScript/production build passed. Playwright with simulated backend replies verified
  readiness, nested patches, settings reads, mask prerequisites and unknown-option rejection. No generation ran.

### Comparison download feedback

- Comparison + references downloads show an immediate preparation indicator in the result menu and history.
- Transfer status shows a percentage when the response includes its size, otherwise received megabytes.
- Repeated clicks are ignored while downloading; failures show a retry message instead of failing silently.
- **Validation:** TypeScript and production build passed. Playwright with simulated responses verified preparation,
  duplicate suppression, browser download, visible failure and successful retry; no generation was started.
- **Limitations:** comparison rendering has no numerical progress API, so preparation stays indeterminate.
  Downloads are buffered in the browser before saving. Code only; Render deployment is still required.

### Native H3 context-window comparison

- Compared Henge with ComfyUI PR #17425 at its reviewed commit, using source inspection and focused CPU probes.
- Confirmed matching video windows and pyramid weights at equal settings; documented different defaults,
  accumulation, guide handling and TARA integration requirements.
- Recorded the still-image/long-audio guide case that needs improvement in Henge.
- **Component:** documentation and analysis only. No runtime defaults, worker image or deployment were changed.
- [Findings and validation scope](docs/context-windows-native-comparison.md).

### Portable ComfyUI workflow packages

- Workflow downloads now include an editable visual workflow, portable and original API graphs, the input files,
  runtime Henge nodes and setup/model links. Internal conditioning expands into native H3/BFS nodes.
- Explicit dynamic sockets retain references on import; seed controls stay fixed. Henge timing/mask/attention
  widgets preserve float precision instead of rounding job settings.
- Video loading keeps the original FFmpeg decode and invalidates its cache when the uploaded file changes.
- Node packages exclude session notes, caches and external symlinks; packaged inputs must remain inside staging.
- **Components:** UI/bridge and packaged custom nodes. Existing inference graphs are unchanged.
- **Validation:** real ComfyUI prompt validation including the generated output; loader RGB parity; frontend
  round trip with TARA references and continuity. Full model inference was not repeated for export validation.
- [Package contents, setup and limits](docs/workflow-export.md).

### Export the ComfyUI workflow from History and per shot

- History cards list **Workflow (ComfyUI)** next to the other downloads; each finished shot has a `{ }` link with
  that shot's API-format graph; the result menu says its workflow is shot 1. **Everything (.zip)** still carries
  every graph under `workflows/`.
- **Component:** UI only. **Tests:** Playwright on the local UI (history card, shot strip at desktop and 420 px, a
  downloaded shot graph parsed as JSON).

### Repository: no private details; local settings documented

- Removed hard-coded private hosts from `next.config.ts` (development origins now come from `HENGE_DEV_ORIGINS` in
  `.env.local`), absolute local paths from four workflow JSONs, internal test notes with local job ids
  (`docs/tests/`) and job ids from the guide capture manifest; the capture script now picks the newest jobs of each
  kind instead of named local tests.
- `.env.example` lists the RunPod Serverless, login and development-origin variables; `docs/RUN_LOCAL.md` has a
  "What to change for your machine" table. `AGENTS.md` states the rule for every contributor and agent.
- **Component:** repository and documentation; no behaviour change.

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
- Fixed the editor layout: opening it no longer breaks the finished-shots grid (the grid rule targeted the strip's
  last child), and the prompt box follows the dark theme. Checked with Playwright on desktop, 420 px and dark mode.

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
