"""API graphs based on the published Character Swap v1.1 native workflow.
Only branches selected in a validated plan are added: unused loaders never execute.
"""
import json,math
from pathlib import Path
MODELS={
 'motion':{'label':'Motion Transfer v1.0','task':'motion','lora':'henge/minimax_h3_motion_transfer_v1.0_ref2va.safetensors','adapter':'henge/minimax_h3_ref2va_training_adapter_v2.safetensors','clip_context':True},
 # Motion Transfer TARA v1.0: the LoRA trained for TARA; the studio switches to the TARA method with it.
 'motion_tara':{'label':'Motion Transfer TARA v1.0','task':'motion','lora':'henge/minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors','adapter':'henge/minimax_h3_ref2va_training_adapter_v2.safetensors','clip_context':True,'method':'tara'},
 # Motion Transfer Combined (for testing): Motion Transfer v1.0 x1.0 + TARA v1.0 x0.3, rank concat then per-module SVD keeping 95% /
 # 99% of the Frobenius energy (tools/henge_session_20261025/merge_fro.py); for Guide Latents and TARA.
 'motion_mix_dyn95':{'label':'Motion Transfer Combined · dyn95 (test)','task':'motion','lora':'henge/minimax_h3_motion_transfer_combined_v1.0_dyn95.safetensors','adapter':'henge/minimax_h3_ref2va_training_adapter_v2.safetensors','clip_context':True},
 'motion_mix_dyn99':{'label':'Motion Transfer Combined · dyn99 (test)','task':'motion','lora':'henge/minimax_h3_motion_transfer_combined_v1.0_dyn99.safetensors','adapter':'henge/minimax_h3_ref2va_training_adapter_v2.safetensors','clip_context':True},
 # First-frame propagate: Alissonerdx VFX Edit FFP (r128) merged with SolarRenderer control at 0.5 (Frobenius dyn99 / dyn95).
 # The whole source is the guide; an optional edited first frame enters as a native image reference (prompt: vfx_edit:).
 'motion_ffp':{'label':'Motion Transfer FFP · dyn99','task':'motion','lora':'henge/minimax_h3_vfx_edit_ffp_v1.0_solar05_dyn99.safetensors','adapter':None,'clip_context':False,'ffp':True},
 # The same merge kept at 95% of the energy: a lighter LoRA, a little less of SolarRenderer's control.
 'motion_ffp_dyn95':{'label':'Motion Transfer FFP · dyn95','task':'motion','lora':'henge/minimax_h3_vfx_edit_ffp_v1.0_solar05_dyn95.safetensors','adapter':None,'clip_context':False,'ffp':True},
 # SolarRenderer control alone (no Henge LoRA, `solar` profile), shrunk to a dynamic rank by Frobenius energy: the
 # baseline to compare our Motion Transfer against.
 'motion_solar_dyn95':{'label':'SolarRenderer control · dyn95 (comparison)','task':'motion','lora':'henge/solarrenderer_control_fro_dyn95.safetensors','adapter':None,'clip_context':True},
 'motion_solar_dyn99':{'label':'SolarRenderer control · dyn99 (comparison)','task':'motion','lora':'henge/solarrenderer_control_fro_dyn99.safetensors','adapter':None,'clip_context':True},
 'character':{'task':'swap','label':'Character Swap v1.1','lora':'henge/minimax_h3_character_swap_v1.1_ref2va_fro.safetensors','adapter':'henge/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors','turbo':True,'clip_context':False},
 # Head Swap and Sharpness follow the published workflows: the whole source video is an
 # aligned Add Guide; Head Swap adds one face as a native reference, Sharpness none.
 'headswap':{'task':'headswap','label':'Head Swap v1.0','lora':'henge/minimax_h3_head_swap_v1.0_r32.safetensors','adapter':'henge/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors','turbo':True,'clip_context':False,'scheduler':'beta'},
 'sharpness':{'task':'sharpness','label':'Little More Sharpness v1.0','lora':'henge/minimax_h3_lms_v1.0_r64.safetensors','adapter':'henge/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors','turbo':True,'clip_context':False},
}
# Swappable speed LoRAs. Swap modes load it in place of an adapter; Motion stacks it on training
# adapter V2 (what the motion LoRAs were trained on).
TURBOS={
 'none':{'label':'None (for distilled bases such as FastH3 OmniRef)','lora':None,'steps':8},
 'dmd8':{'label':'DMD 8-step (drbaph)','lora':'henge/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors','steps':8},
 'dmad4':{'label':'DMAD 4-step (Kijai)','lora':'henge/minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors','steps':4},
 'pdmd4':{'label':'pDMD 4-step (Kijai, experimental)','lora':'henge/minimax_h3_pdmd_4step_lora_avg_rank_57_bf16.safetensors','steps':4},
 'pdmd2':{'label':'pDMD 2-step (Kijai, experimental)','lora':'henge/minimax_h3_pdmd_2step_lora_avg_rank_38_bf16.safetensors','steps':2},
 'lightx8':{'label':'lightx2v 8-step v1.1 (768p)','lora':'henge/minimax_h3_ref2v_turbo_8step_v1.1_768p_comfyui_bf16.safetensors','steps':8},
 'lightx4':{'label':'lightx2v 4-step v1.0 (768p)','lora':'henge/minimax_h3_ref2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors','steps':4},
 'solar4':{'label':'SolarRenderer 4-step (ComfyUI keys)','lora':'henge/solarrenderer_4step_comfy.safetensors','steps':4},
}
SAMPLING=json.loads((Path(__file__).resolve().parents[1]/'lib/h3-sampling.json').read_text())
SAMPLERS=tuple(SAMPLING['samplers'])
PIKA=SAMPLING['pika']
# Default turbo for new jobs (Pika's published 6-step preset). Graphs of older jobs that never stored a turbo keep
# building with DMD 8-step, so a Retry reproduces them.
DEFAULT_TURBO=PIKA['turbo']
TURBOS[PIKA['turbo']]={'label':'Pika H3 Flex · 6-step (experimental stack)','lora':'henge/pika_h3_flex_ref2va_v1_avg_rank_55_bf16.safetensors','steps':PIKA['steps']}

