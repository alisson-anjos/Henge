# Pure temporal windows in Henge

In **Settings → Temporal processing → Processing strategy**, choose:

- **Standard processing**: keeps the previous path. This is the default.
- **Pure temporal windows · experimental**: every denoise evaluation uses overlapping windows whose
  predictions are combined before the sampler updates the global latent. There is no sequential warmup.

- **Segments → full-video refiner windows · experimental**: in Sharpness with Open-H3 Refiner + LMS
  and 1080p/2K output, stage 1 renders the segments as usual (up to 107 frames, keeping context between
  segments). After the segments are joined without crossfade, stage 2 refines **the whole interval** with
  overlapping windows at every step. Stage 1 uses no context windows and runs no per-segment refiner.

Windows in every pass are available for Character Swap, Motion Transfer (Guide Latents and TARA), Head Swap
and Sharpness. In Sharpness they apply to the first pass and also to the H3/Open-H3 refinement, when present.
NVIDIA VSR still runs on the frames after the first pass; it is not an extra denoise.

## Segments first, global refiner after

This strategy keeps a single global sampler evaluation per noise level in stage 2: local predictions are
combined before the update. Window and overlap start at 107/22 frames; the refiner keeps its default 2 steps
and `er_sde`. It is not the hybrid sampler that switches strategy in the middle **of the same pass**: these are
two complete passes, with separate models and schedules.

To reuse the segment infrastructure and allow Retry/Redo, the assembled first-pass frames are re-encoded with
the tiled VAE. Generation latent files are not concatenated, so this re-encode can introduce some loss. The
native latent upscaler receives the re-encoded video, while Add Guide anchors the interval of the **original
video** at the final resolution. The final audio still follows the job's audio controls; the second pass does
not replace the track with a new generation.

Stage-2 windows can cross camera cuts, including the ones that split stage 1. The full guide keeps the cuts as
control, but this does not guarantee perfect transitions. Compare those regions and reduce window/overlap if
they blend. The automatic `fit→every` split described below applies only to windows in every pass, not to this
strategy.

Stage 2 holds the first pass, the source guide at the output size and the decoded output in RAM at the same
time. At 1952×1088, 530 frames (22 s) is about 34 GB of frames and killed a 56 GB RTX 5090 worker before the
first refiner step. Videos longer than **243 frames (~10 s)** are therefore refined in chunks of at most 243
frames, with context windows inside each chunk. Chunk cuts go at the joins between first-pass segments when one
is in reach (they are already hard joins); a chunk that must start inside a segment re-reads 22 earlier frames,
which are dropped from its output. Chunks are laid end to end without crossfade. Retry keeps the chunks already
refined from the same first pass. A cut inside a long continuous segment can show a small seam; compare it.

The interval is still limited to **3600 frames after padding** (about 150 s at 24 fps).
Redoing a segment runs stage 2 again on the updated assembly.

In the API, use `temporal_windows.enabled=true` and `scope="refiner_full"`. `scope="all"` (or leaving it out)
keeps windows in every pass. `enabled=false` keeps the previous path, unchanged.

## Three different controls

| Control | What it does |
| --- | --- |
| Shots / cut detection | Splits the video into scenes or working segments |
| Context frames between segments | Uses part of an already generated result to condition the next segment |
| Pure temporal windows | Shares predictions between windows during every generation step of one shot |

The windows do not concatenate several finished videos. There is one global latent and a single sampler with
its schedule, noise and history. At every model evaluation, all windows see the same noise level. Overlaps
get larger positive weights in their centre and are normalized after all predictions. This is not a crossfade
of final frames and needs neither the hybrid sampler nor its dependencies.

With cut detection on, pure mode turns `fit` into `every`: each detected cut starts a new shot, so predictions
from different scenes never mix. Turning detection off keeps the chosen interval explicitly continuous. Cuts the
detector misses still need manual review. Context frames between shots keep following the existing Planner rules.

## Starting values

- **Window: 107 frames**, about 4.46 s at 24 fps.
- **Overlap: 22 frames**, about 0.92 s.
- Both follow the H3 `17n+5` grid, with the overlap smaller than the window.
- Predictions accumulate on **CPU/FP32** and go back to the sampler with the expected dtype and device.

