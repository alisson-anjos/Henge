"""Build the four public Motion Transfer examples from a ComfyUI /object_info snapshot.
Usage: python scripts/workflows/build_motion_transfer.py /path/to/object_info.json
Does not queue inference or download/upload models.
"""
import copy,json,sys,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCHEMAS=json.loads(Path(sys.argv[1]).read_text())
OUT=ROOT/'workflows'
PREFIX='minimax_h3_motion_transfer'
ADAPTER='minimax_h3_ref2va_training_adapter_v2.safetensors'
TURBO='minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors'
GUIDE_LORA='minimax_h3_motion_transfer_v1.0_ref2va.safetensors'
TARA_LORA='minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors'
REQUEST='motion_transfer: Transfer the performance from the guide to the subject in <Picture 1>. Preserve its identity and outfit. Keep the guide setting and camera unless explicitly requested otherwise.'
PROMPT='''motion_transfer:
subject_definitions:
<Subject 1> is the subject in <Picture 1>; preserve its visible identity, face, hair or fur, body proportions and outfit. Picture roles are defined by this prompt, not by slot number. Additional connected pictures may specify other subjects, outfits, objects, environments or style; edit these sections to assign each actual attached picture explicitly.
summary:
[video generation + reference] Transfer the source performance to <Subject 1>, preserving the action order, timing and camera of the guide.
retention_analysis:
<Subject 1>: preserve the reference identity and appearance throughout the clip. Keep the guide setting unless a connected reference is explicitly assigned to replace it.
detailed_description:
[Shot 1] <Subject 1> follows the guide's motion, poses, gestures, head movement and expression in order and at matching times. Keep identity stable during occlusion, turns and back views. Do not turn a back view into a front view. Several reference images may describe one subject; image count does not imply performer count. Do not copy an identity reference's still pose or backdrop as the motion or setting.
overall_soundscape:
Keep the source soundtrack when connected; do not invent dialogue.
non_diegetic_music:
No additional music requested.'''
TEMPLATE='''Write an English MiniMax H3 motion_transfer: execution prompt for the actual shot and attached references. Use the six H3 sections: subject_definitions, summary, retention_analysis, detailed_description, overall_soundscape, non_diegetic_music. Infer reference roles only from the user request and the individually inspected reference images. N images are NOT a required person/background pair and NOT necessarily N performers. Multiple pictures can define one identity, clothing, an object, a location or a style. Mention only actually attached Picture indices. Preserve the chronological guide action and timings; separate its performance from reference appearance. Match every intended performer to its actual identity, including late entrances and back views. Preserve the guide camera and setting unless explicitly asked to change them. Do not invent unseen details, speech or music. Avoid assigning reference identities solely by left/right position. If the request is ambiguous, follow its explicit assignments and do not invent an extra performer.'''
REF_NOTE='''# References are flexible: 1..N pictures, not a person/background pair
Only Picture 1 is connected by default. Picture 2 is OPTIONAL and disconnected. Add consecutive slots 1..N as needed (native H3 supports up to 9); in Planner use the reference list, globally or per shot.

A picture may describe a character, outfit, object, setting or style. Several pictures may describe the SAME character. Two images can be two characters, two views of one identity, or any other explicitly requested combination. A separate background is NOT required. Image count is NOT performer count.

Assign the role of every attached picture in the prompt. The guide supplies motion and timing. Preserve its setting/camera unless you explicitly ask to replace them. Avoid ambiguity for multiple performers: include clothes/identity, time of entry, occlusion and back views. Inspect the generated prompt before relying on it. Prompt instructions improve binding; they do not guarantee perfect identity tracking.

Examples: one identity picture; three distinct character pictures; two views of one identity plus an outfit; or character + object + setting. These are choices, not mandatory slots. No automatic background removal is applied in these examples.'''
KITCHEN_NOTE='''# Comfy Kitchen + TARA: supported with the MODIFIED temporal kernel
Guide Latents can use ordinary Comfy Kitchen attention. TARA's fused one-pass Kitchen path additionally needs the modified temporal extension (library AND Python API); installing stock comfy-kitchen alone does not provide it.

Safe default here: TARA uses PyTorch model attention + Flash partitions (no compile). To try Kitchen, select comfy kitchen attention in Model Attention Backend and comfy kitchen (experimental) in the TARA/conditioning backend control.

Update BFSNodes main (1.115.34+), restart ComfyUI, then let BFS install its verified temporal extension on supported Linux/Windows x86_64 NVIDIA GPUs. CUDA-13-capable driver required; PyTorch can use CUDA 12.x. Unsupported/offline setups may keep a slower compatibility path. Flash partitions does not require this extension.

Confirm the fused kernel in the sampling log: Kitchen ONE-PASS dense kernel ACTIVE (or Kitchen ONE-PASS sol kernel ACTIVE when separately using supported Sol attention). A completed render alone does not prove it used the modified kernel. Do not add VSA/SLA to these examples.

Setup and limitations: https://github.com/alisson-anjos/ComfyUI-BFSNodes/blob/main/H3_NATIVE_TEMPORAL.md#kernel-downloads
Manual install: https://github.com/alisson-anjos/comfy-kitchen/blob/feat/h3-native-temporal/MANUAL_TEMPORAL_INSTALL.md
Verified release/checksums: https://github.com/alisson-anjos/comfy-kitchen/releases/tag/temporal-native-0413d43878606425a84aa400f1e5da50ed9dcdad
Binaries passed ABI/build checks; not every GPU/OS has full-video validation.'''

