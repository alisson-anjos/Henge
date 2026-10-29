# Native H3 context windows compared with Henge

Reviewed on 2026-10-29 against [ComfyUI PR #17425](https://github.com/Comfy-Org/ComfyUI/pull/17425),
head `78b9b925cb3e0ca16ee6710d1dd4ba7a387eb061`. The PR was open and unmerged at review time.
This is a code comparison with focused CPU probes, not a GPU quality or performance benchmark.

Both approaches evaluate overlapping temporal windows at each denoise step, fuse the predictions and update a
shared latent through the existing sampler. Neither requires a sequential warmup phase or a final-frame crossfade.
The PR puts H3-specific handling into the native model and reuses ComfyUI's general context handler; Henge uses
its own H3 handler on the same sampling dispatch interface.

| Setting | Henge | PR at the reviewed commit |
| --- | --- | --- |
| Default window / overlap | 107 / 22 pixel frames | 124 / 39 pixel frames |
| Fusion | Pyramid weights | Pyramid by default; other fusion choices available |
| FreeNoise | Disabled | Enabled by default |
| Accumulators | CPU/FP32 by default; node also exposes GPU | Latent device/dtype |
| Multiple temporal conditionings | Not exposed | Optional splitting of combined conditionings between windows |

The [native node](https://github.com/Comfy-Org/ComfyUI/blob/78b9b925cb3e0ca16ee6710d1dd4ba7a387eb061/comfy_extras/nodes_context_windows.py)
has different defaults. Match window, overlap and fusion, and disable FreeNoise first, before comparing results.
FreeNoise changes the noise arrangement; sharing a seed alone does not make the default configurations equivalent.

## Memory and conditioning differences

The [native handler](https://github.com/Comfy-Org/ComfyUI/blob/78b9b925cb3e0ca16ee6710d1dd4ba7a387eb061/comfy/context_windows.py)
evaluates one window at a time but also keeps full-length accumulation buffers on the latent device. Henge's
CPU accumulation trades transfers for less VRAM used by those buffers. Model evaluation memory still depends
on window size; neither implementation makes full-video latent storage, guide encoding or VAE decoding free.
No speed or peak-memory advantage was measured here.

The [native H3 model changes](https://github.com/Comfy-Org/ComfyUI/blob/78b9b925cb3e0ca16ee6710d1dd4ba7a387eb061/comfy/model_base.py)
handle video and audio temporal axes separately. Guide clips are retained in five-latent chunks, potentially
extending beyond the target window. Henge uses strict aligned intersections. Audio edge rounding also differs:
the PR scales from the actual total audio length, while Henge uses the model's 40/24 timeline rate.

A CPU probe found a Henge limitation: with a single still-image anchor and longer audio in the same keyframe,
later windows lose the audio guide. The PR treats video/audio intersections separately and retains it. Henge's
usual full-video guides are a different case; this probe does not establish an error in every audio-enabled job.

## TARA is not a direct replacement

Generic native references stay intact in the reviewed PR. Henge additionally crops the aligned TARA motion
reference and rebuilds its packed layout before the BFS wrapper inspects it. With a guide keyframe present,
the PR removes the old layout for the model forward to rebuild later; the current BFS wrapper needs it earlier.
A CPU probe using the actual BFS wrapper rejected that unadapted payload with a missing-layout error.
This establishes an integration requirement, not that native context windows are incorrect for ordinary Ref2VA.

## CPU checks and next comparison

- Video window indices matched in 40 configurations at equal settings.
- Pyramid weights matched for 100 lengths.
- One tested audio boundary differed by one audio column; output quality impact was not measured.
- The unadapted TARA case and the still-image/long-audio case above were reproduced in CPU probes.

An initial native backend trial should use Sharpness/refinement or Guide Latents, equal settings and FreeNoise
off, followed by an independent FreeNoise comparison. TARA needs its adapter before the same trial. Keep the
current default path until Serverless A/B results establish compatibility and practical quality/memory behavior.

Henge also refines long stage-2 inputs in outer chunks (currently at most 243 frames) to bound host RAM used by
full-resolution guide/output frames. Replacing the inner context handler alone does not remove that constraint.
