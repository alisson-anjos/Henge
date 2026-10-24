"""API graphs based on the published Character Swap v1.1 native workflow.
Only branches selected in a validated plan are added: unused loaders never execute.
"""
import json,math
from pathlib import Path
MODELS={
 'motion':{'label':'Original · 10500','task':'motion','lora':'henge/motion_10500.safetensors','adapter':'henge/training_adapter_v2.safetensors','clip_context':True},
 'motion_tara4500':{'label':'TARA-trained · 4500','task':'motion','lora':'henge/motion_tara_4500.safetensors','adapter':'henge/training_adapter_v2.safetensors','clip_context':True},
 'character':{'task':'swap','label':'Character Swap v1.1 · published','lora':'henge/character_v1_1.safetensors','adapter':'henge/dmd_ref2va_8step.safetensors','turbo':True,'clip_context':False},
 'mix50':{'label':'Character Swap v1.0 + v1.1 · 50/50 Dyn95','lora':'henge/character_mix50_dyn95.safetensors','adapter':'henge/dmd_ref2va_8step.safetensors','turbo':True,'clip_context':False},
 # Head Swap and Sharpness follow the published workflows: the whole source video is an
 # aligned Add Guide; Head Swap adds one face as a native reference, Sharpness none.
 'headswap':{'task':'headswap','label':'Head Swap v1.0','lora':'henge/head_swap_v1_0_r32.safetensors','adapter':'henge/dmd_ref2va_8step.safetensors','turbo':True,'clip_context':False,'scheduler':'beta'},
 'sharpness':{'task':'sharpness','label':'LMS Sharpness v1 · fro dyn95','lora':'henge/lms_v1_fro_dyn95.safetensors','adapter':'henge/dmd_ref2va_8step.safetensors','turbo':True,'clip_context':False,
              'files':[('latent_upscaler','Latent upscaler 3D · LMS v0.1','latent_upscale_models/h3_upscaler_lms_v0.1.safetensors')]},
}
# Swappable speed LoRAs for the modes whose adapter is a turbo LoRA (not Motion: its
# training adapter V2 is what the motion LoRAs were trained on).
TURBOS={
 'none':{'label':'None (for distilled bases such as FastH3 OmniRef)','lora':None,'steps':8},
 'dmd8':{'label':'DMD 8-step (drbaph)','lora':'henge/dmd_ref2va_8step.safetensors','steps':8},
 'dmad4':{'label':'DMAD 4-step (Kijai)','lora':'henge/turbo_dmad_4step.safetensors','steps':4},
 'lightx8':{'label':'lightx2v 8-step v1.1 (768p)','lora':'henge/turbo_lightx2v_8step_v1_1.safetensors','steps':8},
 'lightx4':{'label':'lightx2v 4-step v1.0 (768p)','lora':'henge/turbo_lightx2v_4step_v1_0.safetensors','steps':4},
}
# Base diffusion models. OmniRef (FastVideo) is already distilled to 8 steps: pair it with turbo 'none'.
# Latent upscaler for the Sharpness two-pass recipe (MinimaxH3LatentUpscaler3D, LBH-123-AI, MIT), fine-tuned on the LMS data.
LATENT_UPSCALER='h3_upscaler_lms_v0.1.safetensors'
BASES={
 'h3':{'label':'MiniMax H3 ref2va','unet':'minimax_h3_ref2va_pruned_int8_convrot.safetensors'},
 'omniref':{'label':'FastH3 OmniRef 8-step (FastVideo)','unet':'fasth3_omniref_8step_pruned_int8_convrot.safetensors'},
}
def node(kind,**inputs):return {'class_type':kind,'inputs':inputs}
def grid_frames(n):return max(5,math.ceil((n-5)/17)*17+5)
def split_frames(total,per_shot,context):
    # Context overlaps source time; only newly generated frames are appended to output.
    if per_shot<=context:raise ValueError('Context must be shorter than a segment')
    shots=[];start=0
    while start<total:
        keep=min(per_shot,total-start);overlap=0 if not shots else min(context,keep-1)
        shots.append({'start':start,'frames':keep,'overlap':overlap,'length':grid_frames(keep)})
        if start+keep>=total:break
        start+=keep-context
    return shots

