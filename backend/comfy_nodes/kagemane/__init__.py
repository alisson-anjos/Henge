"""Kagemane media, guide preparation and H3 conditioning nodes. No model downloads."""
import json,math,os,subprocess
from pathlib import Path
import numpy as np
import torch
from PIL import Image
import folder_paths,comfy.utils,comfy.sd,comfy.model_management as mm
from .clip_video import clip_with_video_context


def input_path(name):
    root=Path(folder_paths.get_input_directory()).resolve();p=(root/name).resolve()
    if not p.is_relative_to(root) or not p.is_file():raise ValueError('Unknown Kagemane input asset')
    return p


def read_frames(path,width,height,length):
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vf',f'fps=24,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2','-frames:v',str(length),'-f','rawvideo','-pix_fmt','rgb24','-threads','1','pipe:1'])
    x=np.frombuffer(raw,np.uint8).reshape(-1,height,width,3).copy()
    if len(x)==0:raise ValueError('Video decoded no frames')
    if len(x)<length:x=np.concatenate([x,np.repeat(x[-1:],length-len(x),axis=0)])
    return torch.from_numpy(x).float()/255


class KagemaneLoadShot:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'video':('STRING',),'pictures':('STRING',{'default':'[]'}),'width':('INT',{'default':512,'min':32,'step':32}),'height':('INT',{'default':288,'min':32,'step':32}),'length':('INT',{'default':107,'min':5,'max':362})}}
    RETURN_TYPES=('IMAGE','KAGEMANE_REFS');FUNCTION='load';CATEGORY='Kagemane'
    def load(self,video,pictures,width,height,length):
        refs=[]
        for p in json.loads(pictures):
            with Image.open(input_path(p)) as im:refs.append(torch.from_numpy(np.asarray(im.convert('RGB')).copy()).float()[None]/255)
        return read_frames(input_path(video),width,height,length),refs


class KagemaneGuide:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'representation':(['original','2d','3d'],),'bindings':('STRING',{'default':'[]'}),'source_kind':(['human','animal','other'],),'segment_start':('FLOAT',{'default':0}),'sam_checkpoint':('STRING',{'default':'sam3.1_multiplex_fp16.safetensors'}),'body_model':('STRING',{'default':'sam_3d_body_dinov3_bf16.safetensors'}),'preserve_objects':('STRING',{'default':'[]'})}}
    RETURN_TYPES=('IMAGE',);FUNCTION='prepare';CATEGORY='Kagemane'
    def prepare(self,images,representation,bindings,source_kind,segment_start,sam_checkpoint,body_model,preserve_objects="[]"):
        if representation=='original':return (images,)
        subjects=json.loads(bindings)
        if not subjects:raise ValueError('Color guides need a selected subject and its reference binding')
        if representation=='3d' and source_kind!='human':raise ValueError('SAM 3D Body supports human sources. Use a 2D color guide for animals.')
        from comfy_extras.nodes_sam3 import SAM3_VideoTrack
        from comfy.ldm.sam3.tracker import unpack_masks
        sam,clip,_=comfy.sd.load_checkpoint_guess_config(folder_paths.get_full_path_or_raise('checkpoints',sam_checkpoint),output_vae=False)
        cond=clip.encode_from_tokens_scheduled(clip.tokenize('person' if source_kind=='human' else 'animal'))
        # Track identity before choosing colors; coordinates are normalized source-image coordinates.
        tracks=SAM3_VideoTrack.execute(images=images,model=sam,conditioning=cond,detection_threshold=.4,max_objects=8,detect_interval=1)[0]
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
            if noun not in ['phone','microphone','guitar','ukulele','cup','bottle','bicycle','torch']:continue
            object_cond=clip.encode_from_tokens_scheduled(clip.tokenize(noun))
            objects=SAM3_VideoTrack.execute(images=images,model=sam,conditioning=object_cond,detection_threshold=.5,max_objects=4,detect_interval=1)[0]
            if objects.get('packed_masks') is not None and objects['packed_masks'].shape[1]:
                om=unpack_masks(objects['packed_masks']).cpu().any(dim=1).float()
                if tuple(om.shape[-2:])!=(h,w):om=torch.nn.functional.interpolate(om[:,None],size=(h,w),mode='nearest')[:,0]
                object_mask|=om.bool()
        result=images.clone();del sam,clip;mm.unload_all_models();mm.soft_empty_cache()
        for idx,s,rgb in chosen:result[masks[:,idx]]=torch.tensor(rgb,dtype=result.dtype)/255
        if representation=='2d':
            result[object_mask]=images[object_mask]
            return (result,)
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
        return (result,)


