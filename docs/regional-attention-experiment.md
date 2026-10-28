# Experimental H3 regional reference attention

Branch: `experimental/mast-region-attention`.

This is a LAMA-inspired H3 adaptation, not the full MAST pipeline.
Primary source: https://arxiv.org/html/2604.12281v2 (sections 3.3 and 4.1).
MAST evaluates image style transfer on Stable Diffusion 1.4. It does not establish
identity-transfer or video performance on MiniMax H3. DenseDiffusion
(https://arxiv.org/abs/2308.12964) is another relevant baseline, but its text-region
modulation is less directly matched to our native image-reference partitions.

## Behavior

HengeGuide returns per-reference tracked silhouettes as an extra output. They are
averaged onto H3's spatiotemporal query grid (first video frame then groups of four,
32px spatial patches). Overlapping assignments share the reference budget.
On selected H3 blocks, target-video queries receive LAMA-style logit biases for
each native image-reference key span. All other keys (prompt, guide, audio and
target video) form the retained context partition. This grouping differs from MAST's
separate content branch. No noise mask, pixel replacement, AdaIN, inversion, STS or
DDI is added. Non-video queries retain the native attention implementation.

`reference_budget` controls reference-vs-context allocation at full strength;
`strength` interpolates the logit adjustment with the original attention.
Default: strength 0.5, budget 0.35, blocks 10/25/40 (zero-based, exploratory choices,
not values validated by the paper). A small probability floor avoids hard -infinity
boundaries. The retained context mass is not a guarantee of background preservation.
Strength 0 bypasses patching. Disabled graphs have no regional-attention node.
Scores are evaluated in small query/head chunks rather than a full video NxN matrix;
the reference implementation is slower than fused attention and recomputes QKV in
selected blocks. Measure latency and peak VRAM on the worker.

## Test

In Character Swap, choose 2D or 3D Guide Latents with marked people. Enable
“Focus each reference on its marked person (experimental)”. Initially use one short
shot, two people, two references, no cuts. Keep labels off, seed, prompt, reference
preparation, model and all other settings identical across the comparison.

1. Control: checkbox off.
2. Experiment: checkbox on (0.5 strength / 0.35 budget).
3. Inspect identity-to-person assignment, unmarked people, background changes,
   character duplication, motion, flicker, tracking correctness and runtime.
4. If identity weakens, sweep budget before adding STS or more layers.
5. Only after a successful within-shot test, repeat across a camera cut.

API options: `regional_attention: {enabled: true, strength: 0.5,
reference_budget: 0.35, layers: "10,25,40"}`. The first version rejects latent-mask,
TARA, causal and upscale combinations. No endpoint changes are needed to disable
it once this worker image is installed. Returning to the prior image also removes
it. Keep the experimental image pinned by SHA; do not move main/latest.

## Verification status

CPU tests cover partition masses with unequal reference sizes, overlap/soft masks,
zero-strength parity, bounded chunk equivalence, temporal padding, opt-in graph
wiring, and a simulated H3 block callback retaining non-video queries.
A real GPU render is still required before making any visual-quality claim.
