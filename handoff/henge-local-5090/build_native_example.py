"""Build public-node API and visual examples. Does not enqueue GPU work."""
import argparse, importlib.util, json, urllib.request
parser=argparse.ArgumentParser()
parser.add_argument("--auto-prompt",action="store_true")
parser.add_argument("--bfs-root",default="/data/ComfyUI-BFSNodes")
parser.add_argument("--object-info-url",default="http://127.0.0.1:8191/object_info")
args=parser.parse_args()
from pathlib import Path
R=Path(__file__).resolve().parent/'workflows'
schema=json.load(urllib.request.urlopen(args.object_info_url))
schema['VHS_LoadVideo']={'output':['IMAGE','INT','AUDIO','VHS_VIDEOINFO'],'output_name':['IMAGE','frame_count','audio','video_info'],'input':{'required':{'video':[['guide.mp4']],'force_rate':['FLOAT',{}],'custom_width':['INT',{}],'custom_height':['INT',{}],'frame_load_cap':['INT',{}],'skip_first_frames':['INT',{}],'select_every_nth':['INT',{}]}}}
helper=None
if args.auto_prompt:
 spec=importlib.util.spec_from_file_location('native_workflow_helper',Path(args.bfs_root)/'bfs_h3_native_workflow.py')
 helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 for name,cls in helper.NODE_CLASS_MAPPINGS.items():
  schema[name]={'input':cls.INPUT_TYPES(),'output':list(cls.RETURN_TYPES),'output_name':list(cls.RETURN_NAMES),'display_name':helper.NODE_DISPLAY_NAME_MAPPINGS[name]}