# LoRA files keep their published filenames under loras/henge/. Installs from before 2026-10-27 used short names;
# localize_loras() falls back to the old name when only that one is installed, so nothing has to be downloaded again.
LEGACY_LORAS=json.loads((Path(__file__).with_name('legacy_loras.json')).read_text())
# What ComfyUI lists per loader input, refreshed by the bridge: models already in the user's ComfyUI are reused even
# under an old short name or in another subfolder (e.g. vae/minimax/…), so nothing is downloaded twice.
INSTALLED={}
LOADERS={'LoraLoaderModelOnly':'lora_name','VAELoader':'vae_name','UNETLoader':'unet_name','CLIPLoader':'clip_name','LatentUpscaleModelLoader':'model_name'}
def sampling_model(g,model):
    """Point the first-pass guider and its scheduler at a patched MODEL. Pika's 6-step preset replaces the scheduler
    with ManualSigmas, which takes no model: setting one there fails the whole graph."""
    g['10']['inputs']['model']=model
    if g.get('13',{}).get('class_type')!='ManualSigmas':g['13']['inputs']['model']=model

def resolve_model(node,name,installed=None):
    names=INSTALLED.get(node,set()) if installed is None else installed
    if not name or not names or name in names:return name
    old=LEGACY_LORAS.get(name)
    if old in names:return old
    bases={name.rsplit('/',1)[-1]}|({old.rsplit('/',1)[-1]} if old else set())
    hits=sorted(n for n in names if n.replace('\\','/').rsplit('/',1)[-1] in bases)
    return hits[0] if hits else name
def lora_installed(name,installed=None):
    names=INSTALLED.get('LoraLoaderModelOnly',set()) if installed is None else installed
    return not name or resolve_model('LoraLoaderModelOnly',name,names) in names
def localize_loras(graph):
    for n in graph.values():
        key=LOADERS.get(n.get('class_type'))
        if key and isinstance(n.get('inputs',{}).get(key),str):n['inputs'][key]=resolve_model(n['class_type'],n['inputs'][key])
    return graph
# Base diffusion models. OmniRef (FastVideo) is already distilled to 8 steps: pair it with turbo 'none'.
BASES={
 'h3':{'label':'MiniMax H3 ref2va','unet':'minimax_h3_ref2va_pruned_int8_convrot.safetensors'},
 'omniref':{'label':'FastH3 OmniRef 8-step (FastVideo)','unet':'fasth3_omniref_8step_pruned_int8_convrot.safetensors'},
}
# Sharpness above 720p renders at half the output size, then doubles it with one of two upscalers (henge/upscale.py):
# h3: learned H3 latent upscaler, then a short partial-denoise refine by the same H3 model (tiled above ~2 MP);
# nvidia: NVIDIA RTX Video Super Resolution on the decoded frames (no diffusion, no invented detail).
UPSCALE_METHODS=('h3','regenerate','nvidia','none')
REGENERATE={
 'base':BASES['h3']['unet'],
 'refiner':'henge/minimax_h3_open_regenerate_2k_refiner_rank_16_bf16.safetensors',
 'turbo':TURBOS['dmad4']['lora'],
 'lms':MODELS['sharpness']['lora'],
 'upscaler':'minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors',
}
# Latent upscaler of the refiner stage (native ComfyUI loader): the LBH-123-AI base, or ours fine-tuned on the LMS data
# (same architecture and latent contract).
REGENERATE_UPSCALERS={'base':REGENERATE['upscaler'],'lms':'h3_upscaler_lms_v0.1.safetensors'}
REGENERATE_SIGMAS={2:'0.7, 0.494118, 0',3:'0.909375, 0.857143, 0.666667, 0'}
# Learned H3 latent upscalers, preferred first (LBH-123-AI 3D upscaler, MIT; ours is fine-tuned on the LMS data).
H3_UPSCALERS=('h3_upscaler_lms_v0.1.safetensors','minimax_h3_latent_upscaler_3d_bf16.safetensors')

