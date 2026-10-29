"""CPU numerical tests for pure H3 windows: no model, weights, API or GPU required."""
import importlib.util,sys,unittest,types
from pathlib import Path
from unittest.mock import ANY,patch
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
path=Path(__file__).resolve().parents[1]/'comfy_nodes/henge/temporal_windows.py'
spec=importlib.util.spec_from_file_location('tested_temporal_windows',path);tw=importlib.util.module_from_spec(spec);sys.modules[spec.name]=tw;spec.loader.exec_module(tw)

class Cond:
 def __init__(self,value):self.cond=value
 def _copy_with(self,value):return Cond(value)

def pack(parts):return torch.cat([p.reshape(p.shape[0],1,-1) for p in parts],dim=-1),[tuple(p.shape) for p in parts]
def unpack(value,shapes):
 out=[];offset=0
 for shape in shapes:
  size=1
  for n in shape[1:]:size*=n
  out.append(value[:,:,offset:offset+size].reshape(shape));offset+=size
 return out
RUNTIME=(types.SimpleNamespace(pack_latents=pack,unpack_latents=unpack),types.SimpleNamespace(CONDConstant=Cond),lambda:None)

class PureWindowTests(unittest.TestCase):
 def setUp(self):
  self.runtime=patch.object(tw,'_runtime',return_value=RUNTIME);self.runtime.start();self.addCleanup(self.runtime.stop)
  layout=patch.object(tw,'_make_layout',side_effect=lambda length,shapes,payload:types.SimpleNamespace(text_length=length,video_t=shapes[0][2],audio_t=shapes[1][-1]));layout.start();self.addCleanup(layout.stop)
 def fixture(self,frames=328):
  vt=tw.latent_rows(frames);at=round(frames*40/24)
  v=torch.arange(24*vt*2*2,dtype=torch.float32).reshape(1,24,vt,2,2)/1000
  a=torch.arange(32*2*at,dtype=torch.float32).reshape(1,32,2,at)/2000
  x,shapes=pack([v,a]);payload={'keyframes':[{'resolved_frame_index':0,'latent':v.clone()}],'refs':[{'kind':'image','latent':v[:,:,:1].clone(),'latent_h':2,'latent_w':2}],'layout':object(),'seed':42,'audio_scale':1.}
  entry={'model_conds':{'latent_shapes':Cond(shapes),'minimax_payload':Cond(payload),'c_crossattn':Cond(torch.ones(1,4,8))}}
  return v,a,x,shapes,entry
 def test_causal_grid_and_all_video_audio_rows_covered(self):
  for frames in (5,22,39,107,124,243,328,362,719):
   for size,overlap in ((22,5),(107,22),(124,39)):
    vt=tw.latent_rows(frames);at=round(frames*40/24);windows=tw.plan_windows(vt,at,size,overlap);vc=torch.zeros(vt);ac=torch.zeros(at)
    for w in windows:
     self.assertEqual(w.video_start%5,0);self.assertEqual((w.video_end-w.video_start)%5,2)
     self.assertLessEqual(w.video_end-w.video_start,tw.latent_rows(size))
     vc[w.video_start:w.video_end]+=1;ac[w.audio_start:w.audio_end]+=1
    self.assertTrue(bool((vc>0).all()));self.assertTrue(bool((ac>0).all()));self.assertEqual(windows[-1].audio_end,at)
 def test_invalid_grids_and_audio_mismatch_rejected(self):
  for size,overlap in ((107,107),(108,22),(107,0),(22,22),(True,5)):
   with self.subTest(size=size,overlap=overlap),self.assertRaises(ValueError):tw.validate_window(size,overlap)
  with self.assertRaises(ValueError):tw.plan_windows(32,5)
  with self.assertRaises(ValueError):tw.plan_windows(31,179)
 def test_single_window_is_full_prediction(self):
  v,a,x,shapes,c=self.fixture(22)
  got=tw.PureH3Windows().execute(lambda m,cs,z,t,o:[z*2+.125],None,[[c]],x,torch.tensor(1.),{})[0]
  torch.testing.assert_close(got,x*2+.125,rtol=1e-6,atol=1e-6)
 def test_overlap_fusion_preserves_pointwise_predictions_both_cfg_branches(self):
  v,a,x,shapes,c=self.fixture();calls=[];options={'transformer_options':{'unchanged':True}}
  def prediction(m,conds,z,t,o):
   calls.append((z.shape,t.item(),o['transformer_options']['henge_temporal_window']))
   o['transformer_options']['temporary_layout']='local'
   self.assertTrue(all(e['model_conds']['latent_shapes'].cond[0][2]<=32 for group in conds if group for e in group))
   self.assertTrue(all(e['model_conds']['minimax_payload'].cond['layout'].video_t==e['model_conds']['latent_shapes'].cond[0][2] for group in conds if group for e in group))
   return [z*2+3,z*.5-1,torch.zeros_like(z)]
  # Windows do not redraw noise, change sigma, or perform a sequential warmup.
  with patch.object(torch,'randn',side_effect=AssertionError('unexpected noise draw')):
   outputs=tw.PureH3Windows().execute(prediction,None,[[c],[c],None],x,torch.tensor(.7),options)
  torch.testing.assert_close(outputs[0],x*2+3,rtol=1e-6,atol=1e-5);torch.testing.assert_close(outputs[1],x*.5-1,rtol=1e-6,atol=1e-5)
  self.assertEqual(len(calls),4);self.assertTrue(all(abs(item[1]-.7)<1e-6 for item in calls));self.assertNotIn('temporary_layout',options['transformer_options']);self.assertEqual(outputs[2].shape,x.shape)
 def test_add_guide_and_tara_reference_crop_on_the_same_window_clock(self):
  v,a,x,shapes,c=self.fixture();image=c['model_conds']['minimax_payload'].cond['refs'][0]
  original=c['model_conds']['minimax_payload'].cond
  native={'kind':'video_audio','latent':v,'latent_t':v.shape[2],'latent_h':2,'latent_w':2,'audio_latent':a,'ref_audio_t':a.shape[-1]}
  original['refs']=[image,native]
  w=tw.plan_windows(v.shape[2],a.shape[-1])[1];got=tw.crop_payload(original,w,v.shape[2])
  self.assertNotIn('layout',got);self.assertIn('layout',original)
  self.assertEqual(got['keyframes'][0]['resolved_frame_index'],0)
  torch.testing.assert_close(got['keyframes'][0]['latent'],v[:,:,w.video_start:w.video_end])
  self.assertIs(got['refs'][0]['latent'],image['latent'])
  torch.testing.assert_close(got['refs'][1]['audio_latent'],a[:,:,:,w.audio_start:w.audio_end]);self.assertEqual(got['refs'][1]['latent_t'],32)
  self.assertEqual(original['refs'][1]['latent_t'],97)
 def test_still_anchors_keep_exact_frame_inside_appropriate_window(self):
  v,a,x,shapes,c=self.fixture();anchor={'resolved_frame_index':90,'latent':v[:,:,:1]};windows=tw.plan_windows(v.shape[2],a.shape[-1]);got=tw.crop_keyframes([anchor],windows[1]);self.assertEqual(got[0]['resolved_frame_index'],5)
  self.assertEqual(tw.crop_keyframes([anchor],windows[-1]),[])
 def test_temporal_masks_and_conditioning_are_not_mutated(self):
  v,a,x,shapes,c=self.fixture();v_mask=torch.rand(1,1,v.shape[2],2,2);a_mask=torch.rand(1,1,2,a.shape[-1]);c['model_conds'].update(denoise_mask=Cond(v_mask),audio_denoise_mask=Cond(a_mask));w=tw.plan_windows(v.shape[2],a.shape[-1])[1];sub_shapes=[(1,24,32,2,2),(1,32,2,w.audio_end-w.audio_start)]
  got=tw.PureH3Windows().get_resized_cond([c],x,(w,sub_shapes,v.shape[2]))[0]['model_conds'];torch.testing.assert_close(got['denoise_mask'].cond,v_mask[:,:,w.video_start:w.video_end]);torch.testing.assert_close(got['audio_denoise_mask'].cond,a_mask[:,:,:,w.audio_start:w.audio_end]);self.assertEqual(c['model_conds']['latent_shapes'].cond,shapes)
 def test_short_native_reference_and_controlnet_fail_clearly(self):
  v,a,x,shapes,c=self.fixture();payload=c['model_conds']['minimax_payload'].cond;payload['refs']=[{'kind':'video','latent':v[:,:,:7]}];w=tw.plan_windows(v.shape[2],a.shape[-1])[1]
  with self.assertRaisesRegex(ValueError,'match the target'):tw.crop_payload(payload,w,v.shape[2])
  c['control']=object()
  with self.assertRaisesRegex(ValueError,'ControlNet'):tw.PureH3Windows().get_resized_cond([c],x,(w,shapes,v.shape[2]))
 def test_exceptions_leave_original_metadata_untouched_and_cancellation_propagates(self):
  v,a,x,shapes,c=self.fixture();payload=c['model_conds']['minimax_payload'].cond
  with self.assertRaisesRegex(RuntimeError,'stop'):
   tw.PureH3Windows().execute(lambda *args:(_ for _ in ()).throw(RuntimeError('stop')),None,[[c]],x,torch.tensor(1.),{})
  self.assertEqual(payload['keyframes'][0]['latent'].shape,v.shape)
  with patch.object(tw,'_runtime',return_value=(*RUNTIME[:2],lambda:(_ for _ in ()).throw(InterruptedError('cancel')))),self.assertRaises(InterruptedError):
   tw.PureH3Windows().execute(lambda *args:[],None,[[c]],x,torch.tensor(1.),{})