g={};layout={};titles={}
def n(i,typ,xy,title=None,**kw):g[str(i)]={'class_type':typ,'inputs':kw};layout[i]=xy;titles[i]=title or schema[typ].get('display_name',typ)
n(1,'UNETLoader',(0,0),unet_name='minimax_h3_ref2va_pruned_int8_convrot.safetensors',weight_dtype='default')
n(2,'LoraLoaderModelOnly',(0,180),title='10500 + V2 merged — strength 1; do not add V2 again',model=['1',0],lora_name='motion10500_plus_training_adapter_v2_exact.safetensors',strength_model=1.)
n(3,'MiniMaxH3SigmaShift',(0,400),model=['2',0],shift_video=12.,shift_audio=3.)
n(4,'BFSMiniMaxH3NativeTemporal',(370,0),title='TARA — experimental; MODEL must reach guider',model=['3',0],motion_video_index=1,strength=2.,window_seconds=.2,falloff_seconds=.25,max_penalty=6.,attention_backend='flash partitions (no compile)')
n(5,'CLIPLoader',(0,580),clip_name='qwen3vl_32b_minimax_h3_int8_convrot.safetensors',type='minimax',device='default')
n(6,'VAELoader',(0,760),vae_name='minimax_h3_video_vae_fp16.safetensors')
n(7,'PrimitiveInt',(370,410),title='OUTPUT WIDTH — multiple of 32',value=512)
n(8,'PrimitiveInt',(370,530),title='OUTPUT HEIGHT — multiple of 32',value=288)
n(9,'PrimitiveInt',(370,650),title='FRAMES — 17n+5; 107 = 4.46 seconds at 24 fps',value=107)
n(10,'VHS_LoadVideo',(750,0),title='GUIDE — upload video; resample 24 fps; frame cap linked',video='guide.mp4',force_rate=24.,custom_width=0,custom_height=0,frame_load_cap=['9',0],skip_first_frames=0,select_every_nth=1)
n(11,'ImageScale',(750,430),title='REFERENCE VIDEO SIZE — independent of output; multiples of 32',image=['10',0],upscale_method='area',width=512,height=288,crop='center')
n(12,'LoadImage',(750,710),title='Picture 1 — identity',image='picture_1.png')
n(13,'LoadImage',(750,1030),title='Picture 2 — background',image='picture_2.png')
prompt='motion_transfer: Replace the main performer in <Video 1> with the subject from <Picture 1>, preserving its identity and clothing throughout the video. Replace the entire environment with the setting from <Picture 2>. Transfer the guide action sequence, body gestures, head motion, gaze and visible mouth movements with the same timing. Preserve the source camera movement and framing and any objects required for the performance. Integrate the reference subject and retained objects naturally into the new setting.'
n(14,'MiniMaxH3ReferenceToVideo',(1190,0),title='NATIVE H3 — Video 1 is motion; Picture 1 identity; Picture 2 setting',clip=['5',0],vae=['6',0],prompt=prompt,width=['7',0],height=['8',0],length=['9',0],ref_image_size='match',**{'ref_images.ref_image_1':['12',0],'ref_images.ref_image_2':['13',0],'ref_videos.ref_video_1':['11',0]})
n(15,'CFGGuider',(1690,0),model=['4',0],positive=['14',0],negative=['14',0],cfg=1.)
n(16,'RandomNoise',(1690,200),noise_seed=424242)
n(17,'KSamplerSelect',(1690,360),sampler_name='euler')
n(18,'BasicScheduler',(1690,500),model=['4',0],scheduler='simple',steps=28,denoise=1.)
n(19,'SamplerCustomAdvanced',(2070,0),noise=['16',0],guider=['15',0],sampler=['17',0],sigmas=['18',0],latent_image=['14',1])
n(20,'LTXVSeparateAVLatent',(2070,350),av_latent=['19',0])
n(21,'VAEDecode',(2450,0),samples=['20',0],vae=['6',0])
n(22,'CreateVideo',(2450,230),images=['21',0],fps=24.)
n(23,'SaveVideo',(2830,0),video=['22',0],filename_prefix='Henge/TARA_native_10500_v2',format='auto',**{'format.codec':'auto'})
if args.auto_prompt:
 for i in [7,8,9,11]:del g[str(i)]
 g['10']['inputs']['frame_load_cap']=0
 titles[13]='OPTIONAL Picture 2 — connect to Describe References ref_image_2 if needed'
 titles[10]='GUIDE — source dimensions; force 24 fps; automatic frame count'
 n(24,'BFSH3PrepareNativeVideo',(1130,0),images=['10',0],source_fps=24.,output_scale=1.,max_megapixels=.4,reference_scale=1.,max_frames=0,frame_rounding='pad last frame',analysis_frames=12,request='Replace the main performer with <Picture 1>. Preserve the guide performance, timing, camera motion and source setting unless I explicitly request another change.')
 n(25,'CLIPLoader',(750,1380),title='PROMPT VLM — generation capable; independent of H3 encoder',clip_name='qwen3-vl-4b-heretic_int8_dynamic_convrot.safetensors',type='minimax',device='default')
 n(26,'BFSH3DescribeReferences',(1570,720),clip=['25',0],request=['24',7],tokens_per_image=384,max_image_side=1024,ref_image_1=['12',0])
 n(27,'TextGenerate',(1570,0),title='Generate Text 1 — analyze numbered guide frames only',clip=['25',0],prompt=['24',6],image=['24',1],max_length=1024,sampling_mode='off',thinking=False,use_default_template=True,mtp='off')
 n(28,'BFSH3BuildNativePrompt',(1990,400),request=['24',7],inventory=['26',1],guide_analysis=['27',0],metadata=['24',5],template=helper.FINAL_TEMPLATE,mode='motion_transfer')
 n(29,'TextGenerate',(2420,400),title='Generate Text 2 — final six-section H3 prompt',clip=['25',0],prompt=['28',0],max_length=3072,sampling_mode='off',thinking=False,use_default_template=True,mtp='off')
 n(14,'BFSH3NativeReferenceSetToVideo',(2850,0),title='Native H3 — same N references as writer; Video1; NO Add Guide',clip=['5',0],vae=['6',0],reference_video=['24',0],references=['26',0],prompt=['29',0],width=['24',2],height=['24',3],length=['24',4],ref_image_size='match',validate_h3_sections=True)
 g['23']['inputs']['filename_prefix']='Henge/TARA_native_auto_prompt'
 for i in range(15,24):layout[i]=[layout[i][0]+1540,layout[i][1]]
 n(30,'ImageFromBatch',(3990,250),title='Trim grid padding — keep actual source duration',image=['21',0],batch_index=0,length=['24',8])
 g['22']['inputs']['images']=['30',0]
 n(31,'PreviewAny',(2420,900),title='Review generated H3 prompt',source=['29',0])
 n(32,'PreviewAny',(1130,650),title='Actual source / output geometry and padding',source=['24',5])
 # The final prompt remains editable by bypassing its writer and connecting a STRING.

