"""Henge media, guide preparation and H3 conditioning nodes. No model downloads."""
import hashlib,json,math,os,subprocess
from pathlib import Path
import numpy as np
import torch
from PIL import Image
import folder_paths,comfy.utils,comfy.sd,comfy.model_management as mm
from .clip_video import clip_with_video_context
from . import follow
from .point_tracking import track_marks
from .report import ui_report


def input_path(name):
    root=Path(folder_paths.get_input_directory()).resolve();p=(root/name).resolve()
    if not p.is_relative_to(root) or not p.is_file():raise ValueError('Unknown Henge input asset')
    return p


def read_frames(path,width,height,length):
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vf',f'fps=24,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2','-frames:v',str(length),'-f','rawvideo','-pix_fmt','rgb24','-threads','1','pipe:1'])
    x=np.frombuffer(raw,np.uint8).reshape(-1,height,width,3).copy()
    if len(x)==0:raise ValueError('Video decoded no frames')
    if len(x)<length:x=np.concatenate([x,np.repeat(x[-1:],length-len(x),axis=0)])
    return torch.from_numpy(x).float()/255


class HengeLoadShot:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'video':('STRING',),'pictures':('STRING',{'default':'[]'}),'width':('INT',{'default':512,'min':32,'step':32}),'height':('INT',{'default':288,'min':32,'step':32}),'length':('INT',{'default':107,'min':5,'max':3600})}}
    RETURN_TYPES=('IMAGE','HENGE_REFS');FUNCTION='load';CATEGORY='Henge'
    def load(self,video,pictures,width,height,length):
        refs=[]
        for p in json.loads(pictures):
            with Image.open(input_path(p)) as im:refs.append(torch.from_numpy(np.asarray(im.convert('RGB')).copy()).float()[None]/255)
        return read_frames(input_path(video),width,height,length),refs


VIDEO_EXTENSIONS=('.mp4','.mov','.webm','.mkv','.avi','.m4v')

class HengeLoadVideo:
    """Load Video for exported Henge workflows: a file from ComfyUI's input folder (with an upload button), decoded
    exactly like HengeLoadShot (FFmpeg at 24 fps, fit and pad to width x height, last frame repeated up to length).
    ComfyUI's own Load Video decodes colours slightly differently, so a re-run would not match the original job."""
    @classmethod
    def INPUT_TYPES(cls):
        root=folder_paths.get_input_directory()
        files=sorted(f for f in os.listdir(root) if f.lower().endswith(VIDEO_EXTENSIONS) and os.path.isfile(os.path.join(root,f)))
        return {'required':{'video':(files,{'video_upload':True}),'width':('INT',{'default':512,'min':32,'step':32}),'height':('INT',{'default':288,'min':32,'step':32}),'length':('INT',{'default':107,'min':1})}}
    RETURN_TYPES=('IMAGE',);FUNCTION='load';CATEGORY='Henge'
    def load(self,video,width,height,length):return (read_frames(input_path(video),width,height,length),)
    @classmethod
    def IS_CHANGED(cls,video,**kwargs):
        digest=hashlib.sha256()
        with input_path(video).open('rb') as source:
            for chunk in iter(lambda:source.read(1<<20),b''):digest.update(chunk)
        return digest.hexdigest()

