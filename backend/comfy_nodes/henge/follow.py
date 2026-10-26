"""Following marked people from shot to shot.

The user marks each person once. In every shot HengeGuide must still decide which SAM track is which person:
1. a mark inside the shot (the user's click) wins;
2. a shot that continues the previous one without a cut gets `carry`: where that person was in the previous shot at
   this shot's first frame;
3. after a camera cut people can be anywhere, so they are recognised by look: `signature` is a colour histogram of the
   person's upper and lower body, compared with every unclaimed track.
A person that cannot be told apart is left unmarked for that shot and reported, never guessed and never fatal."""
import torch

BINS = 4  # per RGB channel, for each body half


def signature(images: torch.Tensor, masks: torch.Tensor, frames: int = 24) -> list | None:
    """Normalised RGB histograms of the upper and lower half of the person over up to `frames` visible frames."""
    visible = torch.nonzero(masks.flatten(1).sum(1) > 64).flatten()
    if not len(visible):
        return None
    pick = visible[torch.linspace(0, len(visible) - 1, min(frames, len(visible))).round().long()]
    halves = [torch.zeros(BINS ** 3), torch.zeros(BINS ** 3)]
    for k in pick.tolist():
        m = masks[k]
        ys = torch.nonzero(m.any(1)).flatten()
        mid = int((ys[0] + ys[-1]) // 2)
        q = (images[k, ..., :3].clamp(0, 1) * (BINS - .001)).long()
        code = q[..., 0] * BINS * BINS + q[..., 1] * BINS + q[..., 2]
        for half, rows in enumerate((slice(0, mid), slice(mid, None))):
            sel = code[rows][m[rows]]
            if sel.numel():
                halves[half] += torch.bincount(sel, minlength=BINS ** 3).float()
    out = []
    for h in halves:
        out += (h / h.sum()).tolist() if h.sum() > 0 else [0.] * BINS ** 3
    return [round(v, 5) for v in out]


def similarity(a: list, b: list) -> float:
    """Histogram intersection, averaged over the two body halves (0 = nothing alike, 1 = same colours)."""
    n = BINS ** 3
    ta, tb = torch.tensor(a), torch.tensor(b)
    return float((torch.minimum(ta[:n], tb[:n]).sum() + torch.minimum(ta[n:], tb[n:]).sum()) / 2)


def points(masks: torch.Tensor) -> list:
    """Per frame, a pixel of the mask nearest its centroid (normalised x, y), or None when the person is not visible."""
    n, h, w = masks.shape
    out = []
    for k in range(n):
        ys, xs = torch.nonzero(masks[k], as_tuple=True)
        if len(ys) < 64:
            out.append(None); continue
        cy, cx = ys.float().mean(), xs.float().mean()
        i = int(torch.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
        out.append([round(int(xs[i]) / w, 4), round(int(ys[i]) / h, 4)])
    return out


# Recognition by colour histogram was measured on a real cut (car clip): the man matched the woman's look 0.81 against
# his own 0.49, a confident wrong answer. Off until a real re-identification feature replaces it; a person seen only
# after a cut is left unmarked (and reported) rather than given someone else's colour.
LOOK_MATCHING = False


def choose(subjects: list, masks: torch.Tensor, images: torch.Tensor, segment_start: float, min_look: float = .25, margin: float = .08):
    """Assign SAM tracks (masks: N, tracks, H, W) to subjects. Returns (chosen [(track, subject, how)], warnings)."""
    n, tracks, h, w = masks.shape
    used, chosen, warnings = set(), [], []

    def score_point(k, x, y):
        k = min(n - 1, max(0, k))
        return masks[k, :, min(h - 1, max(0, round(y))), min(w - 1, max(0, round(x)))].int()

    def take(scores, s, how):
        scores = scores.clone()
        for u in used:
            scores[u] = 0
        best = int(scores.argmax())
        if scores[best] == 0 or int((scores == scores[best]).sum()) > 1:
            return False
        used.add(best); chosen.append((best, s, how)); return True

    pending = []
    for s in subjects:
        anchors = [a for a in s.get('anchors', []) if segment_start <= a['time_seconds'] < segment_start + n / 24]
        if anchors:
            scores = torch.zeros(tracks, dtype=torch.int32)
            for a in anchors:
                fw, fh = a['frame_width'], a['frame_height']; scale = min(w / fw, h / fh)
                scores += score_point(round((a['time_seconds'] - segment_start) * 24),
                                      a['x'] * fw * scale + (w - fw * scale) / 2, a['y'] * fh * scale + (h - fh * scale) / 2)
            if take(scores, s, 'mark'):
                continue
            warnings.append(f"{s['label']}: the mark in this shot is not on one person; trying by look")
        elif s.get('carry'):
            c = s['carry']
            scores = sum(score_point(k, c['x'] * w, c['y'] * h) for k in range(3))
            if take(scores, s, 'carry'):
                continue
        pending.append(s)
    # Recognise the rest by look, best matches first, so two people never claim the same track.
    options = []
    for s in pending if LOOK_MATCHING else []:
        if not s.get('signature'):
            warnings.append(f"{s['label']}: not marked yet and never seen before; left unmarked in this shot"); continue
        for t in range(tracks):
            if t in used:
                continue
            sig = signature(images, masks[:, t])
            if sig:
                options.append((similarity(s['signature'], sig), s, t))
    done = set()
    for sim, s, t in sorted(options, key=lambda o: -o[0]):
        if s['id'] in done or t in used:
            continue
        rivals = [o for o in options if o[1]['id'] == s['id'] and o[2] != t and o[2] not in used]
        # Framing changes a lot across cuts (a close-up shows more face), so the decision is relative: the person
        # must look clearly more like this track than like any other one, with a low absolute floor.
        if sim < min_look or (rivals and sim - max(r[0] for r in rivals) < margin):
            continue
        used.add(t); done.add(s['id']); chosen.append((t, s, 'look'))
    for s in pending:
        if s['id'] not in done and (s.get('signature') or not LOOK_MATCHING):
            warnings.append(f"{s['label']}: not marked in this shot (it starts after a camera cut); left unmarked. Mark them once in this shot to colour them.")
    return chosen, warnings


def report(chosen: list, masks: torch.Tensor, images: torch.Tensor, warnings: list) -> dict:
    """What the bridge needs for the next shot: per subject its track's look and where it is in every frame."""
    return {'warnings': warnings,
            'subjects': [{'id': s['id'], 'label': s['label'], 'how': how, 'signature': signature(images, masks[:, t]), 'points': points(masks[:, t])}
                         for t, s, how in chosen]}


class HengeSubjectLook:
    """The look (signature) of one marked person, from the frame and point where the user clicked. Run once before
    the shots, so every shot can recognise everyone, including people marked only later in the video."""
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': ('IMAGE',), 'subject_id': ('STRING', {'default': ''}),
                             'x': ('FLOAT', {'default': .5, 'min': 0, 'max': 1}), 'y': ('FLOAT', {'default': .5, 'min': 0, 'max': 1}),
                             'sam_checkpoint': ('STRING', {'default': 'sam3.1_multiplex_fp16.safetensors'})}}
    RETURN_TYPES = ()
    FUNCTION = 'look'
    OUTPUT_NODE = True
    CATEGORY = 'Henge'

    def look(self, image, subject_id, x, y, sam_checkpoint):
        import json
        import comfy.model_management as mm
        import comfy.sd
        import folder_paths
        from comfy_extras.nodes_sam3 import SAM3_Detect
        sam = comfy.sd.load_checkpoint_guess_config(folder_paths.get_full_path_or_raise('checkpoints', sam_checkpoint), output_vae=False)[0]
        frame = image[:1]; h, w = frame.shape[1:3]
        masks, _ = SAM3_Detect.execute(sam, frame, positive_coords=json.dumps([{'x': int(x * w), 'y': int(y * h)}]), refine_iterations=2, individual_masks=True)
        del sam; mm.unload_all_models(); mm.soft_empty_cache()
        mask = (masks.cpu()[:1] > .5) if masks.numel() else torch.zeros(1, h, w, dtype=torch.bool)
        return {'ui': {'henge_look': [json.dumps({'id': subject_id, 'signature': signature(frame.cpu(), mask)})]}}
