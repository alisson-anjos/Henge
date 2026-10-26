"""HengeFindPeople: number the people (or animals) in one frame for the studio assistant.

SAM 3.1 detects every subject of the given kind; each gets a number drawn on the frame, a box and a point that lies
well inside its mask (the deepest pixel after erosion), so a mark placed there tracks that subject and not the
background between their legs. Returns the numbered overlay and the list as JSON."""
import json

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont

import comfy.model_management as mm
import comfy.sd
import folder_paths

PALETTE = [(230, 70, 60), (45, 125, 225), (50, 180, 90), (235, 205, 35), (205, 55, 180), (30, 200, 205), (240, 130, 35), (135, 75, 210)]


def inner_point(mask: torch.Tensor) -> tuple[int, int]:
    """A pixel deep inside the mask: erode until one more step would empty it, then take the remaining pixel nearest
    to the remaining region's centroid."""
    m = mask[None, None].float()
    last = m
    for _ in range(256):
        eroded = -F.max_pool2d(-F.pad(m, (1, 1, 1, 1), value=0.), 3, 1)   # the frame edge erodes too
        if eroded.sum() == 0:
            break
        last = m = eroded
    ys, xs = torch.nonzero(last[0, 0] > 0, as_tuple=True)
    cy, cx = ys.float().mean(), xs.float().mean()
    i = int(torch.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
    return int(xs[i]), int(ys[i])


class HengeFindPeople:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': ('IMAGE',), 'kind': (['person', 'animal'],),
                             'threshold': ('FLOAT', {'default': .4, 'min': .05, 'max': .95, 'step': .05}),
                             'sam_checkpoint': ('STRING', {'default': 'sam3.1_multiplex_fp16.safetensors'})}}
    RETURN_TYPES = ('IMAGE', 'STRING')
    RETURN_NAMES = ('overlay', 'people')
    FUNCTION = 'find'
    CATEGORY = 'Henge'

    def find(self, image, kind, threshold, sam_checkpoint):
        from comfy_extras.nodes_sam3 import SAM3_Detect
        loaded = comfy.sd.load_checkpoint_guess_config(folder_paths.get_full_path_or_raise('checkpoints', sam_checkpoint), output_vae=False)
        sam, clip = loaded[:2]
        cond = clip.encode_from_tokens_scheduled(clip.tokenize(kind))
        # SAM3_Detect keeps one detection per text prompt unless the prompt asks for more (the SAM3 text encode
        # node's multi-prompt form): ask for up to 8.
        cond = [[cond[0][0], {**cond[0][1], 'sam3_multi_cond': [{'cond': cond[0][0], 'attention_mask': cond[0][1].get('attention_mask'), 'max_detections': 8}]}]]
        frame = image[:1]
        masks, boxes = SAM3_Detect.execute(sam, frame, conditioning=cond, threshold=threshold, refine_iterations=1, individual_masks=True)
        del sam, clip
        mm.unload_all_models(); mm.soft_empty_cache()
        masks = masks.cpu() > .5 if masks.numel() else torch.zeros(0, *frame.shape[1:3], dtype=torch.bool)
        h, w = frame.shape[1:3]
        people = []
        for i, (m, b) in enumerate(zip(masks, boxes[0] if boxes else [])):
            if int(m.sum()) < 64:
                continue
            x, y = inner_point(m)
            people.append({'number': len(people) + 1, 'x': round(x / w, 4), 'y': round(y / h, 4),
                           'box': [round(b['x'] / w, 4), round(b['y'] / h, 4), round(b['width'] / w, 4), round(b['height'] / h, 4)],
                           'score': round(float(b.get('score', 0)), 3), '_mask': m})
        # Left to right, so "number 1" reads naturally.
        people.sort(key=lambda p: p['box'][0])
        rgb = (frame[0, ..., :3].clamp(0, 1) * 255).byte().numpy()
        out = rgb.astype(np.float32)
        for n, p in enumerate(people, 1):
            p['number'] = n
            color = np.array(PALETTE[(n - 1) % len(PALETTE)], np.float32)
            m = p.pop('_mask').numpy()
            out[m] = out[m] * .55 + color * .45
        canvas = Image.fromarray(out.clip(0, 255).astype(np.uint8))
        draw = ImageDraw.Draw(canvas)
        size = max(16, h // 18)
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:
            font = ImageFont.load_default()
        for p in people:
            x, y = p['x'] * w, p['y'] * h
            color = PALETTE[(p['number'] - 1) % len(PALETTE)]
            bx, by, bw, bh = (p['box'][0] * w, p['box'][1] * h, p['box'][2] * w, p['box'][3] * h)
            draw.rectangle([bx, by, bx + bw, by + bh], outline=color, width=max(2, h // 240))
            r = size * .75
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(255, 255, 255), width=2)
            draw.text((x, y), str(p['number']), fill=(255, 255, 255), font=font, anchor='mm')
        overlay = torch.from_numpy(np.asarray(canvas, np.float32) / 255)[None]
        return (overlay, json.dumps({'kind': kind, 'width': int(w), 'height': int(h), 'people': people}))