def node(kind,/,**inputs):return {'class_type':kind,'inputs':inputs}  # positional-only: a node input may be named 'kind'
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

def h3_graph(video,refs,prompt,width,height,length,trim_frames,profile,seed,steps,representation,bindings,source_kind,segment_start,audio=False,context_video=None,context_count=0,clip_fps=2.,preserve_objects=None,conditioning_mode="guide",reference_scale=1.,context_prompt=True,attention="comfy kitchen attention",turbo="dmd8",base="h3",cfg=1.,mask=None,lora_strength=1.,causal=None,structure_cfg=1.,structure_sigma_min=0.,upscale=None,skip_frames=0,guide_context=None,gen_audio=False,regional_attention=None,temporal_windows=None,sampler_name="auto"):
    if sampler_name not in SAMPLERS:raise ValueError('Unknown H3 sampler')
    pika=turbo==PIKA['turbo']
    if pika and base!='h3':raise ValueError('Pika H3 Flex Ref2VA requires the H3 Ref2VA base')
    selected_sampler=(PIKA['sampler'] if pika else 'euler') if sampler_name=='auto' else sampler_name
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
      '9':node('HengeH3Conditioning',clip=['5',0],vae=['6',0],guide=['8',0],references=['7',1],prompt=prompt,width=width,height=height,length=length,clip_video_fps=clip_fps,reference_size='match',guide_context=model['clip_context'] if guide_context is None else bool(guide_context),audio_conditioning=audio,audio_video=video),
      '10':node('CFGGuider',model=['4',0],positive=['9',0],negative=['9',0],cfg=1.),
      '11':node('RandomNoise',noise_seed=seed),
      '12':node('KSamplerSelect',sampler_name=selected_sampler),
      '13':node('BasicScheduler',model=['4',0],scheduler=model.get('scheduler','simple'),steps=steps,denoise=1.),
      '14':node('SamplerCustomAdvanced',noise=['11',0],guider=['10',0],sampler=['12',0],sigmas=['13',0],latent_image=['9',1]),
      '15':node('LTXVSeparateAVLatent',av_latent=['14',0]),
      '16':node('VAEDecode',samples=['15',0],vae=['6',0]),
      '17':node('HengeSaveVideo',images=['16',0],filename=video.replace('.mp4','_result.mp4'),trim_frames=trim_frames,fps=24.),
      '18':node('HengeSaveVideo',images=['8',0],filename=video.replace('.mp4','_guide.mp4'),trim_frames=trim_frames,fps=24.),
    }
    g['9']['inputs'].update(conditioning_mode=conditioning_mode,reference_scale=reference_scale)
    # The worker drops the context overlap itself, so the bridge only copies the shot (no second encode).
    if skip_frames:g['17']['inputs']['skip_frames']=g['18']['inputs']['skip_frames']=skip_frames
    if representation=='mask':
        # The saved guide shows the regenerated region over the source, so it can be reviewed and downloaded.
        g['26']=node('HengeMaskPreview',images=['7',0],mask=['8',1]);g['18']['inputs']['images']=['26',0]
        # Only the marked subject is regenerated; everything else starts from (and keeps) the source latent.
        g['23']=node('HengeLatentMask',latent=['9',1],vae=['6',0],images=['7',0],mask=['8',1],grow=1,strength=float((mask or {}).get('strength',1.)))
        g['14']['inputs']['latent_image']=['23',0]
    if cfg>1:
        # Undistilled sampling needs real guidance: negative = same conditioning with the text zeroed.
        g['24']=node('ConditioningZeroOut',conditioning=['9',0]);g['10']['inputs'].update(negative=['24',0],cfg=float(cfg))
    if pika and steps==PIKA['steps']:
        g['13']=node('ManualSigmas',sigmas=', '.join(str(sigma) for sigma in PIKA['sigmas']))
    if model.get('turbo') and not TURBOS[turbo]['lora']:
        # No speed LoRA: the task LoRA loads straight onto the base.
        del g['2'];g['3']['inputs']['model']=['1',0]
    if not model.get('turbo') and not model['adapter']:
        # The adapter is merged into the task LoRA: the speed LoRA (if any) loads straight onto the base.
        if TURBOS[turbo]['lora']:g['2']['inputs']['lora_name']=TURBOS[turbo]['lora']
        else:del g['2'];g['3']['inputs']['model']=['1',0]
    elif not model.get('turbo') and TURBOS[turbo]['lora']:
        # Motion keeps training adapter V2 (what its LoRAs were trained on) and stacks the speed LoRA on it.
        g['25']=node('LoraLoaderModelOnly',model=['2',0],lora_name=TURBOS[turbo]['lora'],strength_model=1.);g['3']['inputs']['model']=['25',0]
    if conditioning_mode=='tara':
        g['21']=node('BFSMiniMaxH3NativeTemporal',model=['4',0],motion_video_index=1,strength=2.,window_seconds=.2,falloff_seconds=.25,max_penalty=6.,attention_backend='comfy kitchen (experimental)' if attention=='comfy kitchen attention' else 'flash partitions (no compile)',
                   # SolarRenderer-style structure CFG inside the TARA node: one extra pass without <Video 1> per step
                   structure_guidance=float(structure_cfg),structure_sigma_min=float(structure_sigma_min))
        sampling_model(g,['21',0])
    elif conditioning_mode!='guide':raise ValueError('Unknown conditioning mode')
    if audio:g['19']=node('VAELoader',vae_name='minimax_h3_audio_vae_fp32.safetensors');g['9']['inputs']['audio_vae']=['19',0]
    if context_video:
        g['20']=node('HengeLoadShot',video=context_video,pictures='[]',width=width,height=height,length=context_count)
        g['9']['inputs'].update(context_images=['20',0],context_count=context_count)
        if conditioning_mode=='tara' and context_prompt:
            g['9']['inputs']['prompt']+=f' <Picture {len(refs)+1}> is the preceding generated final frame, used only for scene/identity continuity. Follow the current Video 1 performance and timing; do not freeze its pose or override the assigned reference identities.'
    if upscale:
        # Output at twice the rendered size (`width`/`height` are the render size); see UPSCALE_METHODS.
        W,H=int(upscale.get('width',width*2)),int(upscale.get('height',height*2))
        if upscale['method']=='h3':
            # Learned H3 latent upscale to the output size, then a short partial-denoise pass guided by the source at
            # that size (`video` holds the output-size shot). Above ~2 MP the refine model samples overlapping tiles.
            g['30']=node('HengeH3LatentUpscale',latent=['15',0],model_name=upscale['model'],width=W,height=H,precision='fp16')
            g['31']=node('HengeLoadShot',video=video,pictures=json.dumps(refs),width=W,height=H,length=length)
            g['32']=node('HengeH3Conditioning',**{**g['9']['inputs'],'guide':['31',0],'references':['31',1],'width':W,'height':H,'reference_scale':max(.25,min(1.,width/W))})
            if context_video:
                # Continuity frames come from the previous upscaled result: feed the refine at the output size.
                g['40']=node('HengeLoadShot',video=context_video,pictures='[]',width=W,height=H,length=context_count);g['32']['inputs']['context_images']=['40',0]
            refine_model=g['10']['inputs']['model']
            if W*H>2_100_000:g['41']=node('HengeH3TiledDiffusion',model=refine_model,tile_width=1024,tile_height=1024,tile_overlap=256,method='gaussian');refine_model=['41',0]
            g['33']=node('LTXVConcatAVLatent',video_latent=['30',0],audio_latent=['15',1])
            g['34']=node('BasicScheduler',model=refine_model,scheduler=model.get('scheduler','simple'),steps=int(upscale.get('steps',1)),denoise=float(upscale.get('denoise',.15)))
            g['35']=node('RandomNoise',noise_seed=seed+1000)
            g['36']=node('CFGGuider',model=refine_model,positive=['32',0],negative=['32',0],cfg=1.)
            g['37']=node('SamplerCustomAdvanced',noise=['35',0],guider=['36',0],sampler=['12',0],sigmas=['34',0],latent_image=['33',0])
            g['38']=node('LTXVSeparateAVLatent',av_latent=['37',0])
            # 2K/4K frames: decode in tiles so the VAE fits beside the model.
            g['16']=node('VAEDecodeTiled',samples=['38',0],vae=['6',0],tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8)
        elif upscale['method']=='regenerate':
            # Separate Ref2VA model stack; reuse the installed H3 base without carrying first-pass patches.
            # Kijai's rank-16 contains only the refiner, not LMS or the turbo.
            count=int(upscale.get('steps',2))
            if count not in REGENERATE_SIGMAS:raise ValueError('Regenerate needs 2 or 3 refine steps')
            g['70']=node('UNETLoader',unet_name=REGENERATE['base'],weight_dtype='default')
            g['71']=node('ModelAttentionBackend',model=['70',0],attention=attention)
            g['72']=node('LoraLoaderModelOnly',model=['71',0],lora_name=REGENERATE['turbo'],strength_model=1.)
            g['73']=node('LoraLoaderModelOnly',model=['72',0],lora_name=REGENERATE['refiner'],strength_model=1.)
            # LMS on top of the refiner is optional, at the chosen strength (0 = refiner and turbo only).
            lms=float(upscale.get('lms_strength',1.))
            if lms>0:g['74']=node('LoraLoaderModelOnly',model=['73',0],lora_name=REGENERATE['lms'],strength_model=lms)
            g['30']=node('LatentUpscaleModelLoader',model_name=upscale.get('model',REGENERATE['upscaler']))
            # Native node resizes video while preserving the AV latent's audio stream.
            g['31']=node('MiniMaxH3LatentUpscaleWithModel',model=['30',0],samples=['14',0],width=W,height=H)
            g['32']=node('CLIPTextEncode',clip=['5',0],text=upscale.get('prompt') or prompt)
            g['33']=node('ManualSigmas',sigmas=REGENERATE_SIGMAS[count])
            # LMS follows the source through Add Guide, at the final canvas size.
            g['75']=node('HengeLoadShot',video=video,pictures='[]',width=W,height=H,length=length)
            g['76']=node('MiniMaxH3AddGuide',positive=['32',0],latent=['31',0],vae=['6',0],image=['75',0],frame_idx=0)
            g['34']=node('BasicGuider',model=['74' if lms>0 else '73',0],conditioning=['76',0])
            g['35']=node('KSamplerSelect',sampler_name='er_sde')
            g['36']=node('RandomNoise',noise_seed=seed)
            g['37']=node('SamplerCustomAdvanced',noise=['36',0],guider=['34',0],sampler=['35',0],sigmas=['33',0],latent_image=['31',0])
            g['38']=node('LTXVSeparateAVLatent',av_latent=['37',0])
            g['16']=node('VAEDecodeTiled',samples=['38',0],vae=['6',0],tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8)
        elif upscale['method']=='nvidia':
            g['30']=node('HengeRTXUpscale',images=['16',0],width=W,height=H,quality='ULTRA')
            g['17']['inputs']['images']=['30',0]
        else:raise ValueError('Unknown upscale method')
    if regional_attention and regional_attention.get('enabled'):
        if representation not in ('2d','3d') or conditioning_mode!='guide' or causal or upscale:
            raise ValueError('Regional attention experiment needs a 2D/3D Guide Latents shot without causal sampling or upscale')
        g['60']=node('HengeRegionalAttention',model=g['10']['inputs']['model'],regions=['8',2],
                     strength=float(regional_attention.get('strength',.5)),reference_budget=float(regional_attention.get('reference_budget',.35)),
                     layers=regional_attention.get('layers','10,25,40'))
        sampling_model(g,['60',0])
    if gen_audio:
        # H3 always samples a joint video+audio latent; keep its soundtrack (32 kHz stereo) instead of dropping it.
        if '19' not in g:g['19']=node('VAELoader',vae_name='minimax_h3_audio_vae_fp32.safetensors')
        g['50']=node('VAEDecodeAudio',samples=['37',0] if '37' in g else ['14',0],vae=['19',0])
        g['51']=node('SaveAudio',audio=['50',0],filename_prefix=video.replace('.mp4','_audio'))
    if causal:
        # One render for the whole interval, chunk by chunk against a key/value cache (no shot seams).
        if conditioning_mode!='guide' or representation=='mask' or upscale:raise ValueError('Causal rendering needs Guide Latents, no latent mask and no upscale')
        g['14']=node('HengeCausalSampler',model=g['10']['inputs']['model'],positive=['9',0],latent=['9',1],seed=seed,steps=steps,
                     chunk=int(causal.get('chunk',5)),window=int(causal.get('window',6)),sampler='euler',cache='auto')
        for k in ('10','11','12','13','24'):g.pop(k,None)
    if temporal_windows and temporal_windows.get('enabled'):
        if temporal_windows.get('scope')=='refiner_full':raise ValueError('Full-video refinement requires assembling the normal segments first')
        if causal or (regional_attention and regional_attention.get('enabled')):
            raise ValueError('Pure temporal windows cannot be combined with Causal or regional attention')
        window_args={'window_frames':int(temporal_windows.get('window_frames',107)),'overlap_frames':int(temporal_windows.get('overlap_frames',22)),'accumulator_device':'cpu'}
        g['80']=node('HengeH3PureWindows',model=g['10']['inputs']['model'],**window_args)
        sampling_model(g,['80',0])
        if upscale and upscale['method']=='regenerate':
            g['81']=node('HengeH3PureWindows',model=g['34']['inputs']['model'],**window_args)
            g['34']['inputs']['model']=['81',0]
        elif upscale and upscale['method']=='h3':
            g['81']=node('HengeH3PureWindows',model=g['36']['inputs']['model'],**window_args)
            g['36']['inputs']['model']=g['34']['inputs']['model']=['81',0]
    return g