def h3_graph(video,refs,prompt,width,height,length,trim_frames,profile,seed,steps,representation,bindings,source_kind,segment_start,audio=False,context_video=None,context_count=0,clip_fps=2.,preserve_objects=None,conditioning_mode="guide",reference_scale=1.,context_prompt=True,attention="comfy kitchen attention",turbo="dmd8",base="h3",cfg=1.,mask=None,lora_strength=1.,upscale=None):
    model=MODELS[profile];g={
      '1':node('UNETLoader',unet_name=BASES[base]['unet'],weight_dtype='default'),
      '2':node('LoraLoaderModelOnly',model=['1',0],lora_name=TURBOS[turbo]['lora'] if model.get('turbo') else model['adapter'],strength_model=1.),
      '3':node('LoraLoaderModelOnly',model=['2',0],lora_name=model['lora'],strength_model=float(lora_strength)),
      # Published H3 workflows run dense attention on Comfy Kitchen (INT8); TARA detects it.
      '22':node('ModelAttentionBackend',model=['3',0],attention=attention),
      '4':node('MiniMaxH3SigmaShift',model=['22',0],shift_video=12.,shift_audio=3.),
      '5':node('CLIPLoader',clip_name='qwen3vl_32b_minimax_h3_int8_convrot.safetensors',type='minimax',device='default'),
      '6':node('VAELoader',vae_name='minimax_h3_video_vae_fp16.safetensors'),
      '7':node('HengeLoadShot',video=video,pictures=json.dumps(refs),width=width,height=height,length=length),
      '8':node('HengeGuide',images=['7',0],representation=representation,bindings=json.dumps(bindings),source_kind=source_kind,segment_start=segment_start,sam_checkpoint='sam3.1_multiplex_fp16.safetensors',body_model='sam_3d_body_dinov3_bf16.safetensors',preserve_objects=json.dumps(preserve_objects or []),mask_settings=json.dumps(mask or {})),
      '9':node('HengeH3Conditioning',clip=['5',0],vae=['6',0],guide=['8',0],references=['7',1],prompt=prompt,width=width,height=height,length=length,clip_video_fps=clip_fps,reference_size='match',guide_context=model['clip_context'],audio_conditioning=audio,audio_video=video),
      '10':node('CFGGuider',model=['4',0],positive=['9',0],negative=['9',0],cfg=1.),
      '11':node('RandomNoise',noise_seed=seed),
      '12':node('KSamplerSelect',sampler_name='euler'),
      '13':node('BasicScheduler',model=['4',0],scheduler=model.get('scheduler','simple'),steps=steps,denoise=1.),
      '14':node('SamplerCustomAdvanced',noise=['11',0],guider=['10',0],sampler=['12',0],sigmas=['13',0],latent_image=['9',1]),
      '15':node('LTXVSeparateAVLatent',av_latent=['14',0]),
      '16':node('VAEDecode',samples=['15',0],vae=['6',0]),
      '17':node('HengeSaveVideo',images=['16',0],filename=video.replace('.mp4','_result.mp4'),trim_frames=trim_frames,fps=24.),
      '18':node('HengeSaveVideo',images=['8',0],filename=video.replace('.mp4','_guide.mp4'),trim_frames=trim_frames,fps=24.),
    }
    g['9']['inputs'].update(conditioning_mode=conditioning_mode,reference_scale=reference_scale)
    if representation=='mask':
        # Only the marked subject is regenerated; everything else starts from (and keeps) the source latent.
        g['23']=node('HengeLatentMask',latent=['9',1],vae=['6',0],images=['7',0],mask=['8',1],grow=1,strength=float((mask or {}).get('strength',1.)))
        g['14']['inputs']['latent_image']=['23',0]
    if cfg>1:
        # Undistilled sampling needs real guidance: negative = same conditioning with the text zeroed.
        g['24']=node('ConditioningZeroOut',conditioning=['9',0]);g['10']['inputs'].update(negative=['24',0],cfg=float(cfg))
    if model.get('turbo') and not TURBOS[turbo]['lora']:
        # No speed LoRA: the task LoRA loads straight onto the base.
        del g['2'];g['3']['inputs']['model']=['1',0]
    if conditioning_mode=='tara':
        g['21']=node('BFSMiniMaxH3NativeTemporal',model=['4',0],motion_video_index=1,strength=2.,window_seconds=.2,falloff_seconds=.25,max_penalty=6.,attention_backend='comfy kitchen (experimental)' if attention=='comfy kitchen attention' else 'flash partitions (no compile)')
        g['10']['inputs']['model']=['21',0];g['13']['inputs']['model']=['21',0]
    elif conditioning_mode!='guide':raise ValueError('Unknown conditioning mode')
    if audio:g['19']=node('VAELoader',vae_name='minimax_h3_audio_vae_fp32.safetensors');g['9']['inputs']['audio_vae']=['19',0]
    if context_video:
        g['20']=node('HengeLoadShot',video=context_video,pictures='[]',width=width,height=height,length=context_count)
        g['9']['inputs'].update(context_images=['20',0],context_count=context_count)
        if conditioning_mode=='tara' and context_prompt:
            g['9']['inputs']['prompt']+=f' <Picture {len(refs)+1}> is the preceding generated final frame, used only for scene/identity continuity. Follow the current Video 1 performance and timing; do not freeze its pose or override the assigned reference identities.'
    if upscale:
        # Sharpness two-pass: LMS at the low first-pass size, the 3D latent upscaler to the target size, then a
        # partial-denoise LMS pass guided by the source at the target size. `video` holds the target-size shot.
        W,H=upscale['width'],upscale['height']
        g['30']=node('MinimaxH3LatentUpscaler3D',latent=['15',0],model_name=LATENT_UPSCALER,mode='target dimensions',align=32,enable_chunking=True,device='cuda',precision='fp16',**{'mode.width':W,'mode.height':H})
        g['31']=node('HengeLoadShot',video=video,pictures=json.dumps(refs),width=W,height=H,length=length)
        g['32']=node('HengeH3Conditioning',**{**g['9']['inputs'],'guide':['31',0],'references':['31',1],'width':W,'height':H,
                                               'reference_scale':max(.25,min(1.,width/W))})
        if context_video:
            # Continuity frames come from the previous upscaled result: feed pass 2 at the target size.
            g['40']=node('HengeLoadShot',video=context_video,pictures='[]',width=W,height=H,length=context_count);g['32']['inputs']['context_images']=['40',0]
        g['33']=node('LTXVConcatAVLatent',video_latent=['30',0],audio_latent=['15',1])
        g['34']=node('BasicScheduler',model=g['13']['inputs']['model'],scheduler=g['13']['inputs']['scheduler'],steps=max(2,round(steps*float(upscale['denoise']))),denoise=float(upscale['denoise']))
        g['35']=node('RandomNoise',noise_seed=seed+1000)
        g['36']=node('CFGGuider',**{**g['10']['inputs'],'positive':['32',0],'negative':['39',0] if cfg>1 else ['32',0]})
        if cfg>1:g['39']=node('ConditioningZeroOut',conditioning=['32',0])
        g['37']=node('SamplerCustomAdvanced',noise=['35',0],guider=['36',0],sampler=['12',0],sigmas=['34',0],latent_image=['33',0])
        g['38']=node('LTXVSeparateAVLatent',av_latent=['37',0])
        g['16']['inputs']['samples']=['38',0]
    return g

