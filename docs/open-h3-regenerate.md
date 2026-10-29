# Open-H3 Regenerate in Sharpness

**Open-H3 Refiner + LMS · default**, the first entry and default selection of the Sharpness upscale dropdown,
first runs Henge's LMS sharpening and then a second, generative pass. It can change details: always compare
with the original video.

The second pass uses the same Ref2VA base that is already installed, loaded in an independent LoRA chain:
DMAD 4-step, Kijai's rank-16 refiner and our LMS v1.0 r64. That file contains **only the refiner**, without
LMS and without LightX2V Turbo. LMS is loaded separately in each pass, once per model chain. In the second pass
LMS is optional (**Add LMS on top of the refiner**, on by default) with its own strength (0.1–1.5, default 1.0);
off, the second pass runs the refiner and the turbo only. In the second pass, `MiniMaxH3AddGuide` anchors the
shot's original video at the final resolution, starting at frame 0.

The graph adapts `minimax_h3_2stage_testing.json`: native latent upscaler, a text description plus Add Guide of
the original video in the second pass, and the `er_sde` sampler. Selecting this method in the UI sets the first
pass to **DMAD 4-step, 4 steps and CFG 1**. Those controls stay editable afterwards. The refiner has its own
steps: the default is two (`0.7, 0.494118, 0`); three are experimental (`0.909375, 0.857143, 0.666667, 0`), from
the alternative schedule that is not connected in that workflow. The public DMAD used here is avg rank 39,
unlike the local rank-83 file of that workflow. The Ref2VA base also differs from the workflow's FL2VA. This
combination is experimental and is not an identical reproduction of NVIDIA's CUDA inference.

## Installing on the worker

The Dockerfile pins ComfyUI to `35060f0156181ae78a86b10f098f67ce8e83697f`, which includes
`MiniMaxH3LatentUpscaleWithModel`. Updating only the frontend does not install that node on the worker.
Rebuild and publish the worker image and point the endpoint at it.

### Regular pod / local install

Add `regenerate` to the existing profiles in `HENGE_MODEL_PROFILES` (for example
`character,sharpness,regenerate`) and restart the pod with the updated image. The profile is optional; it reuses
the common Ref2VA base and neither downloads nor needs FL2VA. For a manual install:

```bash
python scripts/download_models.py --models-dir /opt/ComfyUI/models --profiles sharpness,regenerate
```

### RunPod Serverless

**Serverless startup/rendering does not run the downloader.** Updated workers also offer an explicit
**Settings → Models** installation action, without a fill pod; see [on-demand installs](models-and-updates.md). Adding the profile only to the worker's variables does not
install the weights. Use a temporary pod to top up the volume attached to the endpoint:

```bash
VOLUME_ID=<existing-volume> DATACENTER=<volume-datacenter> \
  PROFILES=regenerate scripts/runpod_volume.sh
```

Then update the worker template's image and recycle the old workers when no jobs are active. Keep the same
volume. It shows up as `/workspace/henge/models` in the download pod and `/runpod-volume/henge/models` in the
worker; both are the same persistent storage.

The bridge keeps the inventory the worker returns. After the update, run a short job with another available
method from Henge and reload the page. That refreshes the cache without reinstalling the bridge. `/health` and
**Test connection** do not wake the worker to fetch a new inventory, and a direct `inventory` call to RunPod does
not refresh the bridge's cache either.

See the [full Serverless procedure](SERVERLESS.md#enable-refiner--lms-on-an-existing-endpoint).

### Dependencies that enable the dropdown

| Type | File under `models/` |
| --- | --- |
| Base already used by Henge | `diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| DMAD | `loras/henge/minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors` |
| Refiner | `loras/henge/minimax_h3_open_regenerate_2k_refiner_rank_16_bf16.safetensors` |
| LMS | `loras/henge/minimax_h3_lms_v1.0_r64.safetensors` |
| Native upscaler | `latent_upscale_models/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors` |

The checked nodes are `MiniMaxH3LatentUpscaleWithModel`, `LatentUpscaleModelLoader`, `ManualSigmas`,
`BasicGuider` and `MiniMaxH3AddGuide`. The earlier LMS upscaler does not replace the native upscaler listed
above. An old worker can have the weights and still lack the nodes. The diagnosis is in
`regenerate.missing_nodes` and `regenerate.missing_models` in the bridge's `/health` reply (from the UI:
`/api/backend/health`).

## Use and limits

Entering Sharpness switches 480p/720p to **1080p**, which the default method supports; **2K** is also available.
The dropdown and the **Refiner prompt (optional)** field are in the main creation panel, outside Advanced. Saved
settings with an explicit method are still honoured. The first pass runs with a 768-pixel short side; the second
gets the final dimensions explicitly, keeping the video's orientation. 4K is not enabled for this method.

Give a faithful description of the scene, or leave it empty for the configured VLM to describe the frames. That
description is separate from the technical LMS instruction and can be reviewed in the job's plan. It does not
depend on local Molmo. On clips with several shots the automatic description covers the whole interval; check
cuts and different scenes in particular.

Automated tests check graph assembly, schedules, audio, resolution and the block on missing dependencies. Real
generations on RunPod Serverless (2026-10-29, see the [changelog](../CHANGELOG.md)) completed at 1952×1088;
quality, time and VRAM still need more comparisons, and there is no capacity estimate yet.

Sources: [Kijai workflow/models](https://huggingface.co/Kijai/MiniMax-H3-experimental),
[native ComfyUI node](https://github.com/Comfy-Org/ComfyUI/commit/35060f0156181ae78a86b10f098f67ce8e83697f),
[NVIDIA model](https://huggingface.co/Efficient-Large-Model/Open-H3-Regenerate-2K).

### Memory limit per block

The refiner processes blocks of at most **107 frames (~4.46 s at 24 fps)**, even when the UI asks for one long
segment. The blocks share the configured continuity context; the join removes the overlap and keeps the full
duration, without crossfade. This limit reduces the load of both passes and of Add Guide at the final
resolution; it does not guarantee enough VRAM/RAM for every resolution or hardware.

A failed graph recovered on 2026-10-29 tried 328 frames, a 1376×768 first pass and refinement with a 1952×1088
guide. The worker closed the connection; the old log was not available to confirm an OOM. A closed WebSocket
message should not be treated as a definitive diagnosis.

### Pure windows option

**Settings → Temporal processing** also applies to both Sharpness passes. It combines predictions per step and
keeps the global sampler. It is not the same as splitting into finished blocks, nor the hybrid sequential-warmup
mode. See [setup, explanation and limits](temporal-windows.md).

### Segments → full-video refiner windows (optional)

In **Settings → Temporal processing**, the two-stage strategy keeps the normal segment-by-segment generation at
the initial resolution and applies Open-H3 only after the full video is assembled. The second pass uses pure
context windows, initially 107 frames with 22 of overlap, at every refiner step. The default is still the
previous per-segment path. The worker must be updated too. See [temporal processing](temporal-windows.md) for
the limits on memory, VAE re-encoding, audio and camera cuts.