def full_refiner_graph(video,guide,prompt,width,height,output_width,output_height,length,trim_frames,seed,steps=2,attention="comfy kitchen attention",temporal_windows=None,lms_strength=1.,upscaler_model=None):
    """Refine the assembled first pass once, using a separate Ref2VA stack and global sampler.

    Persisted first-pass frames are re-encoded (not concatenated latent caches). The original
    source interval remains the Add Guide control; no first-pass model or sampler is executed here.
    """
    windows={**(temporal_windows or {}),'enabled':True}
    g=h3_graph(guide,[],prompt,width,height,length,trim_frames,'sharpness',seed,4,'original',[],'human',0,
               attention=attention,upscale={'method':'regenerate','width':output_width,'height':output_height,'steps':steps,'prompt':prompt,'lms_strength':lms_strength,**({'model':upscaler_model} if upscaler_model else {})})
    g['90']=node('HengeLoadShot',video=video,pictures='[]',width=width,height=height,length=length)
    g['91']=node('VAEEncodeTiled',pixels=['90',0],vae=['6',0],tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8)
    g['92']=node('EmptyMiniMaxH3LatentAV',width=width,height=height,length=length)
    g['93']=node('LTXVSeparateAVLatent',av_latent=['92',0])
    g['94']=node('LTXVConcatAVLatent',video_latent=['91',0],audio_latent=['93',1])
    g['31']['inputs']['samples']=['94',0]
    g['81']=node('HengeH3PureWindows',model=g['34']['inputs']['model'],window_frames=int(windows.get('window_frames',107)),overlap_frames=int(windows.get('overlap_frames',22)),accumulator_device='cpu')
    g['34']['inputs']['model']=['81',0]
    g['17']['inputs']['filename']=video.replace('.mp4','_refined.mp4')
    # Keep only ancestors of the saved output, so stage one cannot run again accidentally.
    keep=set()
    def visit(key):
        if key in keep:return
        keep.add(key)
        for value in g[key]['inputs'].values():
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and value[0] in g:visit(value[0])
    visit('17')
    return {key:value for key,value in g.items() if key in keep}