def scene_cuts(images,threshold=.18,spike=.1,window=6):
    """Frame indexes where a camera cut starts (a big jump between consecutive small grey thumbnails). A cut between
    two similar-looking shots can stay under the absolute threshold (Top Gun: 0.16 against 0.18), so a single-frame
    spike above `spike` that is far above its neighbours also counts; motion raises the neighbours too."""
    small=torch.nn.functional.interpolate(images.mean(-1,keepdim=True).permute(0,3,1,2),size=(18,32),mode='area')[:,0]
    diff=(small[1:]-small[:-1]).abs().mean((1,2))
    if len(diff)==0:return []
    floor=max(threshold,float(diff.median())*4)
    values=diff.tolist();cuts,last=[],0
    for i,d in enumerate(values,1):
        around=values[max(0,i-1-window):i-1]+values[i:i+window]
        isolated=bool(around) and d>spike and d>8*max(sorted(around)[len(around)//2],.004)
        if (d>floor or isolated) and i-last>=6:cuts.append(i);last=i
    return cuts

def track_scenes(images,sam,cond,threshold,per_scene=6,total=16,min_frames=3):
    """SAM 3.1 people tracks for a shot, tracked scene by scene. One tracking pass over a whole shot gives up once its
    track slots are used: a blurry opening or a cut can spend them all on detections that last a frame, and the people
    seen later never get a track. Each scene between camera cuts gets its own pass; short-lived tracks are dropped.
    Returns N,tracks,h,w (bool) or None when nobody is found."""
    from comfy_extras.nodes_sam3 import SAM3_VideoTrack
    from comfy.ldm.sam3.tracker import unpack_masks
    n,h,w=images.shape[:3];bounds=[0,*scene_cuts(images),n];kept=[]
    for a,b in zip(bounds[:-1],bounds[1:]):
        if b-a<2:continue
        packed=SAM3_VideoTrack.execute(images=images[a:b],model=sam,conditioning=cond,detection_threshold=threshold,max_objects=8,detect_interval=1)[0].get('packed_masks')
        if packed is None or packed.shape[1]==0:continue
        m=unpack_masks(packed).cpu().bool()
        if tuple(m.shape[-2:])!=(h,w):m=torch.nn.functional.interpolate(m.float(),size=(h,w),mode='nearest').bool()
        alive=m.flatten(2).any(2).sum(0) # frames each track is present
        best=[int(t) for t in alive.argsort(descending=True)[:per_scene] if int(alive[t])>=min(min_frames,b-a)]
        kept+=[(int(alive[t]),a,m[:,t]) for t in best]
    if not kept:return None
    kept=sorted(kept,key=lambda k:-k[0])[:total]
    masks=torch.zeros((n,len(kept),h,w),dtype=torch.bool)
    for i,(_,a,m) in enumerate(kept):masks[a:a+len(m),i]=m
    return masks

_BFS_BLUR=[]

def bfs_blur():
    """BFS source blur (ComfyUI-BFSNodes, installed next to Henge), imported as a namespace package so the BFS node
    registration does not run twice. None when the BFS nodes are not installed."""
    if _BFS_BLUR:return _BFS_BLUR[0]
    import glob,importlib,sys,types
    found=None
    for root in folder_paths.get_folder_paths('custom_nodes'):
        hit=sorted(glob.glob(os.path.join(root,'*','bfs_source_blur.py')))
        if hit:found=os.path.dirname(hit[0]);break
    if found:
        package=types.ModuleType('henge_bfs');package.__path__=[found];sys.modules.setdefault('henge_bfs',package)
        _BFS_BLUR.append(importlib.import_module('henge_bfs.bfs_source_blur'))
    else:_BFS_BLUR.append(None)
    return _BFS_BLUR[0]

def blur_guide(images,spec,area=None):
    """The guide frames with the source person blurred (or colour-inverted) as the BFS planner does: the model reads
    the pose and motion but has no face to copy. 'masked area' blurs only the marked people (area)."""
    mode=spec.get('source_blur','off')
    if not mode or mode=='off':return images
    blur=bfs_blur()
    if blur is None:raise ValueError('Source blur needs the BFS nodes (ComfyUI-BFSNodes) installed with Henge')
    out=blur.blur_source(images,mode,1.,'Henge source blur',spec.get('source_blur_segmenter','SAM 3.1'),spec.get('source_blur_effect','blur'),area.float() if area is not None else None)
    return out.to(images.dtype)

class HengeGuide:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'representation':(['original','2d','3d','mask'],),'bindings':('STRING',{'default':'[]'}),'source_kind':(['human','animal','other'],),'segment_start':('FLOAT',{'default':0,'round':False,'precision':15,'step':.000001}),'sam_checkpoint':('STRING',{'default':'sam3.1_multiplex_fp16.safetensors'}),'body_model':('STRING',{'default':'sam_3d_body_dinov3_bf16.safetensors'}),'preserve_objects':('STRING',{'default':'[]'})},'optional':{'mask_settings':('STRING',{'default':'{}'})}}
    RETURN_TYPES=('IMAGE','MASK','HENGE_REGIONS');FUNCTION='prepare';CATEGORY='Henge'
    def prepare(self,images,representation,bindings,source_kind,segment_start,sam_checkpoint,body_model,preserve_objects="[]",mask_settings='{}'):
        spec={**DEFAULT_MASK,**json.loads(mask_settings or '{}')}
        empty=torch.zeros(images.shape[:3])
        subjects=json.loads(bindings)
        if representation=='original':
            # Only 'masked area' needs the people tracked; the other blur regions find every person themselves.
            if not str(spec.get('source_blur','off')).startswith('masked area') or not subjects:return (blur_guide(images,spec),empty,{})
        if not subjects:raise ValueError('Color guides need a selected subject and its reference binding')
        if representation=='3d' and source_kind!='human':raise ValueError('SAM 3D Body supports human sources. Use a 2D color guide for animals.')
        from comfy_extras.nodes_sam3 import SAM3_VideoTrack,SAM3_Detect
        from comfy.ldm.sam3.tracker import unpack_masks,pack_masks
        loaded=comfy.sd.load_checkpoint_guess_config(folder_paths.get_full_path_or_raise('checkpoints',sam_checkpoint),output_vae=False)
        sam,clip=loaded[:2]
        cond=clip.encode_from_tokens_scheduled(clip.tokenize('person' if source_kind=='human' else 'animal'))
        # Track identity before choosing colors; coordinates are normalized source-image coordinates.
        masks,picked,warnings,anchored=track_marks(images,sam,subjects,segment_start,
            [0,*scene_cuts(images),len(images)],SAM3_Detect.execute,SAM3_VideoTrack.execute,unpack_masks)
        remaining=[s for s in subjects if s['id'] not in anchored]
        automatic=track_scenes(images,sam,cond,float(spec['threshold']) if representation=='mask' else .4) if remaining else None
        if automatic is not None:
            extra,notes=follow.choose(remaining,automatic,images,segment_start)
            picked.extend((t+masks.shape[1],s,how) for t,s,how in extra);warnings.extend(notes)
            masks=torch.cat((masks,automatic),dim=1)
        if not picked and representation=='mask':
            del sam,clip;mm.unload_all_models();mm.soft_empty_cache()
            raise ValueError('SAM could not segment the marked subject in this shot. Move the mark inside the subject in this shot and preview the mask again. '+ '; '.join(warnings))
        if masks.shape[1]==0:
            # Nobody in this shot (a cutaway, an empty room): it goes through unmarked instead of failing the job.
            del sam,clip;mm.unload_all_models();mm.soft_empty_cache()
            return {'ui':ui_report({'henge_tracks':[json.dumps({'warnings':['Nobody found in this shot; it was left unmarked'],'subjects':[]})]}),'result':(images if representation=='original' else blur_guide(images,spec),empty,{})}
        n,h,w=images.shape[:3]
        # Marks, continuity from the previous shot and recognition by look (follow.py): never guessed by position.
        chosen=[(t,s,tuple(int(s['hex'].lstrip('#')[i:i+2],16) for i in [0,2,4])) for t,s,_ in picked]
        tracking={'ui':ui_report({'henge_tracks':[json.dumps(follow.report(picked,masks,images,warnings))]})}
        attention_regions={}
        for idx,subject,_ in chosen:
            for slot in subject.get('picture_slots',[]):
                attention_regions[slot]=torch.maximum(attention_regions.get(slot,torch.zeros_like(masks[:,idx],dtype=torch.float32)),masks[:,idx].float())
        object_mask=torch.zeros((n,h,w),dtype=torch.bool)
        for noun in json.loads(preserve_objects):
            if noun not in ['phone','microphone','guitar','ukulele','cup','bottle','bicycle','torch','piano','keyboard']:continue
            object_cond=clip.encode_from_tokens_scheduled(clip.tokenize(noun))
            objects=SAM3_VideoTrack.execute(images=images,model=sam,conditioning=object_cond,detection_threshold=.5,max_objects=4,detect_interval=1)[0]
            if objects.get('packed_masks') is not None and objects['packed_masks'].shape[1]:
                om=unpack_masks(objects['packed_masks']).cpu().any(dim=1).float()
                if tuple(om.shape[-2:])!=(h,w):om=torch.nn.functional.interpolate(om[:,None],size=(h,w),mode='nearest')[:,0]
                object_mask|=om.bool()
        selected=torch.zeros((n,h,w),dtype=torch.bool)
        for idx,_,_ in chosen:selected|=masks[:,idx]
        if representation=='original':
            del sam,clip;mm.unload_all_models();mm.soft_empty_cache()
            return {**tracking,'result':(blur_guide(images,spec,selected),empty,attention_regions)}
        if representation=='mask':
            # Latent mask: keep the source pixels; only the region of the selected subjects is regenerated.
            # BFS Mask only keeps the per-frame segmentation on the full frame, grown by expand.
            del sam,clip;mm.unload_all_models();mm.soft_empty_cache()
            # Held props (guitar, microphone...) stay as in the source instead of being regenerated with the person.
            region=mask_region(shape_mask(selected,spec),spec)
            if bool(object_mask.any()):region=region*(~object_mask).float()
            return {**tracking,'result':(blur_guide(images,spec,selected),region,attention_regions)}
        del sam,clip;mm.unload_all_models();mm.soft_empty_cache()
        # The blur goes under the marks: with translucent 2D marks the face would otherwise show through the tint.
        seen=blur_guide(images,spec,selected) if representation=='2d' else images
        result=seen.clone()
        # 2D marks can be translucent (mark_opacity < 1, the BFS Colored Mark look): the guide person stays visible
        # under the tint, so the face and expression come through. 3D always paints the body solid.
        alpha=float(spec.get('mark_opacity',1.)) if representation=='2d' else 1.
        for idx,s,rgb in chosen:
            m=masks[:,idx];color=torch.tensor(rgb,dtype=result.dtype)/255
            result[m]=color if alpha>=1 else seen[m]*(1-alpha)+color*alpha
        if representation=='2d':
            result[object_mask]=images[object_mask]
            if spec.get('labels'):result=draw_labels(result,chosen,masks)
            return {**tracking,'result':(result,selected.float(),attention_regions)}
        from comfy_extras.nodes_sam3d_body import SAM3DBody_Loader,SAM3DBody_Predict,SAM3DBody_FaceExpression,SAM3DBody_Smooth
        from .mesh_renderer import render
        # DINOv3's sparse body regression requires FP32 on this checkpoint.
        from comfy.cli_args import args
        old_fp32=args.force_fp32
        try:
            args.force_fp32=True
            body=SAM3DBody_Loader.execute(body_model)[0]
        finally:args.force_fp32=old_fp32
        persons=[[] for _ in range(n)];faces=None;regions=None
        from comfy_extras.nodes_moge import LoadMoGeModel,MoGeInference,MoGeGeometryToFOV
        camera_model=LoadMoGeModel.execute('moge_2_vitl_normal_fp16.safetensors')[0]
        geometry=MoGeInference.execute(camera_model,images[:1],resolution_level=0,fov_x_degrees=0.,batch_size=1,force_projection=True,apply_mask=True,refine_steps=0)[0]
        fov=float(MoGeGeometryToFOV.execute(geometry,'vertical','degrees')[0]);del geometry,camera_model
        mm.unload_all_models();mm.soft_empty_cache()
        for idx,s,rgb in chosen:
            visible=np.where(masks[:,idx].flatten(1).sum(1).numpy()>64)[0]
            for span in np.split(visible,np.where(np.diff(visible)>1)[0]+1):
                if len(span)==0:continue
                # SAM 3D Body reads bit-packed masks; they come from the scene-by-scene tracks (width padded to a multiple of 8).
                m=masks[torch.as_tensor(span),idx:idx+1]
                if m.shape[-1]%8:m=torch.nn.functional.pad(m,(0,8-m.shape[-1]%8))
                subset={'packed_masks':pack_masks(m),'n_frames':len(span),'orig_size':(h,w)}
                pose=SAM3DBody_Predict.execute(body,images[span],track_data=subset,run_hand_refinement=True,fov=fov,batch_size=1)[0]
                pose=SAM3DBody_FaceExpression.execute(body,pose,images[span],strength=1.,mouth_strength=1.5,eye_strength=1.5,brow_strength=1.5,input_threshold=.02,blendshape_smooth_window=3)[0]
                pose=SAM3DBody_Smooth.execute(pose,strength=.35,method='gaussian',window=3,rotation_threshold_degrees=30.)[0]
                faces=pose['faces'];regions=np.asarray(pose['canonical_colors']['face_region_rgb'],np.float32)
                for j,k in enumerate(span):
                    for person in pose['frames'][j]:person['_rgb']=rgb;persons[int(k)].append(person)
        if faces is None:
            # None of the marked people is in this shot (a cut to someone else): like 2D, it goes through unmarked
            # instead of failing the job.
            note='None of the marked people is visible in this shot; it was left unmarked'
            return {'ui':ui_report({'henge_tracks':[json.dumps(follow.report(picked,masks,images,warnings+[note]))]}),'result':(images,selected.float(),attention_regions)}
        output=[]
        for k in range(n):
            background=(images[k].clamp(0,1).numpy()*255).astype(np.uint8)
            underlays=[(masks[k,idx].numpy(),rgb) for idx,_,rgb in chosen]
            output.append(render(background,persons[k],faces,underlays,regions)[...,::-1].copy())
        mm.unload_all_models();mm.soft_empty_cache()
        result=torch.from_numpy(np.stack(output)).float()/255
        result[object_mask]=images[object_mask]
        return {**tracking,'result':(result,selected.float(),attention_regions)}