def fibo_graph(image,refs,instruction,seed):
    g={'1':node('UNETLoader',unet_name='fibo2_edit_turbo_int8_convrot.safetensors',weight_dtype='default'),'2':node('CLIPLoader',clip_name='qwen3vl_4b_int8_convrot.safetensors',type='fibo2',device='default'),'3':node('VAELoader',vae_name='flux2-vae.safetensors'),'4':node('LoadImage',image=image),'5':node('TextEncodeFibo2',clip=['2',0],vae=['3',0],prompt=instruction,negative_prompt='',width=0,height=0,batch_size=1,**{'images.image_1':['4',0]}),'6':node('KSampler',model=['1',0],positive=['5',0],negative=['5',1],latent_image=['5',2],seed=seed,steps=4,cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.),'7':node('VAEDecode',samples=['6',0],vae=['3',0]),'8':node('SaveImage',images=['7',0],filename_prefix=image.rsplit('.',1)[0]+'_fibo')}
    for i,p in enumerate(refs,2):g[str(20+i)]=node('LoadImage',image=p);g['5']['inputs'][f'images.image_{i}']=[str(20+i),0]
    return g

def mask_preview_graph(video,width,height,length,trim_frames,bindings,source_kind,segment_start,preserve_objects,mask,filename):
    # Same HengeGuide pass the render uses, drawn over the source so the user can check the region first.
    return {'1':node('HengeLoadShot',video=video,pictures='[]',width=width,height=height,length=length),
            '2':node('HengeGuide',images=['1',0],representation='mask',bindings=json.dumps(bindings),source_kind=source_kind,segment_start=segment_start,
                     sam_checkpoint='sam3.1_multiplex_fp16.safetensors',body_model='sam_3d_body_dinov3_bf16.safetensors',preserve_objects=json.dumps(preserve_objects or []),mask_settings=json.dumps(mask or {})),
            '3':node('HengeMaskPreview',images=['1',0],mask=['2',1]),
            '4':node('HengeSaveVideo',images=['3',0],filename=filename,trim_frames=trim_frames,fps=24.)}