def fibo_graph(image,refs,instruction,seed):
    g={'1':node('UNETLoader',unet_name='fibo2_edit_turbo_int8_convrot.safetensors',weight_dtype='default'),'2':node('CLIPLoader',clip_name='qwen3vl_4b_int8_convrot.safetensors',type='fibo2',device='default'),'3':node('VAELoader',vae_name='flux2-vae.safetensors'),'4':node('LoadImage',image=image),'5':node('TextEncodeFibo2',clip=['2',0],vae=['3',0],prompt=instruction,negative_prompt='',width=0,height=0,batch_size=1,**{'images.image_1':['4',0]}),'6':node('KSampler',model=['1',0],positive=['5',0],negative=['5',1],latent_image=['5',2],seed=seed,steps=4,cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.),'7':node('VAEDecode',samples=['6',0],vae=['3',0]),'8':node('SaveImage',images=['7',0],filename_prefix=image.rsplit('.',1)[0]+'_fibo')}
    for i,p in enumerate(refs,2):g[str(20+i)]=node('LoadImage',image=p);g['5']['inputs'][f'images.image_{i}']=[str(20+i),0]
    return g

# FLUX.2 [klein] 4B (Black Forest Labs, Apache-2.0): first-frame edits. Same graph as ComfyUI's "Image Edit (FLUX.2 Klein
# 4B Distilled)" template: every picture is a ReferenceLatent, 4 steps, CFG 1. The output keeps the first image's size.
KLEIN={'unet':'flux-2-klein-4b-fp8.safetensors','clip':'qwen_3_4b.safetensors','vae':'flux2-vae.safetensors'}
def klein_graph(image,refs,instruction,seed,steps=4,prefix=None):
    g={'1':node('UNETLoader',unet_name=KLEIN['unet'],weight_dtype='default'),'2':node('CLIPLoader',clip_name=KLEIN['clip'],type='flux2',device='default'),
       '3':node('VAELoader',vae_name=KLEIN['vae']),'4':node('CLIPTextEncode',clip=['2',0],text=instruction),'5':node('ConditioningZeroOut',conditioning=['4',0]),
       '10':node('LoadImage',image=image),'11':node('ImageScaleToTotalPixels',image=['10',0],upscale_method='lanczos',megapixels=1.,resolution_steps=16),
       '12':node('GetImageSize',image=['11',0])}
    pos,neg=['4',0],['5',0]
    for i,p in enumerate([image]+list(refs)):
        if i:g[f'2{i}0']=node('LoadImage',image=p);g[f'2{i}1']=node('ImageScaleToTotalPixels',image=[f'2{i}0',0],upscale_method='lanczos',megapixels=1.,resolution_steps=16)
        src=['11',0] if i==0 else [f'2{i}1',0]
        g[f'3{i}0']=node('VAEEncode',pixels=src,vae=['3',0])
        g[f'3{i}1']=node('ReferenceLatent',conditioning=pos,latent=[f'3{i}0',0]);g[f'3{i}2']=node('ReferenceLatent',conditioning=neg,latent=[f'3{i}0',0])
        pos,neg=[f'3{i}1',0],[f'3{i}2',0]
    g.update({'40':node('EmptyFlux2LatentImage',width=['12',0],height=['12',1],batch_size=1),'41':node('Flux2Scheduler',steps=steps,width=['12',0],height=['12',1]),
              '42':node('CFGGuider',model=['1',0],positive=pos,negative=neg,cfg=1.),'43':node('KSamplerSelect',sampler_name='euler'),'44':node('RandomNoise',noise_seed=seed),
              '45':node('SamplerCustomAdvanced',noise=['44',0],guider=['42',0],sampler=['43',0],sigmas=['41',0],latent_image=['40',0]),
              '46':node('VAEDecode',samples=['45',0],vae=['3',0]),'47':node('SaveImage',images=['46',0],filename_prefix=prefix or image.rsplit('.',1)[0]+'_klein')})
    return g