class PureWindowGraphTests(unittest.TestCase):
 def test_all_modes_route_patched_models_and_refiner_has_its_own_patch(self):
  from workflows import h3_graph
  for profile in ('character','headswap','motion','motion_tara','sharpness'):
   tara=profile=='motion_tara';up={'method':'regenerate','steps':2,'width':1920,'height':1088} if profile=='sharpness' else None
   g=h3_graph('v.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0,conditioning_mode='tara' if tara else 'guide',upscale=up,temporal_windows={'enabled':True,'window_frames':107,'overlap_frames':22})
   self.assertEqual(g['10']['inputs']['model'],['80',0]);self.assertEqual(g['13']['inputs']['model'],['80',0]);self.assertEqual(g['80']['inputs']['model'],['21',0] if tara else ['4',0])
   if up:self.assertEqual(g['81']['inputs']['model'],['74',0]);self.assertEqual(g['34']['inputs']['model'],['81',0])
 def test_disabled_windows_do_not_change_normal_graph(self):
  from workflows import h3_graph
  args=('v.mp4',[],'test',512,288,22,22,'sharpness',42,8,'original',[],'human',0)
  self.assertEqual(h3_graph(*args),h3_graph(*args,temporal_windows={'enabled':False}))
 def test_api_rejects_invalid_controls_and_context_conflicts(self):
  import server
  r={'mode':'sharpness','prompt':'','quality':'1080p','video':{'start_seconds':0,'end_seconds':1},'processing':{'mode':'single'}}
  for options in ({'enabled':True,'window_frames':108},{'enabled':True,'window_frames':22,'overlap_frames':22},{'enabled':'yes'},{'enabled':True,'other':1}):
   with self.subTest(options=options),self.assertRaises(ValueError):server.validate_request(r.copy(),{'temporal_windows':options},[])
  with self.assertRaisesRegex(ValueError,'Causal'):server.validate_request({**r,'processing':{'mode':'causal'}},{'temporal_windows':{'enabled':True}},[])
 def test_pure_windows_allow_single_long_refiner_shot(self):
  import server
  job={'request':{'mode':'sharpness','video':{'start_seconds':0,'end_seconds':13.458333},'processing':{'mode':'single','requested_seconds_per_shot':15,'context_frames':22,'cut_mode':'off'}},'options':{'upscale_method':'regenerate','temporal_windows':{'enabled':True}}}
  # 13.5 s in one 328-frame shot is what a 56 GB worker could not hold at 2K: shots stay within FULL_REFINE_CHUNK.
  shots,_=server.plan_shots(job);self.assertEqual(len(shots),2);self.assertTrue(all(s['length']<=server.FULL_REFINE_CHUNK for s in shots))

 def test_pure_windows_respect_each_detected_camera_cut(self):
  import server
  job={'request':{'mode':'sharpness','video':{'start_seconds':0,'end_seconds':13.458333},'processing':{'mode':'single','requested_seconds_per_shot':15,'context_frames':22,'cut_mode':'fit'}},'options':{'upscale_method':'regenerate','temporal_windows':{'enabled':True}}}
  with patch.object(server,'camera_cuts',return_value=[95,250]):shots,_=server.plan_shots(job)
  self.assertEqual(server.cut_mode(job),'every')
  self.assertEqual([s['start'] for s in shots],[0,95,250]);self.assertTrue(all(s['overlap']==0 for s in shots))
  self.assertEqual(sum(s['frames'] for s in shots),323)


class FullRefinerTests(unittest.TestCase):
 def test_full_refiner_runs_only_stage_two_on_assembled_frames(self):
  from workflows import full_refiner_graph,REGENERATE
  g=full_refiner_graph('henge/test/first_pass_full.mp4','henge/test/source.mp4','scene',1376,768,2560,1440,362,360,42,temporal_windows={'enabled':True,'scope':'refiner_full'})
  self.assertNotIn('14',g);self.assertNotIn('9',g);self.assertNotIn('80',g)
  self.assertEqual(sum(n['class_type']=='SamplerCustomAdvanced' for n in g.values()),1)
  self.assertEqual(g['31']['inputs']['samples'],['94',0]);self.assertEqual(g['94']['inputs']['video_latent'],['91',0])
  self.assertEqual(g['90']['inputs']['video'],'henge/test/first_pass_full.mp4')
  self.assertEqual(g['75']['inputs']['video'],'henge/test/source.mp4')
  self.assertEqual(g['81']['inputs']['model'],['74',0]);self.assertEqual(g['34']['inputs']['model'],['81',0])
  self.assertEqual(g['70']['inputs']['unet_name'],REGENERATE['base'])
  self.assertEqual(g['17']['inputs']['trim_frames'],360)
  self.assertEqual(g['33']['inputs']['sigmas'],'0.7, 0.494118, 0')
  for n in g.values():
   for value in n['inputs'].values():
    if isinstance(value,list) and len(value)==2 and isinstance(value[0],str):self.assertIn(value[0],g)
 def test_full_mode_retains_segment_cap_and_normal_cut_behavior(self):
  import server
  job={'request':{'mode':'sharpness','video':{'start_seconds':0,'end_seconds':13.458333},'processing':{'mode':'single','requested_seconds_per_shot':15,'context_frames':22,'cut_mode':'fit'}},'options':{'upscale_method':'regenerate','temporal_windows':{'enabled':True,'scope':'refiner_full'}}}
  self.assertEqual(server.cut_mode(job),'fit')
  shots,_=server.plan_shots(job);self.assertGreater(len(shots),1);self.assertTrue(all(s['length']<=107 for s in shots));self.assertTrue(any(s['overlap'] for s in shots))
  self.assertEqual(sum(s['frames']-s['overlap'] for s in shots),323)
 def test_scope_guard_ignores_disabled_setting(self):
  import server
  self.assertTrue(server.full_refiner_enabled({'temporal_windows':{'enabled':True,'scope':'refiner_full'}}))
  self.assertFalse(server.full_refiner_enabled({'temporal_windows':{'enabled':False,'scope':'refiner_full'}}))
 def test_full_refine_checks_output_duration(self):
  import server,tempfile
  from contextlib import ExitStack
  with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
   root=Path(tmp);inp=root/'input';work=root/'work';work.mkdir();(inp/'henge'/'test').mkdir(parents=True);joined=work/'joined.mp4';joined.write_bytes(b'first pass')
   job={'id':'test','options':{'temporal_windows':{'enabled':True,'scope':'refiner_full'}},'request':{'video':{'start_seconds':2,'end_seconds':17}},'assets':{'video':'source.mp4'},'plan':{'prompt':'scene'}}
   stack.enter_context(patch.object(server,'INPUT',inp));stack.enter_context(patch.object(server,'job_path',return_value=work));stack.enter_context(patch.object(server,'probe',return_value={'width':1376,'height':768}));stack.enter_context(patch.object(server,'run'));stack.enter_context(patch.object(server,'save'))
   execute=stack.enter_context(patch.object(server,'execute_graph',return_value={'17':{'videos':[{'filename':'result.mp4'}]}}));stack.enter_context(patch.object(server.FILES,'download',return_value=work/'refined_full.mp4'))
   stack.enter_context(patch.object(server,'frame_count',side_effect=[200,200]))
   result=server.refine_full_video(job,joined,2560,1440)
   self.assertEqual(result,work/'refined_full.mp4');self.assertEqual(execute.call_args.args[2],'h3_refine_full')
   first_path=execute.call_args.args[1]['90']['inputs']['video']
   joined.write_bytes(b'changed first pass after redo')
   with patch.object(server,'frame_count',side_effect=[200,200]):server.refine_full_video(job,joined,2560,1440)
   self.assertNotEqual(first_path,execute.call_args.args[1]['90']['inputs']['video'])
   with patch.object(server,'frame_count',side_effect=[200,199]),self.assertRaisesRegex(ValueError,'frame count'):server.refine_full_video(job,joined,2560,1440)

 def test_long_full_refine_is_split_at_segment_joins(self):
  import server
  # The 22 s Character Swap that killed a 56 GB worker: 530 frames in five first-pass segments.
  chunks=server.refine_chunks(530,[144,214,317,418])
  self.assertEqual(chunks,[(0,0,214),(214,214,418),(418,418,530)])
  self.assertTrue(all(e-a<=server.FULL_REFINE_CHUNK for a,_,e in chunks))
  # One segment longer than a chunk: split inside it, re-reading context frames that are dropped afterwards.
  self.assertEqual(server.refine_chunks(500,[]),[(0,0,243),(221,243,464),(442,464,500)])
 def test_chunked_full_refine_keeps_every_frame_in_order(self):
  import server,tempfile,subprocess,shutil
  from contextlib import ExitStack
  with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
   root=Path(tmp);inp=root/'input';work=root/'work';work.mkdir();(inp/'henge'/'test').mkdir(parents=True)
   source=inp/'source.mp4';joined=work/'joined.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=128x72:rate=24:duration=3','-c:v','libx264','-crf','10','-pix_fmt','yuv420p','-y',str(source)],check=True);shutil.copyfile(source,joined)
   job={'id':'test','options':{'temporal_windows':{'enabled':True,'scope':'refiner_full'}},'request':{'video':{'start_seconds':0,'end_seconds':3}},'assets':{'video':'source.mp4'},'plan':{'prompt':'scene'}}
   staged=[]
   def execute(job,graph,stage):staged.append((stage,graph['90']['inputs']['video'],graph['90']['inputs']['length']));return {'17':{'videos':[{'filename':graph['90']['inputs']['video']}]}}
   def download(item,dest):shutil.copyfile(inp/item['filename'],dest);return dest  # identity "refinement"
   for name,value in [('INPUT',inp),('FULL_REFINE_CHUNK',30),('FULL_REFINE_CONTEXT',5)]:stack.enter_context(patch.object(server,name,value))
   stack.enter_context(patch.object(server,'job_path',return_value=work));stack.enter_context(patch.object(server,'save'))
   stack.enter_context(patch.object(server,'execute_graph',side_effect=execute));stack.enter_context(patch.object(server.FILES,'download',side_effect=download))
   pieces=[]
   for i,(a,b) in enumerate([(0,20),(20,72)]):pieces.append(server.trim_frames(source,work/f'piece_{i:03d}.mp4',a,b))
   refined=server.refine_full_video(job,joined,128,72,pieces)
   self.assertEqual(server.frame_count(refined),72)
   self.assertEqual([x[0] for x in staged],['h3_refine_full_01','h3_refine_full_02','h3_refine_full_03'])
   self.assertEqual([x[2] for x in staged],[server.grid_frames(n) for n in (20,30,27)])
   psnr=subprocess.run(['ffmpeg','-i',str(refined),'-i',str(joined),'-lavfi','psnr','-f','null','-'],capture_output=True,text=True).stderr
   self.assertGreater(float(psnr.split('average:')[1].split()[0]),35)
   # Retry resumes: refined chunks are reused, nothing runs again.
   staged.clear();server.refine_full_video(job,joined,128,72,pieces);self.assertEqual(staged,[])
 def test_api_accepts_full_scope_and_rejects_incompatible_modes_and_duration(self):
  import server,copy
  base={'mode':'sharpness','prompt':'','quality':'1440p','video':{'start_seconds':0,'end_seconds':15}}
  options={'upscale_method':'regenerate','temporal_windows':{'enabled':True,'scope':'refiner_full'}}
  server.validate_request(copy.deepcopy(base),copy.deepcopy(options),[])
  for request,settings in (({**base,'quality':'720p'},options),(base,{**options,'upscale_method':'h3'}),({**base,'video':{'start_seconds':0,'end_seconds':151}},options),(base,{**options,'temporal_windows':{'enabled':True,'scope':'unknown'}})):
   with self.subTest(request=request,settings=settings),self.assertRaises(ValueError):server.validate_request(copy.deepcopy(request),copy.deepcopy(settings),[])
 def test_generation_defers_upscale_and_windows_until_after_segments(self):
  import server,tempfile
  from contextlib import ExitStack
  with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
   root=Path(tmp);inp=root/'input';work=root/'work';work.mkdir();(inp/'henge'/'test').mkdir(parents=True)
   job={'id':'test','status':'running','options':{'profile':'sharpness','upscale_method':'regenerate','temporal_windows':{'enabled':True,'scope':'refiner_full'}},'request':{'mode':'sharpness','quality':'1440p','processing':{},'video':{'start_seconds':0,'end_seconds':1}},'assets':{'video':'source.mp4','pictures':{}},'video_info':{'width':1920,'height':1080,'audio':True},'plan':{'adapt_reference':False,'representation':'original','source_kind':'human','prompt':'LMS','regenerate_prompt':'scene'}}
   def save(record,**changes):record.update(changes)
   def run(args):Path(args[-1]).write_bytes(b'video')
   def download(item,dest):dest.write_bytes(b'video');return dest
   for key,value in [('INPUT',inp)]:stack.enter_context(patch.object(server,key,value))
   for name,kw in [('job_path',{'return_value':work}),('save',{'side_effect':save}),('load',{'return_value':job}),('run',{'side_effect':run}),('plan_shots',{'return_value':([{'start':0,'frames':24,'overlap':0,'length':39}],22)}),('comfy_info',{'return_value':{'HengeH3PureWindows':{}}}),('regenerate_requirements',{'return_value':{'available':True}}),('shot_audio',{}),('frame_count',{'return_value':24})]:stack.enter_context(patch.object(server,name,**kw))
   execute=stack.enter_context(patch.object(server,'execute_graph',return_value={'17':{'videos':[{'filename':'result.mp4'}]}}));finalize=stack.enter_context(patch.object(server,'finalize'));stack.enter_context(patch.object(server.FILES,'download',side_effect=download))
   server.generate(job)
   graph=execute.call_args.args[1]
   self.assertNotIn('70',graph);self.assertNotIn('80',graph);self.assertNotIn('81',graph)
   self.assertEqual(graph['7']['inputs']['height'],768);self.assertEqual(graph['17']['inputs']['images'],['16',0])
   self.assertEqual(finalize.call_args.args[-2:],(2560,1440))
 def test_finalization_refines_once_and_keeps_segment_audio_and_guides(self):
  import server,tempfile
  from contextlib import ExitStack
  for enabled in (False,True):
   with self.subTest(enabled=enabled),tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
    work=Path(tmp);piece=work/'piece_000.mp4';guide=work/'guide_000.mp4';(work/'audio_000.wav').write_bytes(b'audio')
    job={'id':'test','options':{'temporal_windows':{'enabled':enabled,'scope':'refiner_full'}},'request':{'video':{'start_seconds':0,'end_seconds':1},'processing':{},'output_audio':{'generate':True}},'assets':{'video':'source.mp4'},'video_info':{'audio':False},'plan':{'representation':'original'}}
    stack.enter_context(patch.object(server,'job_path',return_value=work));stack.enter_context(patch.object(server,'save'));run=stack.enter_context(patch.object(server,'run'));refine=stack.enter_context(patch.object(server,'refine_full_video',return_value=work/'refined_full.mp4'))
    server.finalize(job,[piece],[guide],2560,1440)
    self.assertEqual(refine.call_count,int(enabled))
    if enabled:refine.assert_called_once_with(job,work/'joined.mp4',2560,1440,ANY)
    mux=next(c.args[0] for c in run.call_args_list if str(work/'result.mp4')==c.args[0][-1])
    self.assertEqual(mux[mux.index('-i')+1],str(work/('refined_full.mp4' if enabled else 'joined.mp4')))
    self.assertIn(str(work/'soundtrack.wav'),mux);self.assertEqual((work/'audio_concat.txt').read_text(),"file 'audio_000.wav'\n")
    self.assertEqual((work/'guide_concat.txt').read_text(),"file 'guide_000.mp4'\n")

 def test_download_returns_latest_render_when_stage_two_fails(self):
  import server,tempfile,json,os
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp);stage1=work/'h3_segment_000.api.json';stage2=work/'h3_refine_full.api.json'
   stage1.write_text(json.dumps({'first':'pass'}));os.utime(stage1,ns=(1,1))
   with patch.object(server,'load',return_value={}),patch.object(server,'job_path',return_value=work):
    self.assertEqual(json.loads(server.workflow('test',stage='render_latest').body),{'first':'pass'})
    stage2.write_text(json.dumps({'second':'pass'}))
    self.assertEqual(json.loads(server.workflow('test',stage='render_latest').body),{'second':'pass'})
