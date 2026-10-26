"""Henge media, guide preparation and H3 conditioning nodes. No model downloads."""
import json,math,os,subprocess
from pathlib import Path
import numpy as np
import torch
from PIL import Image
import folder_paths,comfy.utils,comfy.sd,comfy.model_management as mm
from .clip_video import clip_with_video_context


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


class HengeGuide:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'representation':(['original','2d','3d','mask'],),'bindings':('STRING',{'default':'[]'}),'source_kind':(['human','animal','other'],),'segment_start':('FLOAT',{'default':0}),'sam_checkpoint':('STRING',{'default':'sam3.1_multiplex_fp16.safetensors'}),'body_model':('STRING',{'default':'sam_3d_body_dinov3_bf16.safetensors'}),'preserve_objects':('STRING',{'default':'[]'})},'optional':{'mask_settings':('STRING',{'default':'{}'})}}
    RETURN_TYPES=('IMAGE','MASK');FUNCTION='prepare';CATEGORY='Henge'
    def prepare(self,images,representation,bindings,source_kind,segment_start,sam_checkpoint,body_model,preserve_objects="[]",mask_settings='{}'):
        spec={**DEFAULT_MASK,**json.loads(mask_settings or '{}')}
        empty=torch.zeros(images.shape[:3])
        if representation=='original':return (images,empty)
        subjects=json.loads(bindings)
        if not subjects:raise ValueError('Color guides need a selected subject and its reference binding')
        if representation=='3d' and source_kind!='human':raise ValueError('SAM 3D Body supports human sources. Use a 2D color guide for animals.')
        from comfy_extras.nodes_sam3 import SAM3_VideoTrack
        from comfy.ldm.sam3.tracker import unpack_masks
        loaded=comfy.sd.load_checkpoint_guess_config(folder_paths.get_full_path_or_raise('checkpoints',sam_checkpoint),output_vae=False)
        sam,clip=loaded[:2]
        cond=clip.encode_from_tokens_scheduled(clip.tokenize('person' if source_kind=='human' else 'animal'))
        # Track identity before choosing colors; coordinates are normalized source-image coordinates.
        tracks=SAM3_VideoTrack.execute(images=images,model=sam,conditioning=cond,detection_threshold=float(spec['threshold']) if representation=='mask' else .4,max_objects=8,detect_interval=1)[0]
        packed=tracks.get('packed_masks')
        if packed is None or packed.shape[1]==0:raise ValueError('SAM found no tracks. Adjust the subject selection.')
        masks=unpack_masks(packed).cpu().bool() # N,objects,h,w
        if tuple(masks.shape[-2:])!=tuple(images.shape[1:3]):masks=torch.nn.functional.interpolate(masks.float(),size=images.shape[1:3],mode='nearest').bool()
        n,h,w=images.shape[:3];chosen=[];used=set()
        for s in subjects:
            anchors=[a for a in s['anchors'] if segment_start<=a['time_seconds']<segment_start+n/24]
            if not anchors:raise ValueError(f"Mark {s['label']} within this segment ({segment_start:.2f}s). A color is never reassigned by screen position.")
            scores=torch.zeros(masks.shape[1],dtype=torch.int32)
            for a in anchors:
                k=min(n-1,round((a['time_seconds']-segment_start)*24))
                fw,fh=a['frame_width'],a['frame_height'];scale=min(w/fw,h/fh)
                x=min(w-1,max(0,round(a['x']*fw*scale+(w-fw*scale)/2)))
                y=min(h-1,max(0,round(a['y']*fh*scale+(h-fh*scale)/2)));scores+=masks[k,:,y,x].int()
            best=int(scores.argmax())
            if scores[best]==0 or best in used or int((scores==scores[best]).sum())>1:raise ValueError('Ambiguous subject-to-track mapping. Add another anchor on the same person.')
            used.add(best);rgb=tuple(int(s['hex'].lstrip('#')[i:i+2],16) for i in [0,2,4]);chosen.append((best,s,rgb))
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
        if representation=='mask':
            # Latent mask: keep the source pixels; only the region of the selected subjects is regenerated.
            # Like the BFS Shot Planner, the region is one box around the subjects' whole travel in this segment
            # (+15% margin), so a replacement with a different silhouette (hair, clothing, build) has room.
            del sam,clip;mm.unload_all_models();mm.soft_empty_cache()
            # Held props (guitar, microphone...) stay as in the source instead of being regenerated with the person.
            region=mask_region(shape_mask(selected,spec),spec)
            if bool(object_mask.any()):region=region*(~object_mask).float()
            return (images,region)
        result=images.clone();del sam,clip;mm.unload_all_models();mm.soft_empty_cache()
        # 2D marks can be translucent (mark_opacity < 1, the BFS Colored Mark look): the guide person stays visible
        # under the tint, so the face and expression come through. 3D always paints the body solid.
        alpha=float(spec.get('mark_opacity',1.)) if representation=='2d' else 1.
        for idx,s,rgb in chosen:
            m=masks[:,idx];color=torch.tensor(rgb,dtype=result.dtype)/255
            result[m]=color if alpha>=1 else images[m]*(1-alpha)+color*alpha
        if representation=='2d':
            result[object_mask]=images[object_mask]
            return (result,selected.float())
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
                subset={'packed_masks':packed[span,idx:idx+1],'n_frames':len(span),'orig_size':tracks['orig_size']}
                pose=SAM3DBody_Predict.execute(body,images[span],track_data=subset,run_hand_refinement=True,fov=fov,batch_size=1)[0]
                pose=SAM3DBody_FaceExpression.execute(body,pose,images[span],strength=1.,mouth_strength=1.5,eye_strength=1.5,brow_strength=1.5,input_threshold=.02,blendshape_smooth_window=3)[0]
                pose=SAM3DBody_Smooth.execute(pose,strength=.35,method='gaussian',window=3,rotation_threshold_degrees=30.)[0]
                faces=pose['faces'];regions=np.asarray(pose['canonical_colors']['face_region_rgb'],np.float32)
                for j,k in enumerate(span):
                    for person in pose['frames'][j]:person['_rgb']=rgb;persons[int(k)].append(person)
        if faces is None:raise ValueError('SAM 3D Body produced no visible geometry')
        output=[]
        for k in range(n):
            background=(images[k].clamp(0,1).numpy()*255).astype(np.uint8)
            underlays=[(masks[k,idx].numpy(),rgb) for idx,_,rgb in chosen]
            output.append(render(background,persons[k],faces,underlays,regions)[...,::-1].copy())
        mm.unload_all_models();mm.soft_empty_cache()
        result=torch.from_numpy(np.stack(output)).float()/255
        result[object_mask]=images[object_mask]
        return (result,selected.float())


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
            print(f'[Henge H3] TARA native Video 1; reference scale {reference_scale:g}; Add Guide OFF',flush=True)
            cond,latent=MiniMaxH3ReferenceToVideo.execute(clip=clip,vae=vae,prompt=prompt,width=width,height=height,length=length,
                ref_image_size=reference_size,ref_images=pictures,ref_videos={'ref_video_1':video},
                audio_vae=audio_vae,ref_video_audios={'ref_video_audio_1':audio} if audio is not None else None)
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
DEFAULT_MASK={'threshold':.5,'shape':'box','padding':.15,'expand':16,'fill_holes':True,'temporal_expand':2,'blockify':0,'invert':False,'strength':1.}

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
    """Region to regenerate: one padded box over the union of every frame (BFS Shot Planner default) or the
    silhouette grown by `expand` px."""
    padding,expand=float(spec['padding']),int(spec['expand'])
    if not bool(mask.any()):return mask.float()
    if spec['shape']=='silhouette':
        k=2*expand+1;return torch.nn.functional.max_pool2d(mask.float()[:,None],k,1,expand)[:,0]
    union=mask.any(0);ys,xs=torch.nonzero(union,as_tuple=True);H,W=union.shape
    x0,x1,y0,y1=int(xs.min()),int(xs.max())+1,int(ys.min()),int(ys.max())+1;px,py=int((x1-x0)*padding),int((y1-y0)*padding)
    region=torch.zeros_like(mask,dtype=torch.float32);region[:,max(0,y0-py):min(H,y1+py),max(0,x0-px):min(W,x1+px)]=1
    return region

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
    def INPUT_TYPES(cls):return {'required':{'latent':('LATENT',),'vae':('VAE',),'images':('IMAGE',),'mask':('MASK',),'grow':('INT',{'default':1,'min':0,'max':8})},'optional':{'strength':('FLOAT',{'default':1.,'min':0.,'max':1.,'step':.05})}}
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
    def save(self,images,filename,trim_frames,fps,skip_frames=0):
        # skip_frames drops a shot's context overlap here, so this is the shot's only encode (CRF 17, visually lossless).
        root=Path(folder_paths.get_output_directory()).resolve();p=(root/filename).resolve()
        if not p.is_relative_to(root) or p.suffix!='.mp4':raise ValueError('Invalid output name')
        p.parent.mkdir(parents=True,exist_ok=True);frames=(images[skip_frames:trim_frames,...,:3].clamp(0,1)*255).round().byte().cpu().numpy();h,w=frames.shape[1:3]
        proc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-threads','2','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(p)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        _,err=proc.communicate(frames.tobytes())
        if proc.returncode:raise RuntimeError(err.decode(errors='replace')[-1000:])
        return {'ui':{'videos':[{'filename':p.name,'subfolder':str(p.parent.relative_to(root)),'type':'output'}]}}

NODE_CLASS_MAPPINGS={c.__name__:c for c in [HengeLoadShot,HengeGuide,HengeH3Conditioning,HengeLatentMask,HengeMaskPreview,HengeSaveVideo]}

class HengeTextResult:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'text':('STRING',{'forceInput':True})}}
    RETURN_TYPES=();FUNCTION='save';OUTPUT_NODE=True;CATEGORY='Henge'
    def save(self,text):return {'ui':{'text':[text]}}

NODE_CLASS_MAPPINGS['HengeTextResult']=HengeTextResult
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