class HengeH3Conditioning:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'clip':('CLIP',),'vae':('VAE',),'guide':('IMAGE',),'references':('HENGE_REFS',),'prompt':('STRING',{'multiline':True}),'width':('INT',{'default':512}),'height':('INT',{'default':288}),'length':('INT',{'default':107}),'clip_video_fps':('FLOAT',{'default':2,'min':.5,'max':24}),'reference_size':(['match','max'],),'guide_context':('BOOLEAN',{'default':True}),'audio_conditioning':('BOOLEAN',{'default':False}),'audio_video':('STRING',{'default':''})},'optional':{'audio_vae':('VAE',),'context_images':('IMAGE',),'context_count':('INT',{'default':0}),'conditioning_mode':(['guide','tara'],{'default':'guide'}),'reference_scale':('FLOAT',{'default':1.,'min':.25,'max':1.})}}
    RETURN_TYPES=('CONDITIONING','LATENT');FUNCTION='encode';CATEGORY='Henge'
    def encode(self,clip,vae,guide,references,prompt,width,height,length,clip_video_fps,reference_size,guide_context,audio_conditioning,audio_video,audio_vae=None,context_images=None,context_count=0,conditioning_mode="guide",reference_scale=1.):
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo,MiniMaxH3AddGuide
        audio=None
        if audio_conditioning:
            if audio_vae is None:raise ValueError('Audio conditioning needs the H3 audio VAE')
            import comfy.audio
            waveform,sample_rate=comfy.audio.load(str(input_path(audio_video)))
            audio={'waveform':waveform.unsqueeze(0),'sample_rate':sample_rate}
        pictures={f'ref_image_{i+1}':r for i,r in enumerate(references)}
        if conditioning_mode=='tara':
            if context_images is not None and context_count>=5:
                pictures[f'ref_image_{len(pictures)+1}']=context_images[-1:]
            video=guide
            if reference_scale!=1.:
                h,w=guide.shape[1:3];size=(max(32,int(h*reference_scale)//32*32),max(32,int(w*reference_scale)//32*32))
                video=torch.nn.functional.interpolate(guide.movedim(-1,1),size=size,mode='bilinear',align_corners=False).movedim(1,-1)
            print(f'[Henge H3] TARA native Video 1; reference scale {reference_scale:g}; Add Guide only for continuity',flush=True)
            cond,latent=MiniMaxH3ReferenceToVideo.execute(clip=clip,vae=vae,prompt=prompt,width=width,height=height,length=length,
                ref_image_size=reference_size,ref_images=pictures,ref_videos={'ref_video_1':video},
                audio_vae=audio_vae,ref_video_audios={'ref_video_audio_1':audio} if audio is not None else None)
            # A still of the previous shot only says how things look; its last generated frames locked at the head of this
            # shot (Add Guide history) also hold the framing, pose and light at the join. Needs the BFS TARA node that
            # accepts keyframes (BFSNodes 6df4276).
            if context_images is not None and context_count>=5:
                count=min(context_count,len(context_images),length);count-=max(0,(count-5)%17)
                cond=MiniMaxH3AddGuide.execute(positive=cond,latent=latent,frame_idx=0,vae=vae,image=context_images[-count:])[0]
                print(f'[Henge H3] TARA continuity: {count} previous frames locked at the start',flush=True)
            return cond,latent
        if conditioning_mode!='guide':raise ValueError('Unknown H3 conditioning mode')
        if guide_context:clip=clip_with_video_context(clip,{'guide':guide},length,context_fps=clip_video_fps)
        cond,latent=MiniMaxH3ReferenceToVideo.execute(clip=clip,vae=vae,prompt=prompt,width=width,height=height,length=length,ref_image_size=reference_size,ref_images=pictures)
        cond=MiniMaxH3AddGuide.execute(positive=cond,latent=latent,frame_idx=0,vae=vae,image=guide,audio_vae=audio_vae,audio=audio)[0]
        # Previous generated frames anchor the next segment on the same timeline, not a new reference identity.
        if context_images is not None and context_count>=5:
            count=min(context_count,len(context_images),length);count-=max(0,(count-5)%17)
            cond=MiniMaxH3AddGuide.execute(positive=cond,latent=latent,frame_idx=0,vae=vae,image=context_images[-count:])[0]
        return cond,latent


# Defaults of the BFS Shot Planner "Mask" card (feather/paste are paste-back settings, not used by a latent mask).
def label_spot(mask,step=4):
    """Where a label fits inside a mask: its most interior point (farthest from the edge, usually the chest) and the
    distance to the edge there, in pixels. None when the mask is empty."""
    m=mask[::step,::step]
    if not m.any():return None
    try:
        from scipy.ndimage import distance_transform_edt
        # The frame border is not the person's edge (a close-up is cut by it): pad with the mask itself there.
        dist=distance_transform_edt(np.pad(m,1,mode='edge'))[1:-1,1:-1]
    except ImportError:
        ys,xs=np.nonzero(m);return float(xs.mean()*step),float(ys.mean()*step),float(min(np.ptp(xs),np.ptp(ys))*step/4)
    # Prefer the chest: not the head (the label would cover the face, visible under translucent marks) and not the
    # bottom (a seated person's widest part is often the lap or the table edge).
    rows=np.arange(m.shape[0])[:,None];ys=np.nonzero(m)[0];top,bottom=ys.min(),ys.max()
    rel=(rows-top)/max(1,bottom-top)
    weight=1-.6*np.clip((.3-rel)/.3,0,1)-(0 if m[-1].any() else .35*np.clip((rel-.65)/.35,0,1))
    y,x=np.unravel_index(int(np.argmax(dist*weight)),dist.shape)
    return float(x*step),float(y*step),float(dist[y,x]*step)

def draw_labels(result,chosen,masks):
    """Experimental (mask_settings labels=true): write each subject's picture tag (<Picture 1>) inside its marked person
    in every frame, at the most interior point of the mask, sized to fit, white with a dark outline, smoothed over time
    so it does not jitter, so the binding is readable in the guide itself."""
    from PIL import ImageDraw,ImageFont
    n,h,w=result.shape[:3]
    fonts={}
    def font(size):
        if size not in fonts:
            try:fonts[size]=ImageFont.truetype('DejaVuSans-Bold.ttf',size)
            except OSError:fonts[size]=ImageFont.load_default(size=size)
        return fonts[size]
    frames=(result.clamp(0,1)*255).byte().cpu().numpy()
    places=[[None]*n for _ in chosen]
    for k,(idx,s,rgb) in enumerate(chosen):
        text='<Picture '+', '.join(str(x) for x in s.get('picture_slots') or [])+'>'
        probe=font(100);box=probe.getbbox(text);ratio=(box[2]-box[0])/100 # text width per pixel of font size
        last=None;gap=0
        for f in range(n):
            spot=label_spot(masks[f,idx].cpu().numpy())
            # Fits inside: the text box within the interior circle (width about 1.8x the distance to the edge), but
            # never below a readable size; a narrow mask lets it overflow a little. A sliver gets no label.
            size=None if spot is None else int(max(h/26,min(h/12,1.8*spot[2]/ratio)))
            if spot is None or spot[2]<h/60:
                gap+=1
                if gap>2:last=None
                continue
            x,y=spot[0],spot[1]
            # Smooth over time; restart after a cut or a jump (another track, the person came back elsewhere).
            if last is not None and abs(x-last[0])<.15*w and abs(y-last[1])<.15*h:
                x,y,size=.75*last[0]+.25*x,.75*last[1]+.25*y,int(round(.75*last[2]+.25*size))
            last=(x,y,size);gap=0;places[k][f]=(text,x,y,size)
    for f in range(n):
        todo=[p[f] for p in places if p[f]]
        if not todo:continue
        im=Image.fromarray(frames[f]);d=ImageDraw.Draw(im)
        for text,x,y,size in todo:
            ft=font(size);box=d.textbbox((0,0),text,font=ft,stroke_width=max(1,size//8));tw,th=box[2]-box[0],box[3]-box[1]
            px=int(np.clip(x-tw/2,2,w-tw-2));py=int(np.clip(y-th/2,2,h-th-2))
            d.text((px-box[0],py-box[1]),text,font=ft,fill=(255,255,255),stroke_width=max(1,size//8),stroke_fill=(0,0,0))
        frames[f]=np.asarray(im)
    return torch.from_numpy(frames).to(result.dtype)/255

DEFAULT_MASK={'threshold':.5,'shape':'silhouette','padding':.15,'expand':16,'fill_holes':True,'temporal_expand':2,'blockify':0,'invert':False,'strength':1.}

def shape_mask(masks,spec):
    """invert -> fill holes -> temporal expand -> blockify on [N,H,W] masks (BFS Shot Planner shape_mask)."""
    x=masks.float()
    if spec.get('invert'):x=1-x
    if spec.get('fill_holes'):
        try:
            from scipy.ndimage import binary_fill_holes
            x=torch.from_numpy(np.stack([binary_fill_holes(f>.5) for f in x.numpy()]).astype(np.float32))
        except ImportError:pass
    t=int(spec.get('temporal_expand') or 0)
    if t>0 and x.shape[0]>1:
        N,H,W=x.shape;x=torch.nn.functional.max_pool1d(x.permute(1,2,0).reshape(-1,1,N),2*t+1,1,t).reshape(H,W,N).permute(2,0,1)
    b=int(spec.get('blockify') or 0)
    if b>1:
        H,W=x.shape[1:];cov=torch.nn.functional.avg_pool2d(x[:,None],b,b,ceil_mode=True)[:,0]
        x=(cov>=.5).float().repeat_interleave(b,1).repeat_interleave(b,2)[:,:H,:W]
    return x>.5

def mask_region(mask,spec):
    """BFS Mask only: grow the per-frame SAM silhouette without a crop or bounding box.
    Legacy shape/padding settings remain accepted, but never turn the segmentation into a box.
    """
    expand=int(spec['expand'])
    x=mask.float()[:,None]
    if expand>0:
        k=2*expand+1
        x=torch.nn.functional.max_pool2d(x,(1,k),1,(0,expand))
        x=torch.nn.functional.max_pool2d(x,(k,1),1,(expand,0))
    return x[:,0]

# H3 video latent step k covers these source frames (first step 1, then 4): same grid as BFS latent_mask.
FRAME_PER_TOKEN=(1,4,4,4,4)

def latent_grid_mask(mask,latent_t,h,w,grow=1):
    """Pixel mask [F,H,W] (1 = regenerate) -> [1,1,T,h,w] on the H3 latent grid (adapted from BFSNodes latent_mask)."""
    m=torch.nn.functional.adaptive_max_pool2d(mask.float()[:,None],(h,w))[:,0]
    if grow>0:m=torch.nn.functional.max_pool2d(m[:,None],2*grow+1,1,grow)[:,0]
    out,f=[],0
    for k in range(latent_t):
        n=1 if k==0 else 4
        seg=m[min(f,m.shape[0]-1):min(f+n,m.shape[0])] if f<m.shape[0] else m[-1:]
        out.append(seg.amax(0));f+=n
    return (torch.stack(out)[None,None]>.5).float()

class HengeLatentMask:
    """Start sampling from the encoded source video and regenerate only the masked region.
    Per-row mixed-timestep masking for H3: credit to Neko (Nekodificador) and AbleJones, as in BFSNodes inpaint_latent."""
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'latent':('LATENT',),'vae':('VAE',),'images':('IMAGE',),'mask':('MASK',),'grow':('INT',{'default':1,'min':0,'max':8})},'optional':{'strength':('FLOAT',{'default':1.,'min':0.,'max':1.,'step':.05,'round':False,'precision':15})}}
    RETURN_TYPES=('LATENT',);FUNCTION='apply';CATEGORY='Henge'
    def apply(self,latent,vae,images,mask,grow,strength=1.):
        import comfy.nested_tensor
        samples=latent['samples']
        if not getattr(samples,'is_nested',False):raise ValueError('Latent mask expects a MiniMax H3 AV latent')
        video,audio=samples.tensors[0],samples.tensors[1];T,h,w=video.shape[2:]
        if float(mask.max())<=0:raise ValueError('Latent mask is empty: mark the subject to replace in the video')
        source=vae.encode(images[...,:3]).to(video)
        if source.shape!=video.shape:raise ValueError(f'Encoded source {tuple(source.shape)} does not match the latent {tuple(video.shape)}')
        # strength < 1: masked rows start at strength x the noise level and keep some of the source.
        vmask=latent_grid_mask(mask.cpu(),T,h,w,grow).to(video.device)*float(min(1.,max(0.,strength)))
        print(f'[Henge H3] latent mask: regenerating {100*float(vmask.mean()):.1f}% of the video latent',flush=True)
        out=dict(latent);out['samples']=comfy.nested_tensor.NestedTensor((source,audio))
        out['noise_mask']=comfy.nested_tensor.NestedTensor((vmask,torch.ones_like(audio)))
        return (out,)

class HengeMaskPreview:
    """Source frames with the regenerated region tinted and outlined, for reviewing a latent mask."""
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'mask':('MASK',)}}
    RETURN_TYPES=('IMAGE',);FUNCTION='overlay';CATEGORY='Henge'
    def overlay(self,images,mask):
        m=mask.float().clamp(0,1)
        if m.shape[1:]!=images.shape[1:3]:m=torch.nn.functional.interpolate(m[:,None],size=images.shape[1:3],mode='nearest')[:,0]
        edge=(torch.nn.functional.max_pool2d(m[:,None],5,1,2)[:,0]-m).clamp(0,1)
        tint=torch.tensor([.84,1.,.29],dtype=images.dtype)
        out=images[...,:3]*(1-.45*m[...,None])+tint*.45*m[...,None]
        return (out*(1-edge[...,None])+tint*edge[...,None],)

class HengeSaveVideo:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'filename':('STRING',),'trim_frames':('INT',{'default':107,'min':1}),'fps':('FLOAT',{'default':24})},
                                 'optional':{'skip_frames':('INT',{'default':0,'min':0})}}
    RETURN_TYPES=();FUNCTION='save';OUTPUT_NODE=True;CATEGORY='Henge'
    @classmethod
    def IS_CHANGED(cls,**kwargs):
        # Always write the file: a cached save node is left out of the run's outputs, and the bridge waits for it.
        return float('nan')
    def save(self,images,filename,trim_frames,fps,skip_frames=0):
        # skip_frames drops a shot's context overlap here, so this is the shot's only encode (CRF 17, visually lossless).
        root=Path(folder_paths.get_output_directory()).resolve();p=(root/filename).resolve()
        if not p.is_relative_to(root) or p.suffix!='.mp4':raise ValueError('Invalid output name')
        p.parent.mkdir(parents=True,exist_ok=True);frames=(images[skip_frames:trim_frames,...,:3].clamp(0,1)*255).round().byte().cpu().numpy();h,w=frames.shape[1:3]
        proc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-threads','2','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(p)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        _,err=proc.communicate(frames.tobytes())
        if proc.returncode:raise RuntimeError(err.decode(errors='replace')[-1000:])
        # 'videos' for /history readers; the same entry under 'gifs' (VHS's key) is what Comfy API v2 lists as a video output.
        entry={'filename':p.name,'subfolder':str(p.parent.relative_to(root)),'type':'output'}
        return {'ui':{'videos':[entry],'gifs':[entry]}}