# FLUX.3 [image klein] (optional, gated: FLUX Kommunity License, accept it on Hugging Face and set HF_TOKEN). Graph from
# Black Forest Labs' "Multiple image to image" workflow: ModelSamplingFlux shift log(16), ReferenceMultiLatent, 16 steps.
KLEIN3={'unet':'flux3-image-klein-int8-convrot.safetensors','clip':'qwen3vl_4b_int8_convrot.safetensors','vae':'flux2-vae.safetensors'}
def klein3_graph(image,refs,instruction,seed,steps=16,prefix=None):
    shift=math.log(16)
    g={'1':node('UNETLoader',unet_name=KLEIN3['unet'],weight_dtype='default'),'3':node('CLIPLoader',clip_name=KLEIN3['clip'],type='flux3',device='default'),
       '4':node('VAELoader',vae_name=KLEIN3['vae']),'5':node('CLIPTextEncode',clip=['3',0],text=instruction),'6':node('CLIPTextEncode',clip=['3',0],text=''),
       '10':node('LoadImage',image=image),'11':node('ImageScaleToTotalPixels',image=['10',0],upscale_method='lanczos',megapixels=1.,resolution_steps=16),
       '12':node('GetImageSize',image=['11',0]),
       '2':node('ModelSamplingFlux',model=['1',0],max_shift=shift,base_shift=shift,width=['12',0],height=['12',1]),
       '20':node('ReferenceMultiLatent',positive=['5',0],negative=['6',0],vae=['4',0],resolution='resize',**{'resolution.megapixels':1.,'images.image0':['10',0]}),
       '30':node('EmptyFlux2LatentImage',width=['12',0],height=['12',1],batch_size=1),
       '31':node('KSampler',model=['2',0],positive=['20',0],negative=['20',1],latent_image=['30',0],seed=seed,steps=steps,cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.),
       '32':node('VAEDecode',samples=['31',0],vae=['4',0]),'33':node('SaveImage',images=['32',0],filename_prefix=prefix or image.rsplit('.',1)[0]+'_klein3')}
    for i,r in enumerate(refs,1):g[f'4{i}']=node('LoadImage',image=r);g['20']['inputs'][f'images.image{i}']=[f'4{i}',0]
    return g

