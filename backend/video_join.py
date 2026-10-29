"""Join overlapping generated windows without dissolving two different poses."""
import numpy as np


def overlap_match(tail, head):
    """Colour transform and hard seam from aligned overlap samples only."""
    if len(tail)==0 or tail.shape!=head.shape:raise ValueError('Invalid overlap samples')
    tail=tail.astype(np.float32);head=head.astype(np.float32)
    mean_t,mean_h=tail.mean((0,1,2)),head.mean((0,1,2))
    gain=np.clip((tail.std((0,1,2))+1e-3)/(head.std((0,1,2))+1e-3),.85,1.15)
    fixed=np.rint(np.clip((head-mean_h)*gain+mean_t,0,255)).astype(np.uint8)
    errors=np.abs(tail-fixed.astype(np.float32)).mean((1,2,3))
    seam=min(range(len(tail)),key=lambda i:(float(errors[i]),abs(i-(len(tail)-1)/2)))
    return seam,mean_h,gain,mean_t


def join_overlap(a, b, overlap):
    """Array reference implementation: fixed timeline length, colour match, no pixel blending."""
    n=int(overlap)
    if n<=0 or len(a)<n or len(b)<=n or a.shape[1:]!=b.shape[1:]:raise ValueError('Invalid video overlap')
    seam,mean_h,gain,mean_t=overlap_match(a[-n:],b[:n])
    fixed=np.rint(np.clip((b.astype(np.float32)-mean_h)*gain+mean_t,0,255)).astype(np.uint8)
    previous=np.concatenate((a[:-n],a[-n:][:seam],fixed[seam:n]))
    return previous,fixed[n:]
