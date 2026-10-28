# Finding people with Molmo2 (optional, local)

Henge can use [Molmo2](https://huggingface.co/collections/allenai/molmo2) on the bridge machine to find people
in the guide video and propose the marks that SAM tracks. It never runs on the generation backend: it is a
separate Python environment, started per request and closed after it, so H3 and SAM never share its weights.

Two tools (studio assistant and MCP):

- **match_people**: one photo per person (at most 6). Henge detects the camera cuts, takes three keyframes per
  shot and asks Molmo2 to point at the person from the photo. Each point is checked in reverse: a crop around
  it is compared with all the photos side by side, and the point is kept only if Molmo2 picks the same photo.
  A person is marked in a shot only when this holds in two of its three keyframes. In the assistant the photo is
  an explanation image from the chat (the performer in the video) or a Picture that shows the same person; the
  marks are applied to one subject per person, bound to its picture_slots.
- **point_video**: a text description of the target in one shot (at most 30 s), with time-indexed points.

Molmo2 cannot read images and a video in the same request, which is why match_people compares the photo with
keyframes instead of tracking in the video. Points are proposals: check the previews.

## Setup

```bash
python -m venv ~/envs/molmo2
~/envs/molmo2/bin/pip install torch torchvision transformers==4.57.1 accelerate einops pillow molmo_utils decord2 compressed-tensors
huggingface-cli download tollea1234/Molmo2-8B-FP8 --local-dir /models/Molmo2-8B-FP8   # ~14 GB
```

The official `allenai/Molmo2-8B` also works (about 35 GB on disk, stored in FP32). The FP8 checkpoint loads
through transformers with `compressed-tensors` and needs about 12 GB of VRAM.

In `.env.local`:

```
HENGE_MOLMO_PYTHON=/home/you/envs/molmo2/bin/python
HENGE_MOLMO_MODEL=/models/Molmo2-8B-FP8
```

`GET /assistant/pointing` reports whether it is configured. match_people takes about 50 s to load the model
plus roughly 30 s per shot for three people.