def subject_looks_graph(looks):
    # One node per marked person: the look of the person under the user's click, used to recognise them after cuts.
    g={}
    for i,(image,sid,x,y) in enumerate(looks):
        g[str(2*i+1)]=node('LoadImage',image=image)
        g[str(2*i+2)]=node('HengeSubjectLook',image=[str(2*i+1),0],subject_id=sid,x=float(x),y=float(y),sam_checkpoint='sam3.1_multiplex_fp16.safetensors')
    return g

def plate_mask_graph(video,width,height,length,filename):
    # People masks for the moving plate: native BiRefNet on every frame, saved as a grey video (white = people).
    return {'1':node('HengeLoadShot',video=video,pictures='[]',width=width,height=height,length=length),
            '2':node('LoadBackgroundRemovalModel',bg_removal_name='birefnet.safetensors'),
            '3':node('RemoveBackground',bg_removal_model=['2',0],image=['1',0]),'4':node('MaskToImage',mask=['3',0]),
            '5':node('HengeSaveVideo',images=['4',0],filename=filename,trim_frames=length,fps=24.)}

def find_people_graph(image,kind='person'):
    # One frame: SAM 3.1 finds and numbers every person (or animal) for the studio assistant.
    return {'1':node('LoadImage',image=image),'2':node('HengeFindPeople',image=['1',0],kind=kind,threshold=.4,sam_checkpoint='sam3.1_multiplex_fp16.safetensors'),
            '3':node('SaveImage',images=['2',0],filename_prefix=image.rsplit('.',1)[0]+'_people'),'4':node('HengeTextResult',text=['2',1])}

