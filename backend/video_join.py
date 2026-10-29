"""Join overlapping generated windows without dissolving two different poses."""
import numpy as np


def overlap_match(tail, head):
    """Choose a hard seam from aligned samples without changing their colours."""
    if len(tail)==0 or tail.shape!=head.shape:raise ValueError('Invalid overlap samples')
    errors=np.abs(tail.astype(np.float32)-head.astype(np.float32)).mean((1,2,3))
    return min(range(len(tail)),key=lambda i:(float(errors[i]),abs(i-(len(tail)-1)/2)))


def join_overlap(a, b, overlap):
    """Array reference implementation: fixed timeline length, original colours, no pixel blending."""
    n=int(overlap)
    if n<=0 or len(a)<n or len(b)<=n or a.shape[1:]!=b.shape[1:]:raise ValueError('Invalid video overlap')
    seam=overlap_match(a[-n:],b[:n])
    previous=np.concatenate((a[:-n],a[-n:][:seam],b[seam:n]))
    return previous,b[n:]
