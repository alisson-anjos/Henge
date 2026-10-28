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