class Graph:
 def __init__(self):self.nodes=[];self.links=[];self.values={}
 def add(self,kind,title,pos,values=None,size=None):
  values=values or {};i=len(self.nodes)+1;schema=SCHEMAS[kind];inputs=[];widgets=[];named={}
  for group in ('required','optional'):
   for name,spec in schema['input'].get(group,{}).items():
    typ=spec[0];opts=spec[1] if len(spec)>1 else {};combo=isinstance(typ,list) or typ=='COMBO';widget=combo or typ in ('INT','FLOAT','BOOLEAN','STRING','COMFY_DYNAMICCOMBO_V3')
    if widget and not opts.get('forceInput'):
     default=opts.get('default',(typ[0] if isinstance(typ,list) and typ else opts.get('options',[None])[0]))
     if isinstance(default,dict):default=default['key']
     value=values.get(name,default if default is not None else {'INT':0,'FLOAT':0.,'BOOLEAN':False,'STRING':''}.get(typ,''));widgets.append(value);named[name]=value
     if opts.get('control_after_generate'):widgets.append('fixed')
     if typ=='COMFY_DYNAMICCOMBO_V3' and name=='format':widgets.append('auto')
    elif typ!='COMFY_AUTOGROW_V3':inputs.append({'name':name,'type':','.join(typ) if isinstance(typ,list) else typ,'link':None,**({'shape':7} if group=='optional' else {})})
  n={'id':i,'type':kind,'title':title,'pos':list(pos),'size':size or [340, max(100,80+len(widgets)*28)],'flags':{},'order':i-1,'mode':0,'inputs':inputs,'outputs':[{'name':name,'type':typ,'links':[]} for name,typ in zip(schema['output_name'],schema['output'])],'properties':{'Node name for S&R':kind},'widgets_values':widgets,'widgets_values_named':named}
  if kind.startswith(('BFS','BFSMini')):n['properties'].update(cnr_id='bfsnodes',ver='1.115.34')
  self.nodes.append(n);self.values[i]=named;return i
 def link(self,source,slot,target,name,typ=None):
  a=self.nodes[source-1];b=self.nodes[target-1];ports=b['inputs'];p=next((p for p in ports if p['name']==name),None)
  if p is None:
   typ=typ or a['outputs'][slot]['type'];p={'name':name,'type':typ,'link':None}
   if name in self.values[target]:p['widget']={'name':name}
   ports.append(p)
  assert p['link'] is None,(target,name)
  lid=len(self.links)+1;typ=typ or a['outputs'][slot]['type'];self.links.append([lid,source,slot,target,ports.index(p),typ]);p['link']=lid;a['outputs'][slot]['links'].append(lid)
 def note(self,title,text,pos,size=(650,450)):
  i=len(self.nodes)+1;self.nodes.append({'id':i,'type':'MarkdownNote','title':title,'pos':list(pos),'size':list(size),'flags':{},'order':i-1,'mode':0,'inputs':[],'outputs':[],'properties':{},'widgets_values':[text],'color':'#234','bgcolor':'#345'});return i
 def save(self,name,method,planner):
  d={'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/workflows/'+name)),'revision':0,'last_node_id':len(self.nodes),'last_link_id':len(self.links),'nodes':self.nodes,'links':self.links,'groups':[],'config':{},'extra':{'ds':{'scale':.55,'offset':[100,180]},'henge_motion_workflow':{'version':1,'method':method,'planner':planner,'reference_policy':'1..N flexible roles; no required background','base':'Ref2VA','bfs_min_version':'1.115.34'}},'version':.4};(OUT/name).write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n');return d