Shots shorter than the window use a single window. For a first test, compare that case with standard mode,
keeping the same seed and settings. Then test a shot that needs several windows. Smaller windows reduce the
tokens per evaluation but increase the number of evaluations per step. The last window is shifted to end
exactly at the end of the latent; no frame or audio column is left uncovered.

In the standard refiner, the guard that splits long segments into blocks of up to 107 frames stays on.
With pure windows that extra limit is lifted: shot length follows the user's controls and the cuts, and model
evaluations are bounded by the temporal window.

## Conditioning, references and audio

The **HengeH3PureWindows** node uses ComfyUI's context protocol without replacing the sampler:

- Add Guide is cropped to the window's temporal grid and gets local indices.
- Image references keep their roles and order; they do not become new characters.
- In TARA, the reference video and its audio follow the same interval. The packed layout is rebuilt before the
  TARA attention wrapper reads the temporal positions.
- Single anchor frames are kept only in the windows where they appear.
- Video and audio temporal denoise masks are cropped together with their streams.
- The sampler keeps its global noise and history; it does not draw a seed per window or restart a multistep
  solver on every crop. `er_sde` is still the refiner's sampler; it was not replaced with Euler.

Video references used as motion control must have the same temporal length as the target. Partially cropped
Add Guide clips must be aligned to the causal grid; an incompatible case raises an explicit error. Initial
support covers frame-0 guides and the anchors produced by Henge's flows.

## Memory and limits

The reduction is in the size of the DiT evaluations. It does not guarantee that any duration or resolution fits:
video loading, the VAE, segmentation/tracking, the global latent and export still use RAM/VRAM. If memory runs
out, also reduce the duration per shot or the resolution. Identity, motion and quality are not promised to
match global attention when several windows are used.

Do not combine this option with **Causal**, **regional attention**, another context handler or ControlNet.
Those paths need their own integration and are rejected where they apply.
TARA/Kitchen still depends on the modified temporal extension: see
[the Motion Transfer guide](motion-transfer.md#comfy-kitchen-works-with-tara--use-the-modified-temporal-kernel).

## Updating the UI and the worker

Both the new frontend/bridge and a worker image that contains `HengeH3PureWindows` are needed.
Pure windows need no extra weights and no new download profile.

On RunPod, wait for the Docker publish, update the template and recycle the workers once active jobs finish.
The bridge enables the option when the inventory reports the new node (`temporal_windows_ready=true` in
`/health`). The cache is refreshed by a worker job's reply; see
[updating the endpoint](SERVERLESS.md#enable-refiner--lms-on-an-existing-endpoint).
The UI warns when the worker is still old, including for imported settings.

The API and settings export use:

```json
{
  "temporal_windows": {
    "enabled": true,
    "window_frames": 107,
    "overlap_frames": 22
  }
}
```

The setting is saved and shows in the job's settings/comparisons. Turning it off restores the normal graph;
it does not fall back to hybrid processing.

## Implementation references and validation

Independent implementation in Henge, using the
[ComfyUI ContextHandler](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/context_windows.py) API.
[HybridWindows](https://github.com/Jalen-Brunson/ComfyUI-HybridWindows) was studied as an H3 reference for
audio/video, per-window conditioning and the distinction between sequential and joint phases; this option does
not use its warmup phase, does not install that package and does not depend on MMH3Tools.

CPU tests check AV coverage, prediction normalization, CFG, duration preservation, anchors, mask cropping,
incompatible controls, cancellation and model routing in Henge's modes. A small H3 with random weights also ran
one and several windows on CPU, including the real TARA wrapper on the Flex backend, with finite output and AV
shapes preserved. That does not validate the production LoRAs or the Flash/Kitchen GPU kernels.

Real generations on RunPod Serverless (2026-10-29, see the [changelog](../CHANGELOG.md)) showed no seam between
windows in Sharpness, Character Swap results, Motion Transfer and TARA on short clips; longer clips with several
windows and camera cuts are still to be compared before promoting the mode to default.

To repeat the reduced-H3 CPU test (no weight download), with ComfyUI's Python:

```bash
python scripts/check_h3_pure_windows_cpu.py --comfy-root /path/to/ComfyUI --bfs-root /path/to/ComfyUI-BFSNodes
```


## Native ComfyUI H3 context windows

See the [comparison with PR #17425](context-windows-native-comparison.md) for matching settings, memory behavior,
TARA integration requirements and a guide-audio limitation found during CPU probes. No backend migration is enabled
by that analysis.