def marks_preview_graph(video,width,height,length,trim_frames,bindings,source_kind,segment_start,preserve_objects,filename,labels=False):
    # The 2D color guide at full opacity: the UI lays it over the source with the chosen opacity, which is exactly the
    # blend HengeGuide makes, so the opacity can be tried live without running SAM again.
    return {'1':node('HengeLoadShot',video=video,pictures='[]',width=width,height=height,length=length),
            '2':node('HengeGuide',images=['1',0],representation='2d',bindings=json.dumps(bindings),source_kind=source_kind,segment_start=segment_start,
                     sam_checkpoint='sam3.1_multiplex_fp16.safetensors',body_model='sam_3d_body_dinov3_bf16.safetensors',preserve_objects=json.dumps(preserve_objects or []),mask_settings=json.dumps({'mark_opacity':1,'labels':labels})),
            '4':node('HengeSaveVideo',images=['2',0],filename=filename,trim_frames=trim_frames,fps=24.)}

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


def split_at_every_cut(total,per_shot,context,cuts,min_gap=24):
    # A new shot at every camera cut (cuts closer than min_gap frames are skipped), long scenes split by per_shot.
    boundaries=[0]
    for c in sorted({int(c) for c in cuts}):
        if c-boundaries[-1]>=min_gap and total-c>=min_gap:boundaries.append(c)
    boundaries.append(total)
    output=[]
    for start,end in zip(boundaries,boundaries[1:]):
        for i,shot in enumerate(split_frames(end-start,per_shot,context)):
            output.append({**shot,'start':shot['start']+start,'reset_context':i==0})
    return output


def split_at_points(total,per_shot,context,cuts,points,min_gap=24,every_cut=False):
    # Like split_on_cuts, with a second kind of preferred end: suggested points inside a take (the end of a line, a pause
    # between actions). A camera cut starts the next shot clean; a point ends the shot there and the next one carries
    # `context` frames, since it is the same take. every_cut: each camera cut ends a shot (marked people are tracked
    # shot by shot). Without a cut or point in reach the shot keeps the requested length.
    def keep(values):
        out=[]
        for c in sorted({int(c) for c in values}):
            if c-(out[-1] if out else 0)>=min_gap and total-c>=min_gap:out.append(c)
        return out
    cuts=keep(cuts);points=[p for p in keep(points) if p not in cuts]
    output=[];start=0;overlap=0
    while start<total:
        reach=min(total,start+per_shot)
        near=[c for c in cuts if start+overlap+min_gap<=c<=reach and c<total]
        if near:
            end=near[0] if every_cut else near[-1]
            output.append({'start':start,'frames':end-start,'overlap':overlap,'length':grid_frames(end-start),'reset_context':overlap==0});start=end;overlap=0;continue
        if reach>=total:
            output.append({'start':start,'frames':total-start,'overlap':overlap,'length':grid_frames(total-start),'reset_context':overlap==0});break
        end=([c for c in points if start+overlap+min_gap<=c<=reach] or [reach])[-1]
        output.append({'start':start,'frames':end-start,'overlap':overlap,'length':grid_frames(end-start),'reset_context':overlap==0})
        start=end-context;overlap=context
    return output


def split_on_cuts(total,per_shot,context,cuts,min_gap=24):
    # Shots stay as long as the requested length allows; a camera cut only chooses where one ends: the last cut
    # within reach, so the next shot starts clean at the cut (no context). Cuts inside a shot are rendered straight
    # through. With no cut in reach the shot is split mid-scene and the next one carries `context` frames.
    # Scene detection fires on flashes, fades and fast pans; a cut closer than min_gap frames to a boundary (or the
    # end) would only buy a near-empty shot.
    marks=[]
    for c in sorted({int(c) for c in cuts}):
        if c-(marks[-1] if marks else 0)>=min_gap and total-c>=min_gap:marks.append(c)
    output=[];start=0;overlap=0
    while start<total:
        if start+per_shot>=total:end=total
        else:
            reachable=[c for c in marks if start+overlap+min_gap<=c<=start+per_shot]
            end=reachable[-1] if reachable else None
        if end is None:
            output.append({'start':start,'frames':per_shot,'overlap':overlap,'length':grid_frames(per_shot),'reset_context':overlap==0})
            start+=per_shot-context;overlap=context
        else:
            output.append({'start':start,'frames':end-start,'overlap':overlap,'length':grid_frames(end-start),'reset_context':overlap==0})
            start=end;overlap=0
    return output