def build(tara=False,planner=False):
 g=Graph();method='tara' if tara else 'guide_latents';variant='planner' if planner else 'native_nodes';name=f'{PREFIX}_{"tara_" if tara else ""}workflow_{variant}_v1.0.json'
 base=g.add('UNETLoader','MiniMax H3 Ref2VA base',(0,0),{'unet_name':'minimax_h3_ref2va_pruned_int8_convrot.safetensors','weight_dtype':'default'})
 adapter=g.add('LoraLoaderModelOnly','Training adapter V2 — strength 1',(0,160),{'lora_name':ADAPTER,'strength_model':1.})
 turbo=g.add('LoraLoaderModelOnly','DMD Ref2VA 8-step turbo',(0,320),{'lora_name':TURBO,'strength_model':1.})
 task=g.add('LoraLoaderModelOnly','Motion Transfer TARA v1.0' if tara else 'Motion Transfer v1.0 — Guide Latents',(0,480),{'lora_name':TARA_LORA if tara else GUIDE_LORA,'strength_model':1.})
 attention=g.add('ModelAttentionBackend','Attention — see Kitchen/TARA note',(0,640),{'attention':'pytorch attention' if tara else 'comfy kitchen attention'})
 shift=g.add('MiniMaxH3SigmaShift','H3 sampling shift',(0,800),{'shift_video':12.,'shift_audio':3.})
 for a,b in zip([base,adapter,turbo,task,attention],[adapter,turbo,task,attention,shift]):g.link(a,0,b,'model')
 clip=g.add('CLIPLoader','H3 text encoder — NOT the prompt VLM',(400,0),{'clip_name':'qwen3vl_32b_minimax_h3_int8_convrot.safetensors','type':'minimax','device':'default'})
 vae=g.add('VAELoader','H3 video VAE',(400,160),{'vae_name':'minimax_h3_video_vae_fp16.safetensors'})
 if planner:
  vlm=g.add('CLIPLoader','Prompt VLM — independent of the H3 encoder',(400,320),{'clip_name':'qwen3.5_9b_w4a8_gptq.safetensors','type':'minimax','device':'default'})
  state={'video':'guide.mp4','fps':24,'grid':'H3 (17n+5)','mode':'shots','max_s':4.5,'min_s':1.,'sensitivity':.5,'max_parts':0,'max_total_s':0,'start_s':0,'end_s':0,'start_f':None,'end_f':None,'track':None,'bounds':[],'segs':[],'global_refs':['reference_1.png'],'global_ref':'reference_1.png','global_ref2':'','global_prompt':REQUEST,'megapixels':.4,'multiple':32,'generation_size_mode':'megapixels','run':'recursive','between_shots':'keep','shot_cache':'output','shot_storage':'lossless','unload_before_join':True,'auto_continue':True,'skip_fill':'original','audio_mode':'auto','ref_details':{},'picture_details':{},'auto_prompt':{'enabled':True,'frames':8,'source':'guide','template':TEMPLATE,'style':'h3','trigger':'motion_transfer'},'auto_prompts':{},'vlm_cfg':{'enabled':True,'frames':8,'max_tokens':3072,'auto_segment':False,'auto_shot':False,'instruction':'','describe_preset':'custom','describe_custom':'','fit_prompt':True,'temperature':0,'seed':42,'image_max_side':1024},'mask_cfg':{},'cast':{},'cast_split':False,'cast_only':False,'filters':{},'picture_colors':[],'picture_cfg':{},'second_pass':{'enabled':False}}
  plan=g.add('BFSShotPlanner','Upload guide + N references; write request; review shots',(820,0),{'plan':json.dumps(state,ensure_ascii=False)},[700,760]);g.link(vlm,0,plan,'vlm')
  cond=g.add('BFSShotH3ConditioningSimple','TARA native Video 1 — no Add Guide' if tara else 'Guide Latents — Add Guide + CLIP video context',(1580,0),{'guide_mode':'TARA - Native Temporal Alignment (experimental)' if tara else 'aligned guide + CLIP video context','with_audio':False,'ref_image_size':'match','inpaint':'off','source_blur':'off','native_guide_scale':1.,'native_temporal_backend':'flash partitions (no compile)'},[400,500])
  g.link(plan,0,cond,'shot');g.link(clip,0,cond,'clip');g.link(vae,0,cond,'vae');g.link(vlm,0,cond,'vlm');g.link(shift,0,cond,'model');model=(cond,3);positive=(cond,0);latent=(cond,1)
 else:
  video=g.add('VHS_LoadVideoFFmpeg','Upload guide — 24 fps; initial short test (107 frames)',(820,0),{'video':'guide.mp4','force_rate':24.,'frame_load_cap':107,'format':'None'},[360,420]);g.nodes[video-1].pop('widgets_values_named',None);g.nodes[video-1]['widgets_values']={'video':'guide.mp4','force_rate':24.,'custom_width':0,'custom_height':0,'frame_load_cap':107,'start_time':0,'format':'None'}
  prepare=g.add('BFSH3PrepareNativeVideo','Source-derived geometry / frame grid / trim count',(820,480),{'source_fps':24.,'output_scale':1.,'max_megapixels':.4,'reference_scale':1.,'max_frames':107,'frame_rounding':'pad last frame','analysis_frames':8,'request':REQUEST},[360,390]);g.link(video,0,prepare,'images')
  ref=g.add('LoadImage','Picture 1 — reference; role defined by your prompt',(1240,0),{'image':'reference_1.png'},[330,330]);g.add('LoadImage','OPTIONAL Picture 2 — any role; connect only if needed',(1240,390),{'image':'reference_2.png'},[330,330])
  cond=g.add('MiniMaxH3ReferenceToVideo','Native H3 — assign N picture roles in the prompt',(1630,0),{'prompt':PROMPT,'width':864,'height':480,'length':107,'ref_image_size':'match'},[500,680]);g.link(clip,0,cond,'clip');g.link(vae,0,cond,'vae');g.link(prepare,2,cond,'width');g.link(prepare,3,cond,'height');g.link(prepare,4,cond,'length');g.link(ref,0,cond,'ref_images.ref_image_1');g.nodes[cond-1]['inputs'].append({'name':'ref_images.ref_image_2','type':'IMAGE','link':None,'shape':7})
  if tara:
   g.link(prepare,0,cond,'ref_videos.ref_video_1');temporal=g.add('BFSMiniMaxH3NativeTemporal','TARA — this MODEL drives both guider and scheduler',(400,500),{'attention_backend':'flash partitions (no compile)','structure_guidance':1.},[350,360]);g.link(shift,0,temporal,'model');model=(temporal,0);positive=(cond,0)
  else:
   guide=g.add('MiniMaxH3AddGuide','Aligned video latents — frame 0 (not native ref_video)',(1630,760),{'frame_idx':0});g.link(cond,0,guide,'positive');g.link(cond,1,guide,'latent');g.link(vae,0,guide,'vae');g.link(prepare,0,guide,'image');model=(shift,0);positive=(guide,0)
  latent=(cond,1)
 guider=g.add('CFGGuider','CFG 1 — positive conditioning + the correct MODEL',(2200,0),{'cfg':1.});g.link(*model,guider,'model');g.link(*positive,guider,'positive');g.link(*positive,guider,'negative')
 noise=g.add('RandomNoise','Seed — keep fixed for comparisons',(2200,240),{'noise_seed':42});sampler=g.add('KSamplerSelect','Euler sampler',(2200,380),{'sampler_name':'euler'});schedule=g.add('BasicScheduler','8 steps for the selected DMD turbo',(2200,520),{'scheduler':'simple','steps':8,'denoise':1.});g.link(*model,schedule,'model')
 sample=g.add('SamplerCustomAdvanced','Sample each shot' if planner else 'Sample the prepared short clip',(2600,0));g.link(noise,0,sample,'noise');g.link(guider,0,sample,'guider');g.link(sampler,0,sample,'sampler');g.link(schedule,0,sample,'sigmas');g.link(*latent,sample,'latent_image')
 separate=g.add('LTXVSeparateAVLatent','Video/audio latent streams',(2600,250));g.link(sample,0,separate,'av_latent');decode=g.add('VAEDecodeTiled','Tiled video decode',(2600,410));g.link(separate,0,decode,'samples');g.link(vae,0,decode,'vae')
 if planner:
  join=g.add('BFSShotJoin','Join shots — crossfade OFF; original audio',(3020,0),{'crossfade':0,'comparison':False,'label':'Motion Transfer TARA' if tara else 'Motion Transfer Guide Latents','save_to':'mp4 file (long videos, low memory)','filename_prefix':'motion_transfer_'+method,'mp4_crf':17},[440,650]);g.link(decode,0,join,'images');g.link(plan,0,join,'shots');g.link(plan,5,join,'audio');g.link(plan,7,join,'timeline')
  g.note('Planner use / output / prompts','''# Planner workflow\nUpload your guide in BFS Shot Planner and replace the placeholder reference list with your own 1..N images. Edit the request to assign their roles. Auto Prompt is enabled; preview/review it in the panel.\n\nDefault: camera cuts, max 4.5 s/shot, 0.4 MP, recursive execution and lossless shot cache. The planner's conditioning MODEL output must reach BOTH guider and scheduler, especially for TARA.\n\nBFS Shot Join saves the final MP4 directly (original aligned soundtrack) to avoid re-encoding a long IMAGE batch. It is the output node; no second Save Video is required. Crossfade is 0 to avoid blended shot seams.\n\nSegmentation, masks, color marks, cropping and extra images are optional. No fixed person/background pair, no automatic background stripping. Adding references or changing the request invalidates cached prompts; clear/rebuild the plan when changing media.''',(820,950),(700,420))
 else:
  trim=g.add('ImageFromBatch','Trim grid padding to actual source duration',(3020,0),{'batch_index':0,'length':107});g.link(decode,0,trim,'image');g.link(prepare,8,trim,'length');create=g.add('CreateVideo','24 fps; original source audio',(3020,220),{'fps':24.});g.link(trim,0,create,'images');g.link(video,2,create,'audio');save=g.add('SaveVideo','Save Motion Transfer output',(3020,450),{'filename_prefix':'motion_transfer/'+method,'format':'auto','codec':'auto'});g.link(create,0,save,'video')
  g.note('Native use / timing / limits','''# Native conditioning, with small public BFS helpers\nUpload the guide and Picture 1. The second image is disconnected and OPTIONAL; connect more native ref_images slots consecutively (up to 9) and assign their roles in the editable H3 prompt. No Planner or prompt VLM is required.\n\nSource aspect ratio sets the output; 0.4 MP cap; 24 fps; initial test limited to 107 decoded frames. To use a longer clip, change BOTH VHS frame_load_cap and Prepare max_frames. Prefer the Planner workflow for long videos and camera cuts. Padding is trimmed to the actual source duration.\n\nAudio output copies the source; no dialogue is inferred or generated. Motion/identity fidelity still needs visual review. Native means native H3 conditioning, not zero custom nodes: BFS handles source geometry (and TARA), VHS loads the video. No Henge private nodes required.''',(820,950),(700,420))
 g.note('START HERE — choose the matching Motion Transfer LoRA',f'''# Motion Transfer v1.0 — {"TARA" if tara else "Guide Latents"} / {variant}\n\nMatching LoRA: {TARA_LORA if tara else GUIDE_LORA}\nTraining adapter V2 → DMD Ref2VA 8-step turbo → task LoRA; strengths 1, CFG 1, Euler/simple, 8 steps. These are inference defaults, not quality guarantees. Do not load another copy of an already merged adapter/turbo.\n\n{"TARA keeps the guide in native ref_video_1 and patches model attention. No full-video Add Guide is used in the first-pass contract." if tara else "The guide enters through Add Guide, not native video-reference latents. Planner additionally shows sampled guide frames to the text encoder."}\n\nDependencies: updated ComfyUI native MiniMax H3, ComfyUI-BFSNodes 1.115.34+, VideoHelperSuite for native video loading. Model download links are in docs/motion-transfer.md in the HF repo. Select installed model names if your files are in subfolders.\n\nThese graphs are derived from the native/Planner contracts of the published Character Swap v1.1 workflows, with Motion Transfer-specific prompts and model wiring. No bundled private media; replace guide.mp4/reference_1.png before queueing.''',(0,1130),(700,480))
 g.note('N reference images — read before assigning roles',REF_NOTE,(1580,1130),(680,520));g.note('Kitchen compatibility / MODIFIED TARA kernel',KITCHEN_NOTE,(2320,1130),(760,650));return g.save(name,method,planner)

if __name__=='__main__':
 for tara in (False,True):
  for planner in (False,True):
   d=build(tara,planner);print(d['extra']['henge_motion_workflow'],len(d['nodes']),'nodes')
