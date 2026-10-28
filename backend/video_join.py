"""Join overlapping generated windows without dissolving two different poses."""
import numpy as np


def join_overlap(a, b, overlap):
    """Return two pieces with the original timeline length and no pixel blending.

    Match the incoming window's colour, then switch at the closest matching
    frame in the overlap. A pose mismatch can still jump, but never ghosts.
    """
    n = int(overlap)
    if n <= 0 or len(a) < n or len(b) <= n or a.shape[1:] != b.shape[1:]:
        raise ValueError('Invalid video overlap')
    tail = a[-n:].astype(np.float32)
    head = b[:n].astype(np.float32)
    mean_t, mean_h = tail.mean((0, 1, 2)), head.mean((0, 1, 2))
    gain = np.clip((tail.std((0, 1, 2)) + 1e-3) / (head.std((0, 1, 2)) + 1e-3), .85, 1.15)
    fixed = np.rint(np.clip((b.astype(np.float32) - mean_h) * gain + mean_t, 0, 255)).astype(np.uint8)
    # Compare aligned frames, rather than consecutive ones: real movement must
    # not be mistaken for an error at the join. Prefer the middle on a tie.
    errors = np.abs(tail - fixed[:n].astype(np.float32)).mean((1, 2, 3))
    order = sorted(range(n), key=lambda i: (float(errors[i]), abs(i - (n - 1) / 2)))
    seam = order[0]
    previous = np.concatenate((a[:-n], a[-n:][:seam], fixed[seam:n]))
    return previous, fixed[n:]
