"""API graphs based on the published Character Swap v1.1 native workflow.
Only branches selected in a validated plan are added: unused loaders never execute.
"""
import json,math
from pathlib import Path
MODELS={
 'motion':{'label':'Original · 10500','task':'motion','lora':'kagemane/motion_10500.safetensors','adapter':'kagemane/training_adapter_v2.safetensors','clip_context':True},
 'motion_tara4500':{'label':'TARA-trained · 4500','task':'motion','lora':'kagemane/motion_tara_4500.safetensors','adapter':'kagemane/training_adapter_v2.safetensors','clip_context':True},
 'character':{'task':'swap','label':'Character Swap v1.1 · published','lora':'kagemane/character_v1_1.safetensors','adapter':'kagemane/dmd_ref2va_8step.safetensors','clip_context':False},
 'mix50':{'label':'Character Swap v1.0 + v1.1 · 50/50 Dyn95','lora':'kagemane/character_mix50_dyn95.safetensors','adapter':'kagemane/dmd_ref2va_8step.safetensors','clip_context':False},
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

def h3_graph(video,refs,prompt,width,height,length,trim_frames,profile,seed,steps,representation,bindings,source_kind,segment_start,audio=False,context_video=None,context_count=0,clip_fps=2.,preserve_objects=None,conditioning_mode="guide",reference_scale=1.,context_prompt=True):
    model=MODELS[profile];g={
      '1':node('UNETLoader',unet_name='minimax_h3_ref2va_pruned_int8_convrot.safetensors',weight_dtype='default'),
      '2':node('LoraLoaderModelOnly',model=['1',0],lora_name=model['adapter'],strength_model=1.),
      '3':node('LoraLoaderModelOnly',model=['2',0],lora_name=model['lora'],strength_model=1.),
      '4':node('MiniMaxH3SigmaShift',model=['3',0],shift_video=12.,shift_audio=3.),
      '5':node('CLIPLoader',clip_name='qwen3vl_32b_minimax_h3_int8_convrot.safetensors',type='minimax',device='default'),
      '6':node('VAELoader',vae_name='minimax_h3_video_vae_fp16.safetensors'),
      '7':node('KagemaneLoadShot',video=video,pictures=json.dumps(refs),width=width,height=height,length=length),
      '8':node('KagemaneGuide',images=['7',0],representation=representation,bindings=json.dumps(bindings),source_kind=source_kind,segment_start=segment_start,sam_checkpoint='sam3.1_multiplex_fp16.safetensors',body_model='sam_3d_body_dinov3_bf16.safetensors',preserve_objects=json.dumps(preserve_objects or [])),
      '9':node('KagemaneH3Conditioning',clip=['5',0],vae=['6',0],guide=['8',0],references=['7',1],prompt=prompt,width=width,height=height,length=length,clip_video_fps=clip_fps,reference_size='match',guide_context=model['clip_context'],audio_conditioning=audio,audio_video=video),
      '10':node('CFGGuider',model=['4',0],positive=['9',0],negative=['9',0],cfg=1.),
      '11':node('RandomNoise',noise_seed=seed),
      '12':node('KSamplerSelect',sampler_name='euler'),
      '13':node('BasicScheduler',model=['4',0],scheduler='simple',steps=steps,denoise=1.),
      '14':node('SamplerCustomAdvanced',noise=['11',0],guider=['10',0],sampler=['12',0],sigmas=['13',0],latent_image=['9',1]),
      '15':node('LTXVSeparateAVLatent',av_latent=['14',0]),
      '16':node('VAEDecode',samples=['15',0],vae=['6',0]),
      '17':node('KagemaneSaveVideo',images=['16',0],filename=video.replace('.mp4','_result.mp4'),trim_frames=trim_frames,fps=24.),
      '18':node('KagemaneSaveVideo',images=['8',0],filename=video.replace('.mp4','_guide.mp4'),trim_frames=trim_frames,fps=24.),
    }
    g['9']['inputs'].update(conditioning_mode=conditioning_mode,reference_scale=reference_scale)
    if conditioning_mode=='tara':
        g['21']=node('BFSMiniMaxH3NativeTemporal',model=['4',0],motion_video_index=1,strength=2.,window_seconds=.2,falloff_seconds=.25,max_penalty=6.,attention_backend='flash partitions (no compile)')
        g['10']['inputs']['model']=['21',0];g['13']['inputs']['model']=['21',0]
    elif conditioning_mode!='guide':raise ValueError('Unknown conditioning mode')
    if audio:g['19']=node('VAELoader',vae_name='minimax_h3_audio_vae_fp32.safetensors');g['9']['inputs']['audio_vae']=['19',0]
    if context_video:
        g['20']=node('KagemaneLoadShot',video=context_video,pictures='[]',width=width,height=height,length=context_count)
        g['9']['inputs'].update(context_images=['20',0],context_count=context_count)
        if conditioning_mode=='tara' and context_prompt:
            g['9']['inputs']['prompt']+=f' <Picture {len(refs)+1}> is the preceding generated final frame, used only for scene/identity continuity. Follow the current Video 1 performance and timing; do not freeze its pose or override the assigned reference identities.'
    return g

def fibo_graph(image,refs,instruction,seed):
    g={'1':node('UNETLoader',unet_name='fibo2_edit_turbo_int8_convrot.safetensors',weight_dtype='default'),'2':node('CLIPLoader',clip_name='qwen3vl_4b_int8_convrot.safetensors',type='fibo2',device='default'),'3':node('VAELoader',vae_name='flux2-vae.safetensors'),'4':node('LoadImage',image=image),'5':node('TextEncodeFibo2',clip=['2',0],vae=['3',0],prompt=instruction,negative_prompt='',width=0,height=0,batch_size=1,**{'images.image_1':['4',0]}),'6':node('KSampler',model=['1',0],positive=['5',0],negative=['5',1],latent_image=['5',2],seed=seed,steps=4,cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.),'7':node('VAEDecode',samples=['6',0],vae=['3',0]),'8':node('SaveImage',images=['7',0],filename_prefix=image.rsplit('.',1)[0]+'_fibo')}
    for i,p in enumerate(refs,2):g[str(20+i)]=node('LoadImage',image=p);g['5']['inputs'][f'images.image_{i}']=[str(20+i),0]
    return g

def plan_graph(image,instructions,max_tokens=2500,clip_name='qwen3-vl-4b-heretic_int8_dynamic_convrot.safetensors'):
    g={'1':node('CLIPLoader',clip_name=clip_name,type='minimax',device='default'),
       '3':node('TextGenerate',clip=['1',0],prompt=instructions,max_length=max_tokens,sampling_mode='off',thinking=False,use_default_template=True,mtp='off'),
       '4':node('KagemaneTextResult',text=['3',0])}
    if image is not None:
        g['2']=node('LoadImage',image=image);g['3']['inputs']['image']=['2',0]
    return g


def split_on_cuts(total,per_shot,context,cuts):
    boundaries=sorted({0,total,*[int(c) for c in cuts if 0<int(c)<total]})
    output=[]
    for start,end in zip(boundaries,boundaries[1:]):
        for i,shot in enumerate(split_frames(end-start,per_shot,context)):
            output.append({**shot,'start':shot['start']+start,'reset_context':i==0})
    return output