def mask_graph(image,prefix):
    # Native ComfyUI BiRefNet foreground mask (Character Swap v1.1 workflow prepares references this way).
    return {'1':node('LoadImage',image=image),'2':node('LoadBackgroundRemovalModel',bg_removal_name='birefnet.safetensors'),
            '3':node('RemoveBackground',bg_removal_model=['2',0],image=['1',0]),'4':node('MaskToImage',mask=['3',0]),
            '5':node('SaveImage',images=['4',0],filename_prefix=prefix)}

def plan_graph(image,instructions,max_tokens=2500,clip_name='qwen3.5_9b_w4a8_gptq.safetensors'):
    g={'1':node('CLIPLoader',clip_name=clip_name,type='minimax',device='default'),
       '3':node('TextGenerate',clip=['1',0],prompt=instructions,max_length=max_tokens,sampling_mode='off',thinking=False,use_default_template=True,mtp='off'),
       '4':node('HengeTextResult',text=['3',0])}
    if image is not None:
        g['2']=node('LoadImage',image=image);g['3']['inputs']['image']=['2',0]
    return g


def split_on_cuts(total,per_shot,context,cuts,min_gap=24):
    # Scene detection fires on flashes, fades and fast pans; a cut closer than min_gap frames to the
    # previous boundary (or the end) would only buy a near-empty shot rendered at full length.
    boundaries=[0]
    for c in sorted({int(c) for c in cuts}):
        if c-boundaries[-1]>=min_gap and total-c>=min_gap:boundaries.append(c)
    boundaries.append(total)
    output=[]
    for start,end in zip(boundaries,boundaries[1:]):
        for i,shot in enumerate(split_frames(end-start,per_shot,context)):
            output.append({**shot,'start':shot['start']+start,'reset_context':i==0})
    return output
