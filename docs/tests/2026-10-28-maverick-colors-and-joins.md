# Local verification, 2026-10-28

## Window joins

Source completed TARA job: `9263664b15a541c9944a56a5ac6b51bb`.
The previous bridge dissolved eight overlapping frames between generated windows.
A frame comparison shows doubled hands and softened contours when the two generated poses differ.
`video_join.join_overlap` now colour-matches and switches at the closest matching overlap frame,
without interpolating pixels. Reassembling the stored raw outputs retained 474 frames / 19.75 seconds.
The preview improves those doubled contours; a discrete pose jump remains possible and needs visual review.

Preview: `D:\Downloads\henge_molmo2_test\nebsh_tara_sem_crossfade.mp4`.
Side-by-side (old left / new right): `nebsh_comparacao_juncoes.mp4` in the same folder.

## Maverick colour binding

Source project: `c20d487d89004c3ba9949f4ec399daa9`.
New test: `cf2e8193efc746178c74751eefe93828` (Character Swap, Guide Latents, seed 42, 8 steps).
Visual mask review at 0.82, 4.74 and 7.807 seconds confirms green → Picture 1,
purple → Picture 2, cyan → Picture 3. The middle shot marks the back of Maverick's head in purple.
Unmarked people were outside the displayed masks.

At opacity 0.35 the first generated shot left the green-marked actor unchanged and tinted.
The other marked actors changed; the complete three-way assignment did not succeed.
Remaining shots were cancelled after inspecting this failure.

Opacity 1.0 comparison: `0a1a68269fa04a488f19d76dde8396f7`.
Reused the exact reviewed plan, reference descriptions, reference images, seed and first-shot duration
(98 frames / 24 fps). Only the selected first-shot interval and colour opacity were changed.
At 100% the green silhouette remained unfilled; the central subject also deviated from the guide's pose.
Increasing opacity therefore did not solve the binding failure.

The Picture 1 automatic caption was visibly incomplete (generic repeated attributes, omitted hat and sunglasses).
This is a candidate contributor, not an established explanation of the generation failure.
Next investigation: explicit complete reference descriptions and colour-to-reference prompt assignment.
No evidence yet supports claiming that three-person colour swapping works correctly.

