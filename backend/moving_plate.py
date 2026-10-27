"""Moving plate: put a new background picture behind the people of a guide video, moving it with the original camera.

Adapted from the community `moving_plate.py` (Anime Recast with H3): camera motion is tracked on the original
background only (Lucas-Kanade on corners outside the dilated people mask, a RANSAC similarity per frame, chained
through each shot) and applied to the picture, with a slow push-in so a locked-off shot still breathes. Henge runs it
automatically per camera shot (cuts detected from the frames) instead of hand-tuned shot tables.
Needs opencv-python and numpy; the people masks come from BiRefNet in ComfyUI (white = people).
"""
import subprocess
import cv2
import numpy as np


def read_frames(path):
    cap = cv2.VideoCapture(str(path)); frames = []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(f)
    return frames


def scene_cuts(frames, threshold=.18):
    """First frame of each camera shot after the first: a big jump between small grey thumbnails."""
    small = [cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (32, 18), interpolation=cv2.INTER_AREA).astype(np.float32) / 255 for f in frames]
    diff = [float(np.abs(small[i] - small[i - 1]).mean()) for i in range(1, len(small))]
    if not diff: return []
    floor = max(threshold, float(np.median(diff)) * 4); cuts, last = [], 0
    for i, d in enumerate(diff, 1):
        if d > floor and i - last >= 6: cuts.append(i); last = i
    return cuts


def track(a, b, people):
    """2x3 similarity taking background points of frame a to frame b, or None when the background can't be tracked."""
    ga, gb = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    keep = (cv2.dilate((people > .2).astype(np.uint8), np.ones((25, 25), np.uint8)) == 0).astype(np.uint8) * 255
    p0 = cv2.goodFeaturesToTrack(ga, 400, .01, 8, mask=keep)
    if p0 is None or len(p0) < 25: return None
    p1, st, _ = cv2.calcOpticalFlowPyrLK(ga, gb, p0, None, winSize=(21, 21), maxLevel=3)
    good = st.ravel() == 1
    if good.sum() < 25: return None
    A, inl = cv2.estimateAffinePartial2D(p0[good], p1[good], method=cv2.RANSAC, ransacReprojThreshold=2.)
    return A if inl is not None and int(inl.sum()) >= 20 else None


def render(source, masks_video, picture, out, fps=24., zoom=1.3, follow=.5, push=.05, fireflies=0, seed=7, log=print):
    """Write `out` (no audio): `source` with its background replaced by `picture`, moving with the camera.
    zoom: how far the picture is enlarged so the camera can move inside it; follow: share of the camera's own motion the
    far background follows (parallax); push: push-in over each shot; fireflies: optional glowing particles."""
    frames, mframes = read_frames(source), read_frames(masks_video)
    if not frames: raise ValueError('The guide video has no frames')
    H, W = frames[0].shape[:2]; n = min(len(frames), len(mframes))
    masks = [cv2.resize(cv2.cvtColor(m, cv2.COLOR_BGR2GRAY), (W, H)).astype(np.float32) / 255 for m in mframes[:n]]
    frames = frames[:n]; bg = cv2.imread(str(picture))
    if bg is None: raise ValueError('The background picture could not be read')
    rng = np.random.default_rng(seed); out_frames = [f.copy() for f in frames]
    bounds = [0, *scene_cuts(frames), n]
    for s, e in zip(bounds[:-1], bounds[1:]):
        # Pass 1: the camera path of this shot (frame s -> t), damped by `follow` for a far background.
        path, C, prev = [np.eye(3)], np.eye(3), None
        for t in range(s + 1, e):
            A = track(frames[t - 1], frames[t], masks[t - 1])
            if A is None:   # wipes, speed lines, a full-frame person: keep the last motion, slowing down
                A = np.float32([[1, 0, prev[0, 2] * .8], [0, 1, prev[1, 2] * .8]]) if prev is not None else np.float32([[1, 0, 0], [0, 1, 0]])
            prev = A; A = A.copy(); A[:, 2] *= follow
            C = np.vstack([A, [0, 0, 1]]) @ C; path.append(C)
        # Pass 2: every frame's corners mapped back onto the picture (whatever the camera does: pan, rotation, zoom,
        # push-in); the picture is sized and placed to cover them all, so it never runs out into mirrored edges.
        corners = np.float64([[0, 0, 1], [W, 0, 1], [0, H, 1], [W, H, 1]]).T
        seen = []
        for k, C in enumerate(path):
            z = 1 + push * k / max(1, e - s - 1)
            D = np.float64([[z, 0, (1 - z) * W / 2], [0, z, (1 - z) * H / 2], [0, 0, 1]])
            seen.append((np.linalg.inv(D @ C) @ corners)[:2].T)
        seen = np.concatenate(seen); lo, hi = seen.min(0), seen.max(0); span = hi - lo
        need = max(zoom, span[0] * 1.02 / W, span[1] * 1.02 / H)
        PW, PH = int(W * need), int(H * need); sc = max(PW / bg.shape[1], PH / bg.shape[0])
        big = cv2.resize(bg, (int(bg.shape[1] * sc) + 1, int(bg.shape[0] * sc) + 1), interpolation=cv2.INTER_LANCZOS4)
        ox = (big.shape[1] - span[0]) / 2 - lo[0]; oy = (big.shape[0] - span[1]) / 2 - lo[1]
        plate = big.astype(np.float32)
        if fireflies:
            pos = np.c_[rng.uniform(0, big.shape[1], fireflies), rng.uniform(0, big.shape[0] * .85, fireflies)]
            vel = np.c_[rng.uniform(-.35, .35, fireflies), rng.uniform(-.55, .1, fireflies)] * need
            rad, per, ph = rng.uniform(1.2, 2.6, fireflies) * need, rng.uniform(14, 34, fireflies), rng.uniform(0, 2 * np.pi, fireflies)
        shifts = []
        for t in range(s, e):
            C = path[t - s]; layer = plate
            if fireflies:
                glow = np.zeros_like(plate); k = t - s
                for (x, y), (vx, vy), r, p_, f_ in zip(pos, vel, rad, per, ph):
                    b = .35 + .65 * max(0., np.sin(2 * np.pi * k / p_ + f_))
                    cv2.circle(glow, (int(x + vx * k), int(y + vy * k)), max(1, int(round(r))), (80 * b, 200 * b, 255 * b), -1, cv2.LINE_AA)
                layer = np.clip(plate + glow + cv2.GaussianBlur(glow, (0, 0), 4 * need) * 2.5, 0, 255)
            z = 1 + push * (t - s) / max(1, e - s - 1)
            D = np.float64([[z, 0, (1 - z) * W / 2], [0, z, (1 - z) * H / 2], [0, 0, 1]])
            M = (D @ C @ np.float64([[1, 0, -ox], [0, 1, -oy], [0, 0, 1]]))[:2]
            bgt = cv2.warpAffine(layer, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            m = masks[t][..., None]
            out_frames[t] = np.clip(frames[t] * m + bgt * (1 - m), 0, 255).astype(np.uint8)
            shifts.append(float(np.hypot(C[0, 2], C[1, 2])))
        log(f'plate shot {s}-{e}: camera moved up to {max(shifts or [0]):.0f}px, picture zoom {need:.2f}')
    p = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(fps), '-i', '-',
                        '-c:v', 'libx264', '-crf', '12', '-preset', 'medium', '-pix_fmt', 'yuv420p', str(out)], input=np.stack(out_frames).tobytes())
    if p.returncode: raise RuntimeError('ffmpeg could not write the moving plate')
    return {'frames': n, 'shots': len(bounds) - 1}
