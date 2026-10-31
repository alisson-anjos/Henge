# Pika H3 Flex turbo in Henge

Pika is an optional **Turbo LoRA** selection, downloaded by default. It does not replace Henge's task LoRAs or
change the existing default turbo. Henge uses the Comfy-format **Ref2VA** adapter at strength 1.0 with its existing
H3 Ref2VA base; FL2VA and FastH3 OmniRef are not used for this option.

## Sampling

In **Settings → Advanced → Turbo LoRA**, select **Pika H3 Flex · 6-step (Official)** or **Pika H3 Flex · 6-step (Kijai)**. This presets the first pass to six steps,
CFG 1 and **H3 sampler → Auto**, which resolves to LCM for Pika and Euler for the other turbos. At six steps the
Comfy workflow's manual sigmas are:

```text
1.0, 0.972973, 0.923077, 0.8, 0.571429, 0.333333, 0.0
```

- Override **H3 sampler** to experiment with another sampler; at six steps the same manual sigmas remain active.
- Change the step count to use the model's normal scheduler for that many steps. Auto still selects LCM for Pika.
  This is an experimental alternative, not the published six-step schedule; more steps do not guarantee better quality.
- The H3 latent-upscale refinement reuses the selected sampler but has its own partial-denoise schedule.
- **Open-H3 Refiner + LMS** keeps its independent stage-2 DMAD chain, `er_sde` sampler and refiner sigmas.
- Exported settings, assistant options, MCP job options and Retry preserve `sampler_name`. For API/MCP requests,
  use `turbo="pika6"`, `steps=6`, `cfg=1`, `base="h3"`, `sampler_name="auto"`. Omitting steps with Pika defaults to six.

The published Comfy workflow and the original Pika inference package have different sampling implementations.
Matching this Comfy preset is not a claim of reproducing the original package. Stacking Pika with Henge's task
LoRAs, TARA, masks or temporal windows needs generation/quality comparisons.

## Download and availability

The public manifest includes the adapter and accompanying license/notice files in the `common` profile, so normal
profile downloads include them. The optional `pika` profile can be used to top up an existing models folder:

```sh
python scripts/download_models.py --models-dir /path/to/ComfyUI/models --profiles pika
```

The adapter is the official full-rank BF16 Ref2VA Comfy adapter from
[Pika-Labs/Pika-H3-Flex](https://huggingface.co/Pika-Labs/Pika-H3-Flex/blob/0ddf55ad7067ca1e76812253bd7b4600df87f759/comfy/loras/pika_h3_flex_ref2va_comfy_bf16.safetensors),
approximately 1.96 GB. It is installed as `loras/henge/pika_h3_flex_ref2va_comfy_bf16.safetensors`,
pinned to revision `0ddf55ad7067ca1e76812253bd7b4600df87f759`, SHA256
`e4d058fbd027377b925a0ee607b514ddd9037873fee3afa05d73b302e6f7f8e1` from the official `comfy/SHA256SUMS`.
The license and notice files come from the same revision. Existing installations of this official file are reused.
The reduced Kijai adapter is a separate selection, `turbo="pika6_kijai"`, installed under its published
`pika_h3_flex_ref2va_v1_avg_rank_55_bf16.safetensors` filename (approximately 553 MB). Both adapters are included
in the common and pika download profiles. Each selection requires its own file; neither substitutes for the other. The download manifest records this checksum; the explicit on-demand installer
verifies it. The bootstrap profile downloader records the checksum without adding a separate checksum pass.

Serverless workers do not automatically download models during generation. Updated workers can install them
explicitly from **Settings → Models**, without a fill pod; see [on-demand model installation](models-and-updates.md).
The fill-pod bulk setup is still an alternative. With that older path, refresh the bridge inventory through a normal
job using an already available method. Until the worker lists the file,
Pika is unavailable in the dropdown. Redeploy the UI/bridge for the new preset and controls. Existing workers with
native `ManualSigmas` and `KSamplerSelect` can use the graph once the weight is present; a newly published full image
also includes the updated download manifest. See [Serverless setup](SERVERLESS.md).

The adapter uses the **MiniMax H3 Community License Agreement**; it is separate from the application's MIT license.
The downloader keeps the Pika license and notices under `models/licenses/pika-h3-flex/`.

## Sources

- [Pika model card](https://huggingface.co/Pika-Labs/Pika-H3-Flex).
- [Comfy adapter format, sampling and licensing](https://huggingface.co/Pika-Labs/Pika-H3-Flex/blob/0ddf55ad7067ca1e76812253bd7b4600df87f759/comfy/README.md).
- [ComfyUI tutorial](https://docs.comfy.org/tutorials/video/pika/pika-h3-flex) and
  [Ref2VA workflow](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_pika_h3_flex_ref2va.json).