Downloads in `D:\Downloads\henge_molmo2_test\`:
- `maverick_cores_previa.mp4`
- `maverick_35pct_shot1.mp4`
- `maverick_100pct_shot1.mp4`
- `maverick_comparacao_35_vs_100.mp4` (35% left / 100% right)

## Optional Molmo

Settings → Molmo2 already offers on/off, checkpoint folder, warm retention and image detail.
Disabling Molmo preserves manual marks and SAM; planning falls back to sampled-frame analysis.
Studio routing to the worker-side Molmo node remains unimplemented.

## Motion Transfer comparison

Job `48cf089c954041caa3e344cfc96d4bd8`, completed.
Same first-shot interval, references, descriptions, seed, steps, and 100% opacity as above.
Changed profile to Motion Transfer v1.0 with Guide Latents and its training adapter;
changed the prompt trigger from `body_swap:` to `motion_transfer:`.
Verified the graph's guide method, opacity and LoRA chain before sampling.
The volume uses `henge/motion_10500.safetensors`, the mapped legacy local alias
of published `minimax_h3_motion_transfer_v1.0_ref2va.safetensors`.

Visual review at 0.4, 1.8 and 3.1 seconds: all three coloured silhouettes are filled,
but reference assignment remains incorrect. The left/green subject resembles Picture 2
(beard and aviator glasses), while the central/purple subject wears Picture 3's cap.
The graph lists prepared references in 1, 2, 3 order; HengeLoadShot preserves this order
and HengeH3Conditioning enumerates them in that same order. No list permutation
was found in this code path. This does not establish why the model confuses bindings.

Downloads:
- `maverick_motion_transfer_100pct_shot1.mp4`
- `maverick_character_vs_motion_100pct.mp4` (Character Swap left / Motion Transfer right)

User feedback on the TARA join preview: the version without crossfade appears better.

## Motion Transfer TARA comparison

Job `88b7199752094a8bb2ce6f62f93af513`, completed.
Same frozen prompt as Motion Transfer, same references, seed, 100% opacity and first-shot interval.
Changed profile to `motion_tara` and conditioning to native `tara`; structure guidance 1.
Verified training adapter + `motion_tara_4500` legacy alias + DMD8, and native temporal node.
This is an isolated prepared-plan experiment: normal studio validation still rejects TARA with 2D/3D colours,
because the published TARA profile was trained on plain video. No general validation rule was removed.

Visual inspection at 0.4, 1.8 and 3.1 seconds shows an improvement over Motion Transfer / Guide Latents:
the green subject has Picture 1's cap and sunglasses, the purple subject has an uncovered head,
and the cyan subject has Picture 3's navy cap. Guide poses are also closer in the inspected frames.
The purple subject is missing Picture 2's sunglasses, so reference appearance remains incomplete.
These observations cover the first shot only, not the full project across cuts.

Downloads:
- `maverick_tara_100pct_shot1.mp4`
- `maverick_motion_vs_tara_100pct.mp4` (Guide Latents left / TARA right)

Follow-up `35118dd687384e65a8a731888808cbc6` tests the same TARA configuration with a manually reviewed,
more explicit prompt and reference descriptions. Prompt: `maverick-explicit-color-prompt.txt`.
Completed. Visual review at 0.4, 1.8 and 3.1 seconds shows that the purple subject now has
Picture 2's aviator sunglasses and uncovered hair, while green retains Picture 1's cap/glasses
and cyan retains Picture 3's navy cap. This improves the inspected accessory assignments;
it is not a measurement of exact identity fidelity or a validation across the other camera shots.
Best inspected first-shot configuration so far: Motion Transfer TARA + native TARA + explicit prompt,
100% colour opacity, seed 42, 8 steps, DMD8, structure guidance 1.

Downloads:
- `maverick_tara_prompt_explicito_shot1.mp4`
- `maverick_tara_prompt_antes_vs_depois.mp4` (previous prompt left / explicit prompt right)

Next required validation for the complete project: the middle and final camera shots,
including absent subjects and reference renumbering after cuts.

## Character Swap with the explicit prompt

Job `36862c27eae24ec28394b44ae91ddb99`, completed.
Character Swap v1.1 + Guide Latents, 100% colour opacity, seed 42, 8 steps.
Used the manually reviewed prompt, changing its task trigger to `body_swap:`.
Disabled automatic prompt enhancement to prevent per-shot rewriting of the frozen prompt;
`guide_clip=on` still presents the guide frames to the text encoder.

Visual inspection at 0.4, 1.8 and 3.1 seconds shows all three assigned people filled with the expected
reference accessories: gold-detail cap/glasses on green, uncovered hair/glasses on purple,
navy cap on cyan. This is a substantial improvement over the previous generic-caption Character Swap test.
The prompt is therefore an important contributor; this is first-shot evidence, not a guarantee of perfect
identity fidelity or correctness across camera cuts. No latent noise mask was added in this comparison.

Downloads:
- `maverick_character_prompt_explicito_shot1.mp4`
- `maverick_tara_vs_character_prompt_explicito.mp4` (TARA left / Character Swap right)

## Product guidance and checks

Studio now recommends Motion Transfer TARA + TARA with explicit per-person prompts for colour guides;
Character Swap stays available with wording that reference assignment can be unreliable.
Removed the previous UI/backend ban on TARA with colour marks. Existing restrictions unrelated to colour remain.
Assistant instructions use the same recommendation without silently changing the user's chosen settings.

TypeScript and production build passed. Focused validation checks passed.
The wider 55-test contracts/conditioning run had 52 passes and three failures concerning animal adaptation,
a stale history-guide expectation, and reference-preparation mocks. The same three failures were reproduced
against HEAD before the colour recommendation changes in an isolated source copy.

## Latest local build: seed control and per-shot identities

- Multi-character prompt notice is visible near subject marks and generation settings.
- Seed moved out of Advanced, with an explicit randomize button; the sampled base seed remains in job options
  and is displayed with the selected job. Randomizing changes the visible seed; it does not start generation.
- Automatic per-shot identity filtering now covers marked Motion Transfer/TARA runs as well as Character Swap.
- Prompts bind identity to the marked person independently of position/depth, preserve back-facing poses,
  and include only tracked identities with locally renumbered references.
- Per-shot task trigger follows the selected profile (`motion_transfer` or `body_swap`).
- These automatic per-shot prompts require prompt enhancement enabled; manual frozen prompts remain unchanged.
- Five shot-swap tests passed, including a third subject moving forward and being the only visible subject.
  TypeScript, Python compilation, production build and diff whitespace checks passed.
- Local UI and bridge restarted with these changes. No new generation started after the user's request
  to leave the current version for manual testing.