class KagemaneH3Conditioning:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'clip':('CLIP',),'vae':('VAE',),'guide':('IMAGE',),'references':('KAGEMANE_REFS',),'prompt':('STRING',{'multiline':True}),'width':('INT',{'default':512}),'height':('INT',{'default':288}),'length':('INT',{'default':107}),'clip_video_fps':('FLOAT',{'default':2,'min':.5,'max':24}),'reference_size':(['match','max'],),'guide_context':('BOOLEAN',{'default':True}),'audio_conditioning':('BOOLEAN',{'default':False}),'audio_video':('STRING',{'default':''})},'optional':{'audio_vae':('VAE',),'context_images':('IMAGE',),'context_count':('INT',{'default':0})}}
    RETURN_TYPES=('CONDITIONING','LATENT');FUNCTION='encode';CATEGORY='Kagemane'
    def encode(self,clip,vae,guide,references,prompt,width,height,length,clip_video_fps,reference_size,guide_context,audio_conditioning,audio_video,audio_vae=None,context_images=None,context_count=0):
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo,MiniMaxH3AddGuide
        if guide_context:clip=clip_with_video_context(clip,{'guide':guide},length,context_fps=clip_video_fps)
        cond,latent=MiniMaxH3ReferenceToVideo.execute(clip=clip,vae=vae,prompt=prompt,width=width,height=height,length=length,ref_image_size=reference_size,ref_images={f'ref_image_{i+1}':r for i,r in enumerate(references)})
        audio=None
        if audio_conditioning:
            if audio_vae is None:raise ValueError('Audio conditioning needs the H3 audio VAE')
            import comfy.audio
            waveform,sample_rate=comfy.audio.load(str(input_path(audio_video)))
            audio={'waveform':waveform.unsqueeze(0),'sample_rate':sample_rate}
        cond=MiniMaxH3AddGuide.execute(positive=cond,latent=latent,frame_idx=0,vae=vae,image=guide,audio_vae=audio_vae,audio=audio)[0]
        # Previous generated frames anchor the next segment on the same timeline, not a new reference identity.
        if context_images is not None and context_count>=5:
            count=min(context_count,len(context_images),length);count-=max(0,(count-5)%17)
            cond=MiniMaxH3AddGuide.execute(positive=cond,latent=latent,frame_idx=0,vae=vae,image=context_images[-count:])[0]
        return cond,latent


class KagemaneSaveVideo:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'filename':('STRING',),'trim_frames':('INT',{'default':107,'min':1}),'fps':('FLOAT',{'default':24})}}
    RETURN_TYPES=();FUNCTION='save';OUTPUT_NODE=True;CATEGORY='Kagemane'
    def save(self,images,filename,trim_frames,fps):
        root=Path(folder_paths.get_output_directory()).resolve();p=(root/filename).resolve()
        if not p.is_relative_to(root) or p.suffix!='.mp4':raise ValueError('Invalid output name')
        p.parent.mkdir(parents=True,exist_ok=True);frames=(images[:trim_frames,...,:3].clamp(0,1)*255).round().byte().cpu().numpy();h,w=frames.shape[1:3]
        proc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-threads','2','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(p)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        _,err=proc.communicate(frames.tobytes())
        if proc.returncode:raise RuntimeError(err.decode(errors='replace')[-1000:])
        return {'ui':{'videos':[{'filename':p.name,'subfolder':str(p.parent.relative_to(root)),'type':'output'}]}}

NODE_CLASS_MAPPINGS={c.__name__:c for c in [KagemaneLoadShot,KagemaneGuide,KagemaneH3Conditioning,KagemaneSaveVideo]}

class KagemaneTextResult:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'text':('STRING',{'forceInput':True})}}
    RETURN_TYPES=();FUNCTION='save';OUTPUT_NODE=True;CATEGORY='Kagemane'
    def save(self,text):return {'ui':{'text':[text]}}

NODE_CLASS_MAPPINGS['KagemaneTextResult']=KagemaneTextResult

# Validate the exact API graph without adding a GPU execution to the Comfy queue.
from server import PromptServer
from aiohttp import web
@PromptServer.instance.routes.post('/kagemane/validate')
async def validate_kagemane_graph(request):
    import execution,uuid
    body=await request.json()
    result=await execution.validate_prompt(uuid.uuid4().hex,body['prompt'],None)
    return web.json_response({'valid':result[0],'error':result[1],'outputs':result[2],'node_errors':result[3]})