# Dynamic combo child is recorded as a widget for the visual workflow.
# Check required fields and connection types against actual core/helper schemas.
for key,item in g.items():
 definition=schema[item['class_type']]['input']
 missing=set(definition.get('required',{}))-set(item['inputs'])
 assert not missing,(key,missing)
 for name,val in item['inputs'].items():
  if not(isinstance(val,list) and len(val)==2 and isinstance(val[0],str)):continue
  declared=definition.get('required',{}).get(name,definition.get('optional',{}).get(name))
  if declared and isinstance(declared[0],str) and not declared[0].startswith('COMFY_'):
   actual=schema[g[val[0]]['class_type']]['output'][val[1]]
   assert declared[0] in (actual,'*'),(key,name,declared[0],actual)
nodes=[];links=[];byid={};lid=0
for idx,(key,item) in enumerate(g.items()):
 i=int(key);s=schema[item['class_type']];ins=[];widgets=[];named={}
 for name,val in item['inputs'].items():
  link=isinstance(val,list) and len(val)==2 and isinstance(val[0],str)
  if link:
   source,slot=val;outtype=schema[g[source]['class_type']]['output'][slot]
   inp={'name':name,'type':outtype,'link':None}
   definition=s.get('input',{}).get('required',{}).get(name,s.get('input',{}).get('optional',{}).get(name))
   if definition and definition[0] in ['INT','FLOAT','STRING','BOOLEAN']:inp['widget']={'name':name}
   ins.append(inp)
  else:
   widgets.append(val);named[name]=val
   if item['class_type']=='RandomNoise' and name=='noise_seed':widgets.append('fixed')
 outputs=[{'name':s.get('output_name',s['output'])[j],'type':typ,'links':[]} for j,typ in enumerate(s['output'])]
 node={'id':i,'type':item['class_type'],'pos':layout[i],'size':[360,420 if i==14 else 280 if i==10 else 180],'flags':{},'order':idx,'mode':0,'inputs':ins,'outputs':outputs,'title':titles[i],'properties':{'Node name for S&R':item['class_type']},'widgets_values':widgets,'widgets_values_named':named}
 if item['class_type']=='MiniMaxH3ReferenceToVideo':node['widgets_values']=[prompt,512,288,107,'match']
 if item['class_type']=='VHS_LoadVideo':
  node['widgets_values']={**named,'frame_load_cap':0 if args.auto_prompt else 107}
 if item['class_type']=='TextGenerate':node['widgets_values']=['',item['inputs']['max_length'],'off',False,True,'off']
 if item['class_type']=='BFSH3DescribeReferences':
  node['widgets_values']=['',384,1024]
  for j in range(2,10):node['inputs'].append({'name':f'ref_image_{j}','type':'IMAGE','link':None})
 if item['class_type']=='BFSH3NativeReferenceSetToVideo':node['widgets_values']=[512,288,107,'match',True]
 nodes.append(node);byid[i]=node
for key,item in g.items():
 dst=byid[int(key)];slot=0
 for name,val in item['inputs'].items():
  if not(isinstance(val,list) and len(val)==2 and isinstance(val[0],str)):continue
  lid+=1;source,j=val;inp=dst['inputs'][slot];inp['link']=lid;byid[int(source)]['outputs'][j]['links'].append(lid)
  links.append([lid,int(source),j,int(key),slot,inp['type']]);slot+=1
visual={'last_node_id':max(map(int,g)),'last_link_id':lid,'nodes':nodes,'links':links,'groups':[],'config':{},'extra':{'ds':{'scale':.65,'offset':[100,100]},'workflowRendererVersion':'LG'},'version':.4}
# Cross-check every visual edge against API connections and declared output type.
for l in links:
 _,src,os,dst,ins,typ=l;assert byid[dst]['inputs'][ins]['link']==l[0];assert byid[src]['outputs'][os]['type']==typ
assert all('Bench' not in v['class_type'] and 'Henge' not in v['class_type'] for v in g.values())
assert not any(v['class_type']=='MiniMaxH3AddGuide' for v in g.values())
(R/('tara-native-auto-prompt.api.json' if args.auto_prompt else 'tara-native-10500-v2.api.json')).write_text(json.dumps(g,indent=2))
(R/('tara-native-auto-prompt.comfy.json' if args.auto_prompt else 'tara-native-10500-v2.comfy.json')).write_text(json.dumps(visual,indent=2))
print('Saved',len(nodes),'public nodes;',len(links),'checked links. No GPU run.')
