"""Segment explicit marks with SAM's point decoder, then track within camera cuts."""
import json
import torch


def track_marks(images, model, subjects, segment_start, bounds, detect, track, unpack):
    n,h,w=images.shape[:3]
    masks=[];chosen=[];warnings=[];anchored=set()
    for subject in subjects:
        anchors=[a for a in subject.get('anchors',[]) if segment_start<=a['time_seconds']<segment_start+n/24]
        if not anchors:continue
        anchored.add(subject['id'])
        for left,right in zip(bounds,bounds[1:]):
            scene_marks=[a for a in anchors if left<=min(n-1,round((a['time_seconds']-segment_start)*24))<right]
            if not scene_marks:continue
            seeded=False
            for anchor in scene_marks:
                k=min(n-1,round((anchor['time_seconds']-segment_start)*24))
                fw,fh=anchor['frame_width'],anchor['frame_height'];scale=min(w/fw,h/fh)
                x=min(w-1,max(0,round(anchor['x']*fw*scale+(w-fw*scale)/2)))
                y=min(h-1,max(0,round(anchor['y']*fh*scale+(h-fh*scale)/2)))
                # SAM3_Detect's extra refinement drops the point prompt. On small subjects it can erase a valid seed.
                found=detect(model=model,image=images[k:k+1],positive_coords=json.dumps([{'x':x,'y':y}]),refine_iterations=1,individual_masks=True)[0].cpu()>.5
                candidates=[m for m in found if bool(m[y,x])]
                if not candidates:continue
                seed=max(candidates,key=lambda m:int(m.sum())).float()[None]
                full=torch.zeros(n,h,w,dtype=torch.bool);full[k]=seed[0].bool()
                for indices in (list(range(k,right)),list(range(k,left-1,-1))):
                    if len(indices)==1:continue
                    data=track(images=images[indices],model=model,initial_mask=seed,max_objects=1)[0]
                    packed=data.get('packed_masks')
                    if packed is None:continue
                    propagated=unpack(packed).cpu().bool()
                    if tuple(propagated.shape[-2:])!=(h,w):
                        propagated=torch.nn.functional.interpolate(propagated.float(),size=(h,w),mode='nearest').bool()
                    full[indices]|=propagated[:,0]
                # Keep the explicit point segmentation even if propagation loses the object immediately.
                full[k]=seed[0].bool()
                chosen.append((len(masks),subject,'mark'));masks.append(full);seeded=True;break
            if not seeded:warnings.append(f"{subject['label']}: SAM could not segment the marked point in this scene; move the mark inside the subject")
    stacked=torch.stack(masks,dim=1) if masks else torch.zeros(n,0,h,w,dtype=torch.bool)
    return stacked,chosen,warnings,anchored
