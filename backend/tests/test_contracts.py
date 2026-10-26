import sys,unittest,copy,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflows import split_frames,h3_graph,fibo_graph,split_on_cuts
from server import validate_request,validate_plan,training_busy
from unittest.mock import patch,Mock
def structured_prompt(description='Transfer the guide performance.'):
 return 'motion_transfer: subject_definitions: <Subject 1> uses <Picture 1>. summary: [reference generation] '+description+' retention_analysis: <Subject 1>: fully_preserved - stable identity. detailed_description: [Shot 1] Transfer the guide timing and gestures. overall_soundscape: N/A non_diegetic_music: N/A'

class WorkflowContracts(unittest.TestCase):
 def test_visible_generation_reference_resolves_to_full_id(self):
  import server
  with tempfile.TemporaryDirectory() as d,patch.object(server,'JOBS',Path(d)):
   jid='a1b2c3d4'+'0'*24;(Path(d)/jid).mkdir()
   self.assertEqual(server.resolve_job_id('#a1b2c3d4'),jid)
   self.assertEqual(server.resolve_job_id(jid),jid)
   (Path(d)/('a1b2c3d4'+'1'*24)).mkdir()
   with self.assertRaises(Exception):server.resolve_job_id('a1b2c3d4')
 def test_numeric_string_picture_slots_are_normalized(self):
  request=self.request();plan=self.plan()
  plan['picture_roles']=[{'slot':'1','role':'identity','description':'Reference identity'}]
  normalized=validate_plan(plan,[1],{},request)
  self.assertEqual(normalized['picture_roles'][0]['slot'],1)
 def test_training_gate_recognizes_tara_runtime(self):
  process=Mock();process.read_bytes.return_value=b'python\0-u\0/tmp/h3-tara-motion-runtime/run.py\0config.yaml\0'
  with patch('server.Path.glob',return_value=[process]):self.assertTrue(training_busy())
 def test_training_gate_ignores_shell_text(self):
  process=Mock();process.read_bytes.return_value=b'bash\0-c\0echo /tmp/h3-tara-motion-runtime/run.py\0'
  with patch('server.Path.glob',return_value=[process]):self.assertFalse(training_busy())
 def request(self):return {'mode':'motion','prompt':'motion_transfer: <Picture 1> follows <Video 1>.','quality':'480p','video':{'start_seconds':0,'end_seconds':4.5},'processing':{'requested_seconds_per_shot':4.5,'context_frames':22},'subject_guidance':{'representation':'3d','bindings':[]}}
 def plan(self):return {'source_kind':'human','target_kind':'animal','use_fibo':False,'fibo_instruction':'Replace <image_1> performer with <image_2>.','fibo_picture_slots':[1],'picture_roles':[{'slot':1,'role':'identity'}],'prompt':structured_prompt(),'warnings':[]}
 def test_raw_prompt_preserves_exact_user_text(self):
  r=self.request();r['prompt']='  Troque pelo <Picture 1> — anime.\nNão mude o ritmo!  '
  p=self.plan();p['prompt']='Rewritten <Picture 99>'
  self.assertEqual(validate_plan(p,[1],{'enhance_prompt':False},r)['prompt'],r['prompt'])
 def test_enhancement_uses_vlm_prompt(self):
  r=self.request();p=self.plan();p['prompt']=structured_prompt('Enhanced <Picture 1>')
  self.assertEqual(validate_plan(p,[1],{'enhance_prompt':True},r)['prompt'],p['prompt'])
 def test_overlap_covers_every_output_frame_once(self):
  for n in [5,22,107,108,241,720,3600]:
   shots=split_frames(n,107,22);self.assertEqual(sum(s['frames']-s['overlap'] for s in shots),n)
   self.assertEqual(shots[0]['start'],0)
   for prev,cur in zip(shots,shots[1:]):self.assertEqual(cur['start']+cur['overlap'],prev['start']+prev['frames'])
   self.assertTrue(all(s['length']%17==5 and s['length']>=s['frames'] for s in shots))
 def test_camera_cuts_reset_context_without_dropping_frames(self):
  shots=split_on_cuts(720,107,22,[95,250,400]);self.assertEqual(sum(s['frames']-s['overlap'] for s in shots),720)
  self.assertEqual([s['start'] for s in shots if s['reset_context']],[0,95,250,400]);self.assertTrue(all(s['overlap']==0 for s in shots if s['reset_context']))
 def test_cuts_do_not_shorten_the_requested_shot_length(self):
  shots=split_on_cuts(1190,345,22,list(range(72,1190,72)));self.assertEqual(sum(s['frames']-s['overlap'] for s in shots),1190)
  self.assertEqual(len(shots),4);self.assertTrue(all(s['frames']<=345 and s['reset_context'] and s['overlap']==0 for s in shots))
 def test_cut_modes(self):
  import server
  job={'request':{'mode':'motion','video':{'start_seconds':2,'end_seconds':51.6},'processing':{'mode':'context_window','requested_seconds_per_shot':15,'context_frames':22}},'options':{}}
  cuts=list(range(72,1190,72))
  with patch.object(server,'camera_cuts',return_value=cuts):
   fit=server.plan_shots(job)[0];every=server.plan_shots({**job,'request':{**job['request'],'processing':{**job['request']['processing'],'cut_mode':'every'}}})[0];off=server.plan_shots({**job,'options':{'detect_cuts':False}})[0]
   preview=server.shot_preview(job)
  self.assertEqual((len(fit),len(every)),(4,len(cuts)+1));self.assertTrue(all(s['frames']<=345 for s in off+fit))
  self.assertEqual(preview['cut_mode'],'fit');self.assertEqual(preview['shots'][0]['start'],2);self.assertTrue(preview['shots'][1]['after_cut'])
 def test_fibo_reference_is_reused(self):
  import server,shutil as sh
  from PIL import Image
  def job(jid,options={}):
   (server.INPUT/'henge'/jid).mkdir(parents=True,exist_ok=True);server.job_path(jid).mkdir(parents=True,exist_ok=True)
   pic=server.INPUT/'henge'/jid/'cat.png';Image.new('RGB',(8,8),'gray').save(pic);(server.INPUT/'henge'/jid/'guide.mp4').write_bytes(b'v')
   j={'id':jid,'created':0,'status':'awaiting_approval','request':{'mode':'motion','video':{'start_seconds':0}},'options':{'seed':1,**options},'assets':{'video':f'henge/{jid}/guide.mp4','pictures':{'1':str(pic.relative_to(server.INPUT))}},
      'plan':{'use_fibo':True,'fibo_picture_slots':[1],'source_kind':'human','target_kind':'animal','fibo_instruction':'x','picture_roles':[{'slot':1,'description':'A cat.'}]}}
   server.save(j);return j
  def fake(outputs,dest):Image.new('RGB',(8,8),'white').save(dest);return dest
  with patch.object(server,'execute_graph',return_value={}) as run,patch.object(server,'image_from_output',side_effect=fake),patch.object(server,'run'):
   server.fibo_prepare(job('1'*32),job('1'*32));server.fibo_prepare(job('2'*32),job('2'*32));self.assertEqual(run.call_count,1)
   server.fibo_prepare(job('3'*32),job('3'*32),regenerate=True);self.assertEqual(run.call_count,2)
   edited=job('4'*32,{'fibo_instruction':'A cat knight, front and back.'});server.fibo_prepare(edited,edited);self.assertEqual(run.call_count,3)
   graph=run.call_args[0][1];self.assertEqual(graph['5']['inputs']['prompt'],'A cat knight, front and back.')
   self.assertTrue(graph['4']['inputs']['image'].endswith('cat.png'));self.assertTrue(graph['22']['inputs']['image'].endswith('fibo_source.png'))
  self.assertTrue(server.fibo_state(server.load('2'*32))['ready'])
 def test_character_swap_animal_gets_one_fibo_figure(self):
  import server
  from edit_modes import character_figure_instruction
  text=character_figure_instruction(2);self.assertIn('Exactly one figure',text);self.assertIn('the person in <image_3>',text)
  jid='5'*32;(server.INPUT/'henge'/jid).mkdir(parents=True,exist_ok=True);server.job_path(jid).mkdir(parents=True,exist_ok=True)
  pic=server.INPUT/'henge'/jid/'cat.png';__import__('PIL.Image').Image.new('RGB',(8,8),'gray').save(pic)
  (server.INPUT/'henge'/jid/'guide.mp4').write_bytes(b'v')
  job={'id':jid,'created':0,'status':'planning','request':{'mode':'swap','prompt':'','video':{'start_seconds':0}},'options':{},'assets':{'video':f'henge/{jid}/guide.mp4','pictures':{'1':str(pic.relative_to(server.INPUT))}}}
  server.save(job)
  answers={'vlm_picture_1':'Male, orange tabby cat, white paws','vlm_species':'Animal'}
  def fake_graph(job,graph,stage):return {'4':{'text':[answers[stage]]}}
  with patch.object(server,'prepare_evidence',return_value=([(1,pic)],pic,{})),patch.object(server,'fibo_available',return_value=True),patch.object(server,'execute_graph',side_effect=fake_graph):
   server.planning(job)
  plan=server.load(jid)['plan'];self.assertTrue(plan['use_fibo'] and plan['preparation_recommended']);self.assertEqual(plan['target_kind'],'animal')
  req=server.fibo_request(server.load(jid));self.assertTrue(req['figure']);self.assertIn('Exactly one figure',req['instruction'])
 def test_worker_drops_shot_overlap(self):
  g=h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,8,'original',[],'human',0,skip_frames=22)
  self.assertEqual(g['17']['inputs']['skip_frames'],22);self.assertEqual(g['18']['inputs']['skip_frames'],22)
  self.assertNotIn('skip_frames',h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,8,'original',[],'human',0)['17']['inputs'])
 def test_color_marks_reach_the_prompt(self):
  import server
  r={'subject_guidance':{'representation':'2d','mark_opacity':.35,'bindings':[{'color':'green','picture_slots':[1]},{'color':'purple','picture_slots':[2,3]}]}}
  text=server.marks_sentence(r,'2d')
  self.assertIn('tinted green in <Video 1> becomes the character from <Picture 1>',text);self.assertIn('<Picture 2> and <Picture 3>',text)
  self.assertEqual(server.marks_sentence(r,'original'),'');self.assertIn('colored green',server.marks_sentence(r,'3d'))
  from workflows import marks_preview_graph
  g=marks_preview_graph('c.mp4',384,224,107,107,[],'human',0,[],'out.mp4');self.assertEqual(g['2']['inputs']['representation'],'2d');self.assertIn('"mark_opacity": 1',g['2']['inputs']['mask_settings'])
  with self.assertRaises(ValueError):validate_request({**self.request(),'subject_guidance':{'representation':'2d','mark_opacity':0,'bindings':[]}},{},[1])
 def test_mask_in_every_mode_but_sharpness(self):
  anchor={'x':.5,'y':.5,'time_seconds':0,'frame_width':64,'frame_height':64}
  for mode in ('swap','motion','headswap'):
   r={**self.request(),'mode':mode,'subject_guidance':{'representation':'mask','bindings':[{'color':'green','picture_slots':[1],'anchors':[anchor]}]}}
   if mode=='headswap':r['prompt']=''
   validate_request(r,{},[1])
 def test_mask_guide_shows_the_region(self):
  g=h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,8,'mask',[],'human',0,skip_frames=22)
  self.assertEqual(g['18']['inputs']['images'],['26',0]);self.assertEqual(g['26']['class_type'],'HengeMaskPreview');self.assertEqual(g['18']['inputs']['skip_frames'],22)
  self.assertEqual(h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,8,'2d',[],'human',0)['18']['inputs']['images'],['8',0])
 def test_multi_person_swap_template(self):
  from edit_modes import multi_swap_prompt
  t=multi_swap_prompt([('red',[1],'Male, lean build, curly dark hair'),('blue',[2,3],'Female, white trench coat')],'2d')
  self.assertTrue(t.startswith('body_swap: subject_definitions: <Subject 1> is the character shown in <Picture 1>: Male, lean build, curly dark hair.'))
  self.assertIn('<Subject 2> is the character shown in <Picture 2> and <Picture 3>',t);self.assertIn('define the blue-marked replacement',t)
  self.assertIn('Replace the red-tinted person with <Subject 1> and the blue-tinted person with <Subject 2>',t);self.assertIn('  summary: ',t)
 def test_planning_two_marked_people_uses_the_template(self):
  import server
  jid='6'*32;(server.INPUT/'henge'/jid).mkdir(parents=True,exist_ok=True);server.job_path(jid).mkdir(parents=True,exist_ok=True)
  pics=[]
  for i in (1,2):
   p=server.INPUT/'henge'/jid/f'p{i}.png';__import__('PIL.Image').Image.new('RGB',(8,8),'gray').save(p);pics.append((i,p))
  a={'x':.3,'y':.5,'time_seconds':0,'frame_width':8,'frame_height':8}
  marks=[{'id':'r','label':'S1','color':'red','picture_slots':[1],'anchors':[a]},{'id':'b','label':'S2','color':'blue','picture_slots':[2],'anchors':[a]}]
  job={'id':jid,'created':0,'status':'planning','request':{'mode':'swap','prompt':'swap them','video':{'start_seconds':0},'subject_guidance':{'representation':'2d','bindings':marks}},'options':{'auto_approve':True},'assets':{'pictures':{'1':'x','2':'y'}}}
  server.save(job)
  texts={'vlm_picture_1':'Male, curly hair','vlm_picture_2':'Female, red coat','vlm_guide':'[]'}
  with patch.object(server,'prepare_evidence',return_value=(pics,pics[0][1],{})),patch.object(server,'execute_graph',side_effect=lambda j,g,stage:{'4':{'text':[texts[stage]]}}):
   server.planning(job)
  plan=server.load(jid)['plan']
  self.assertIn('<Subject 1> is the character shown in <Picture 1>: Male, curly hair',plan['prompt']);self.assertIn('blue-marked',plan['prompt'])
  self.assertNotIn('Color markers',plan['prompt']);self.assertEqual(plan['representation'],'2d')
 def test_marks_go_inside_subject_definitions(self):
  import server
  r={'subject_guidance':{'representation':'2d','bindings':[{'color':'red','picture_slots':[1]}]}}
  out=server.add_marks('motion_transfer:\nsubject_definitions:\nA.\n\nsummary:\nB.',r,'2d')
  self.assertLess(out.index('Color markers'),out.index('summary:'))
 def test_timecodes_are_removed(self):
  import server
  out=server.strip_timecodes('[Shot 1] From 00:05 to 00:10, they fight. Around 2.0 seconds, the light changes. He waves at 3 people.\nsummary:\nok')
  self.assertEqual(out,'[Shot 1] They fight. The light changes. He waves at 3 people.\nsummary:\nok')
 def test_assistant_graphs_build(self):
  from workflows import find_people_graph,subject_looks_graph
  g=find_people_graph('henge/x/frame.png','animal');self.assertEqual(g['2']['inputs']['kind'],'animal');self.assertEqual(g['2']['class_type'],'HengeFindPeople')
  g=subject_looks_graph([('henge/x/a.png','id1',.3,.5)]);self.assertEqual(g['2']['class_type'],'HengeSubjectLook')
 def test_tara_refuses_color_marks(self):
  a={'x':.5,'y':.5,'time_seconds':0,'frame_width':64,'frame_height':64}
  b=[{'color':'green','picture_slots':[1],'anchors':[a]}]
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'motion','subject_guidance':{'representation':'2d','bindings':b}},{'conditioning_mode':'tara'},[1])
  validate_request({**self.request(),'mode':'motion','subject_guidance':{'representation':'mask','bindings':b}},{'conditioning_mode':'tara'},[1])
 def test_likeness_filter(self):
  import server,os
  jid='7'*32;server.job_path(jid).mkdir(parents=True,exist_ok=True);job={'id':jid,'created':0,'status':'planning','request':{'mode':'swap'}};server.save(job)
  answers={1:'{"public_figure": true}',2:'{"public_figure": false}'}
  ask=lambda instruction,image,stage,tokens:answers[int(stage.rsplit('_',1)[1])]
  with patch.dict(os.environ,{'HENGE_LIKENESS_FILTER':'off'}):server.likeness_check(job,[(1,'a'),(2,'b')],ask);self.assertNotIn('likeness_warning',server.load(jid))
  with patch.dict(os.environ,{'HENGE_LIKENESS_FILTER':'warn'}):server.likeness_check(job,[(1,'a'),(2,'b')],ask)
  self.assertIn('Picture 1 looks like a real public figure',server.load(jid)['likeness_warning']);self.assertNotIn('Picture 2',server.load(jid)['likeness_warning'])
  with patch.dict(os.environ,{'HENGE_LIKENESS_FILTER':'block'}):
   with self.assertRaises(ValueError):server.likeness_check(job,[(1,'a')],ask)
 def test_processing_time_counts_running_only(self):
  import server
  jid='8'*32;server.job_path(jid).mkdir(parents=True,exist_ok=True);job={'id':jid,'created':0,'status':'queued_plan'}
  t=[100.]
  with patch.object(server.time,'time',side_effect=lambda:t[0]):
   server.save(job);t[0]=110;server.save(job,status='running');t[0]=130;server.save(job,status='awaiting_approval')
   t[0]=500;server.save(job,status='running');t[0]=560;server.save(job,status='completed')
  self.assertEqual(server.load(jid)['run_seconds'],80.0);self.assertNotIn('run_started',server.load(jid))
 def test_sharpness_ignores_leftover_marks(self):
  a={'x':.5,'y':.5,'time_seconds':0,'frame_width':64,'frame_height':64}
  validate_request({**self.request(),'mode':'sharpness','prompt':'','subject_guidance':{'representation':'2d','bindings':[{'color':'green','picture_slots':[1],'anchors':[a]}]}},{},[])
 def test_close_cuts_do_not_create_tiny_shots(self):
  shots=split_on_cuts(233,107,22,[3,40,52,60,140,225]);self.assertEqual(sum(s['frames']-s['overlap'] for s in shots),233)
  self.assertEqual([s['start'] for s in shots if s['reset_context']],[0,40,140]);self.assertTrue(all(s['frames']>=24 for s in shots))
 def test_missing_native_reference_slot_is_rejected(self):
  with self.assertRaises(ValueError):validate_request(self.request(),{},[1,3])
 def test_invented_reference_is_rejected(self):
  r=self.request();r['prompt']='Use <Picture 2>'
  with self.assertRaises(ValueError):validate_request(r,{},[1])
 def test_cross_species_turns_on_fibo(self):self.assertTrue(validate_plan(self.plan(),[1],{},self.request())['use_fibo'])
 def test_human_to_human_does_not_prepare_for_clothing_or_hair(self):
  p=self.plan();p.update(source_kind='human',target_kind='human',use_fibo=True)
  out=validate_plan(p,[1],{'fibo':'auto'},self.request())
  self.assertFalse(out['use_fibo']);self.assertFalse(out['preparation_recommended'])
 def test_humanoid_creature_does_not_get_fibo(self):
  plan=self.plan();plan.update(target_kind='other',use_fibo=True)
  out=validate_plan(plan,[1],{},self.request());self.assertFalse(out['use_fibo']);self.assertFalse(out['preparation_recommended'])
 def test_explicit_fibo_off_is_respected(self):self.assertFalse(validate_plan(self.plan(),[1],{'fibo':'off'},self.request())['use_fibo'])
 def test_animal_never_uses_human_body_model(self):
  r=self.request();r['subject_guidance']['bindings']=[{'id':'cat'}];p=self.plan();p.update(source_kind='animal',target_kind='human');self.assertEqual(validate_plan(p,[1],{},r)['representation'],'2d')
 def test_environment_reference_does_not_become_character(self):
  p=self.plan();p['picture_roles']=[{'slot':1,'role':'identity'},{'slot':2,'role':'environment'}];p['fibo_picture_slots']=[1,2];self.assertEqual(validate_plan(p,[1,2],{},self.request())['picture_roles'][1]['role'],'environment')
 def test_roles_cover_all_input_pictures(self):
  with self.assertRaises(ValueError):validate_plan(self.plan(),[1,2],{},self.request())
 def test_disabled_branches_have_no_loaders(self):
  g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,'motion',42,8,'original',[],'human',0)
  self.assertNotIn('VAELoader',[v['class_type'] for k,v in g.items() if k=='19']);self.assertNotIn('20',g)
  self.assertFalse(any(v['class_type']=='TextEncodeFibo2' for v in g.values()))
 def test_motion_profiles_load_adapter_v2_before_lora(self):
  for profile in ['motion','motion_mix_dyn95']:
   g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0)
   # adapter V2 -> turbo (default dmd8) -> motion LoRA
   self.assertEqual(g['2']['inputs']['lora_name'],'henge/training_adapter_v2.safetensors')
   self.assertEqual(g['25']['inputs'],{'model':['2',0],'lora_name':'henge/dmd_ref2va_8step.safetensors','strength_model':1.})
   self.assertEqual(g['3']['inputs']['model'],['25',0])
   self.assertEqual(h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0,turbo='none')['3']['inputs']['model'],['2',0])
 def test_fixed_recipe_modes_pick_profile_and_picture_count(self):
  for mode,slots,profile in [('headswap',[1],'headswap'),('sharpness',[],'sharpness')]:
   r={**self.request(),'mode':mode,'prompt':''};options={'profile':'motion','conditioning_mode':'tara'}
   validate_request(r,options,slots);self.assertEqual(options['profile'],profile);self.assertEqual(options['conditioning_mode'],'tara')
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'headswap'},{},[1,2])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'sharpness'},{},[1])
  with self.assertRaises(ValueError):validate_request(self.request(),{'profile':'sharpness'},[1])
 def test_fixed_recipe_graphs(self):
  g=h3_graph('v.mp4',['face.png'],'head_swap:',512,288,107,107,'headswap',42,8,'original',[],'human',0)
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/head_swap_v1_0_r32.safetensors');self.assertEqual(g['13']['inputs']['scheduler'],'beta');self.assertFalse(g['9']['inputs']['guide_context'])
 def test_sharpness_upscale_methods(self):
  args=('v.mp4',[],'Enhance.',512,288,107,107,'sharpness',1,8,'original',[],'human',0)
  g=h3_graph(*args,upscale={'method':'h3','model':'h3_upscaler_lms_v0.1.safetensors','steps':1,'denoise':.15})
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/lms_v1_fro_dyn95.safetensors');self.assertEqual(g['30']['class_type'],'HengeH3LatentUpscale')
  self.assertEqual((g['30']['inputs']['width'],g['32']['inputs']['width'],g['16']['inputs']['samples']),(1024,1024,['38',0]));self.assertNotIn('41',g)
  self.assertEqual(g['34']['inputs']['denoise'],.15);self.assertEqual(g['16']['class_type'],'VAEDecodeTiled')
  big=h3_graph('v.mp4',[],'Enhance.',1088,1920,107,107,'sharpness',1,8,'original',[],'human',0,upscale={'method':'h3','model':'m'})
  self.assertEqual(big['41']['class_type'],'HengeH3TiledDiffusion');self.assertEqual(big['36']['inputs']['model'],['41',0])
  n=h3_graph(*args,upscale={'method':'nvidia'})
  self.assertEqual(n['30']['class_type'],'HengeRTXUpscale');self.assertEqual((n['30']['inputs']['width'],n['30']['inputs']['height']),(1024,576));self.assertEqual(n['17']['inputs']['images'],['30',0])
  self.assertNotIn('30',h3_graph(*args))
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'sharpness','quality':'2160p'},{'profile':'sharpness','upscale_method':'ltx'},[])
 def test_first_frame_propagate(self):
  from edit_modes import ffp_prompt
  validate_request({**self.request(),'mode':'motion','prompt':'Add rain to the scene.'},{'profile':'motion_ffp'},[])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'motion','prompt':'Add rain to the scene.'},{'profile':'motion'},[])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'motion','first_frame_slot':2},{'profile':'motion_ffp'},[1])
  validate_request({**self.request(),'mode':'motion','first_frame_slot':1},{'profile':'motion_ffp'},[1])
  self.assertEqual(ffp_prompt('Add rain.'),'vfx_edit: Add rain.');self.assertIn('<Picture 3> is the edited first frame',ffp_prompt('vfx_edit: Add rain.',3))
  g=h3_graph('v.mp4',['f.png'],'vfx_edit: Add rain.',512,288,107,107,'motion_ffp',1,8,'original',[],'human',0)
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/vfx_ffp_solar05_fro_dyn99.safetensors');self.assertEqual(g['2']['inputs']['lora_name'],'henge/dmd_ref2va_8step.safetensors');self.assertFalse(g['9']['inputs']['guide_context'])
 def test_tara_structure_guidance(self):
  g=h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'motion',1,8,'original',[],'human',0,conditioning_mode='tara',structure_cfg=1.5)
  self.assertEqual((g['21']['inputs']['structure_guidance'],g['21']['inputs']['structure_sigma_min']),(1.5,0.))
  self.assertEqual(g['10']['inputs']['cfg'],1.);self.assertNotIn('21',h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'motion',1,8,'original',[],'human',0))
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'motion'},{'structure_cfg':1.5},[1])
  options={'conditioning_mode':'tara','structure_cfg':1.5};validate_request({**self.request(),'mode':'motion'},options,[1])
 def test_head_swap_prompt_template(self):
  from edit_modes import head_swap_prompt
  text=head_swap_prompt(' "Male, round face,\n short black hair" ')
  self.assertTrue(text.startswith('head_swap:\n\nsubject_definitions:'));self.assertIn('Facial details of <Subject 1>:\nMale, round face, short black hair\n',text)
  with self.assertRaises(ValueError):head_swap_prompt('  ')
 def test_tara_allowed_in_every_mode(self):
  for mode in ['swap','motion']:
   options={'conditioning_mode':'tara'};validate_request({**self.request(),'mode':mode},options,[1]);self.assertEqual(options['conditioning_mode'],'tara')
  options={'conditioning_mode':'tara'};validate_request({**self.request(),'mode':'headswap','prompt':''},options,[1]);self.assertEqual(options['conditioning_mode'],'tara')
 def test_character_swap_prompt_template(self):
  from edit_modes import character_swap_prompt
  text=character_swap_prompt('Male, tall, red afro wig, white jersey 87.')
  self.assertTrue(text.startswith('body_swap: subject_definitions: <Subject 1> is the Male, tall, red afro wig, white jersey 87 shown in <Picture 1>,'))
  self.assertIn('  summary: ',text);self.assertIn('  detailed_description: [Shot 1]',text);self.assertNotIn('\n',text)
 def test_omniref_base_without_turbo(self):
  g=h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,8,'original',[],'human',0,turbo='none',base='omniref')
  self.assertEqual(g['1']['inputs']['unet_name'],'fasth3_omniref_8step_pruned_int8_convrot.safetensors');self.assertNotIn('2',g);self.assertEqual(g['3']['inputs']['model'],['1',0])
  g=h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'motion',1,8,'original',[],'human',0,turbo='none',base='omniref')
  self.assertEqual(g['2']['inputs']['lora_name'],'henge/training_adapter_v2.safetensors')
 def test_cfg_adds_zeroed_negative(self):
  g=h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,30,'original',[],'human',0,turbo='none',cfg=4)
  self.assertEqual(g['24']['class_type'],'ConditioningZeroOut');self.assertEqual(g['10']['inputs']['negative'],['24',0]);self.assertEqual(g['10']['inputs']['cfg'],4.)
  self.assertNotIn('24',h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,8,'original',[],'human',0))
 def test_reference_order_is_explicit(self):
  g=fibo_graph('guide.png',['identity.png','background.png'],'edit',42);self.assertEqual(g['22']['inputs']['image'],'identity.png');self.assertEqual(g['23']['inputs']['image'],'background.png');self.assertEqual(g['5']['inputs']['images.image_1'],['4',0]);self.assertEqual(g['5']['inputs']['images.image_2'],['22',0]);self.assertNotIn('image_1',g['5']['inputs'])
if __name__=='__main__':unittest.main()