NODE_CLASS_MAPPINGS={c.__name__:c for c in [HengeLoadShot,HengeLoadVideo,HengeGuide,HengeH3Conditioning,HengeLatentMask,HengeMaskPreview,HengeSaveVideo]}

class HengeTextResult:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'text':('STRING',{'forceInput':True})}}
    RETURN_TYPES=();FUNCTION='save';OUTPUT_NODE=True;CATEGORY='Henge'
    def save(self,text):return {'ui':ui_report({'text':[text]})}

NODE_CLASS_MAPPINGS['HengeTextResult']=HengeTextResult
from .find_people import HengeFindPeople
NODE_CLASS_MAPPINGS['HengeSubjectLook']=follow.HengeSubjectLook
NODE_CLASS_MAPPINGS['HengeFindPeople']=HengeFindPeople
from .causal import HengeCausalSampler
NODE_CLASS_MAPPINGS['HengeCausalSampler']=HengeCausalSampler
from .frame_refine import HengeFrameRefine
NODE_CLASS_MAPPINGS['HengeFrameRefine']=HengeFrameRefine

# Validate the exact API graph without adding a GPU execution to the Comfy queue.
from server import PromptServer
from aiohttp import web
@PromptServer.instance.routes.post('/henge/validate')
async def validate_henge_graph(request):
    import execution,uuid
    body=await request.json()
    result=await execution.validate_prompt(uuid.uuid4().hex,body['prompt'],None)
    return web.json_response({'valid':result[0],'error':result[1],'outputs':result[2],'node_errors':result[3]})
from .upscale import NODE_CLASS_MAPPINGS as UPSCALE_NODES
NODE_CLASS_MAPPINGS.update(UPSCALE_NODES)

from .regional_attention import HengeRegionalAttention
NODE_CLASS_MAPPINGS['HengeRegionalAttention']=HengeRegionalAttention

from .molmo import HengeMolmo
NODE_CLASS_MAPPINGS['HengeMolmo']=HengeMolmo

from .temporal_windows import HengeH3PureWindows
NODE_CLASS_MAPPINGS['HengeH3PureWindows']=HengeH3PureWindows
