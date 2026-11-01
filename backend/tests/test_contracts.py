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
 def plan(self):return {'source_kind':'human','target_kind':'animal','adapt_reference':False,'adapt_instruction':'Replace <image_1> performer with <image_2>.','adapt_picture_slots':[1],'picture_roles':[{'slot':1,'role':'identity'}],'prompt':structured_prompt(),'warnings':[]}
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
 def test_adapted_reference_is_reused(self):
  import server,shutil as sh
  from PIL import Image
  def job(jid,options={}):
   (server.INPUT/'henge'/jid).mkdir(parents=True,exist_ok=True);server.job_path(jid).mkdir(parents=True,exist_ok=True)
   pic=server.INPUT/'henge'/jid/'cat.png';Image.new('RGB',(8,8),'gray').save(pic);(server.INPUT/'henge'/jid/'guide.mp4').write_bytes(b'v')
   j={'id':jid,'created':0,'status':'awaiting_approval','request':{'mode':'motion','video':{'start_seconds':0}},'options':{'seed':1,**options},'assets':{'video':f'henge/{jid}/guide.mp4','pictures':{'1':str(pic.relative_to(server.INPUT))}},
      'plan':{'adapt_reference':True,'adapt_picture_slots':[1],'source_kind':'human','target_kind':'animal','adapt_instruction':'x','picture_roles':[{'slot':1,'description':'A cat.'}]}}
   server.save(j);return j
  def fake(outputs,dest):Image.new('RGB',(8,8),'white').save(dest);return dest
  with patch.object(server,'frame_editor',return_value='klein3'),patch.object(server,'execute_graph',return_value={}) as run,patch.object(server,'image_from_output',side_effect=fake),patch.object(server,'run'):
   server.adapt_prepare(job('1'*32),job('1'*32));server.adapt_prepare(job('2'*32),job('2'*32));self.assertEqual(run.call_count,1)
   server.adapt_prepare(job('3'*32),job('3'*32),regenerate=True);self.assertEqual(run.call_count,2)
   edited=job('4'*32,{'adapt_instruction':'A cat knight, front and back.'});server.adapt_prepare(edited,edited);self.assertEqual(run.call_count,3)
   graph=run.call_args[0][1];self.assertEqual(graph['5']['inputs']['text'],'A cat knight, front and back.')
   self.assertTrue(graph['10']['inputs']['image'].endswith('cat.png'));self.assertTrue(graph['41']['inputs']['image'].endswith('adapt_source.png'))
  with patch.object(server,'frame_editor',return_value='klein3'):
   self.assertTrue(server.adapt_state(server.load('2'*32))['ready'])
 def test_character_swap_animal_gets_one_adapted_figure(self):
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
  with patch.object(server,'prepare_evidence',return_value=([(1,pic)],pic,{})),patch.object(server,'frame_editor',return_value='klein3'),patch.object(server,'execute_graph',side_effect=fake_graph):
   server.planning(job)
  plan=server.load(jid)['plan'];self.assertTrue(plan['adapt_reference'] and plan['preparation_recommended']);self.assertEqual(plan['target_kind'],'animal')
  req=server.adapt_request(server.load(jid));self.assertTrue(req['figure']);self.assertIn('Exactly one figure',req['instruction'])
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
 def test_tara_accepts_color_marks(self):
  a={'x':.5,'y':.5,'time_seconds':0,'frame_width':64,'frame_height':64}
  b=[{'color':'green','picture_slots':[1],'anchors':[a]}]
  for representation in ('2d','3d'):
   validate_request({**self.request(),'mode':'motion','subject_guidance':{'representation':representation,'bindings':b}},{'profile':'motion_tara','conditioning_mode':'tara'},[1])
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
 def test_cross_species_turns_on_adaptation(self):self.assertTrue(validate_plan(self.plan(),[1],{},self.request())['adapt_reference'])
 def test_human_to_human_does_not_prepare_for_clothing_or_hair(self):
  p=self.plan();p.update(source_kind='human',target_kind='human',adapt_reference=True)
  out=validate_plan(p,[1],{'adapt':'auto'},self.request())
  self.assertFalse(out['adapt_reference']);self.assertFalse(out['preparation_recommended'])
 def test_humanoid_creature_does_not_get_adaptation(self):
  plan=self.plan();plan.update(target_kind='other',adapt_reference=True)
  out=validate_plan(plan,[1],{},self.request());self.assertFalse(out['adapt_reference']);self.assertFalse(out['preparation_recommended'])
 def test_explicit_adapt_off_is_respected(self):self.assertFalse(validate_plan(self.plan(),[1],{'adapt':'off'},self.request())['adapt_reference'])
 def test_animal_never_uses_human_body_model(self):
  r=self.request();r['subject_guidance']['bindings']=[{'id':'cat'}];p=self.plan();p.update(source_kind='animal',target_kind='human');self.assertEqual(validate_plan(p,[1],{},r)['representation'],'2d')
 def test_environment_reference_does_not_become_character(self):
  p=self.plan();p['picture_roles']=[{'slot':1,'role':'identity'},{'slot':2,'role':'environment'}];p['adapt_picture_slots']=[1,2];self.assertEqual(validate_plan(p,[1,2],{},self.request())['picture_roles'][1]['role'],'environment')
 def test_roles_cover_all_input_pictures(self):
  with self.assertRaises(ValueError):validate_plan(self.plan(),[1,2],{},self.request())
 def test_disabled_branches_have_no_loaders(self):
  g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,'motion',42,8,'original',[],'human',0)
  self.assertNotIn('VAELoader',[v['class_type'] for k,v in g.items() if k=='19']);self.assertNotIn('20',g)
  self.assertFalse(any(v['class_type']=='TextEncodeFibo2' for v in g.values()))
 def test_motion_profiles_run_without_the_training_adapter(self):
  for profile in ['motion','motion_mix_dyn99']:
   g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0)
   # No training adapter at inference: turbo (default dmd8) -> motion LoRA; without a turbo the LoRA sits on the base.
   self.assertEqual(g['2']['inputs']['lora_name'],'henge/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors')
   self.assertNotIn('25',g);self.assertEqual(g['3']['inputs']['model'],['2',0])
   self.assertFalse(any('training_adapter' in str(n['inputs'].get('lora_name','')) for n in g.values()))
   bare=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0,turbo='none')
   self.assertNotIn('2',bare);self.assertEqual(bare['3']['inputs']['model'],['1',0])
 def test_fixed_recipe_modes_pick_profile_and_picture_count(self):
  for mode,slots,profile in [('headswap',[1],'headswap'),('sharpness',[],'sharpness')]:
   r={**self.request(),'mode':mode,'prompt':''};options={'profile':'motion','conditioning_mode':'tara'}
   validate_request(r,options,slots);self.assertEqual(options['profile'],profile);self.assertEqual(options['conditioning_mode'],'tara')
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'headswap'},{},[1,2])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'sharpness'},{},[1])
  with self.assertRaises(ValueError):validate_request(self.request(),{'profile':'sharpness'},[1])
 def test_fixed_recipe_graphs(self):
  g=h3_graph('v.mp4',['face.png'],'head_swap:',512,288,107,107,'headswap',42,8,'original',[],'human',0)
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/minimax_h3_head_swap_v1.0_r32.safetensors');self.assertEqual(g['13']['inputs']['scheduler'],'beta');self.assertFalse(g['9']['inputs']['guide_context'])
 def test_sharpness_upscale_methods(self):
  args=('v.mp4',[],'Enhance.',512,288,107,107,'sharpness',1,8,'original',[],'human',0)
  g=h3_graph(*args,upscale={'method':'h3','model':'h3_upscaler_lms_v0.1.safetensors','steps':1,'denoise':.15})
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/minimax_h3_lms_v1.0_r64.safetensors');self.assertEqual(g['30']['class_type'],'HengeH3LatentUpscale')
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
  import workflows
  ffp=workflows.FFP_PROFILE
  validate_request({**self.request(),'mode':'motion','prompt':'Add rain to the scene.'},{'profile':ffp},[])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'motion','prompt':'Add rain to the scene.'},{'profile':'motion'},[])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'motion','first_frame_slot':2},{'profile':ffp},[1])
  validate_request({**self.request(),'mode':'motion','first_frame_slot':1},{'profile':ffp},[1])
  self.assertEqual(ffp_prompt('Add rain.'),'vfx_edit: Add rain.');self.assertIn('<Picture 3> is the edited first frame',ffp_prompt('vfx_edit: Add rain.',3))
  # The merge carries its own SolarRenderer control, so it builds on the standard turbo and takes the guide as latents only.
  g=h3_graph('v.mp4',['f.png'],'vfx_edit: Add rain.',512,288,107,107,ffp,1,4,'original',[],'human',0,turbo=workflows.MODELS[ffp]['turbo_default'])
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors');self.assertEqual(g['2']['inputs']['lora_name'],workflows.TURBOS[workflows.MODELS[ffp]['turbo_default']]['lora']);self.assertFalse(g['9']['inputs']['guide_context'])
 def test_character_swap_first_frame(self):
  from edit_modes import character_swap_prompt,swap_first_frame
  import server
  # Character Swap's edited frame is not a Picture: it goes into the guide (guide_first_frame + its own file).
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'swap','first_frame_slot':1},{'profile':'character'},[1])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'motion','guide_first_frame':True},{},[1])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'swap','guide_first_frame':True,'first_frame_mode':'output'},{},[1])
  options={};validate_request({**self.request(),'mode':'swap','guide_first_frame':True},options,[1]);self.assertEqual(options['profile'],'character')
  # Its own first frame already shows the characters: no picture is needed then, and only then.
  validate_request({**self.request(),'mode':'swap','guide_first_frame':True,'prompt':'Keep the hat.'},{},[])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'swap','prompt':'Keep the hat.'},{},[])
  from edit_modes import first_frame_only_prompt
  p=first_frame_only_prompt('  Keep   the hat. ');self.assertTrue(p.startswith('body_swap: subject_definitions: the people in the edited first frame'));self.assertTrue(p.endswith(' Keep the hat.'));self.assertNotIn('<Picture',p)
  # Default: frame 0 of the guide; reference mode names it as the Picture after the character pictures.
  self.assertIn('guide video opens on an edited first frame',swap_first_frame('body_swap: x',True))
  self.assertIn('<Picture 2> is the edited first frame',swap_first_frame('body_swap: x',True,2))
  self.assertEqual(swap_first_frame('body_swap: x',False),'body_swap: x')
  self.assertIn('shown in <Picture 2>',character_swap_prompt('Male, tall',2))
  # Which image a job opens on: Character Swap's own file, Motion's First Frame Picture, or none.
  assets={'first_frame':'henge/j/first_frame.png','pictures':{'1':'henge/j/picture_1.png','2':'henge/j/picture_2.png'}}
  self.assertEqual(server.first_frame_image({'mode':'swap','guide_first_frame':True},assets).name,'first_frame.png')
  self.assertEqual(server.first_frame_image({'mode':'motion','first_frame_slot':2},assets).name,'picture_2.png')
  self.assertIsNone(server.first_frame_image({'mode':'swap'},assets))
  # The graph puts it into the conditioning node, which replaces the guide's frame 0 after HengeGuide.
  g=h3_graph('v.mp4',['p.png'],'body_swap: x',512,288,107,107,'character',1,8,'original',[],'human',0,first_frame='henge/j/first_frame.png')
  self.assertEqual(g['9']['inputs']['first_frame'],['27',0]);self.assertEqual(g['27']['inputs']['image'],'henge/j/first_frame.png')
  self.assertNotIn('first_frame',h3_graph('v.mp4',['p.png'],'body_swap: x',512,288,107,107,'character',1,8,'original',[],'human',0)['9']['inputs'])
  # The Swap character frame edit: image 2 is the character, put in the performer's place with the same pose.
  from server import edit_instruction
  text=edit_instruction('swap','the man in red','',1)
  self.assertTrue(text.startswith('Replace the man in red with the character from image 2'));self.assertNotIn('Use image 2 as the reference',text)
  self.assertIn('the main person',edit_instruction('swap','','',1))
  # Picked from the SAM 3.1 segments: the frame is marked magenta and the marker has to go.
  marked=edit_instruction('swap','','',1,True)
  self.assertTrue(marked.startswith('Replace the character marked in magenta with the character from image 2'));self.assertIn('remove it completely',marked)
  # No picture: the description is the character.
  self.assertTrue(edit_instruction('swap','','a knight in silver armor',0,True).startswith('Replace the character marked in magenta with this character: a knight in silver armor.'))
  # The modal shows this default and lets the user rewrite it.
  from server import frame_edit_default
  self.assertEqual(frame_edit_default('swap','','',1,True)['instruction'],marked)
  from workflows import find_people_graph
  g=find_people_graph('henge/x/frame.png','character',True);self.assertEqual(g['5']['inputs']['images'],['2',2]);self.assertNotIn('5',find_people_graph('henge/x/frame.png'))
 def test_bfs_body_swap_editor(self):
  # BFS Body Swap V1.0 (Qwen-Image 2.1): its guide's contract, scene first at ~2 MP, the character second at ~0.59 MP,
  # the BFS LoRA over the (turbo) model, and its trained prompt by default.
  from workflows import bfs_graph,BFS,QWEN21
  g=bfs_graph('henge/j/frame.png',['henge/j/picture_01.png'],'',7,unet=QWEN21['base'],lora=QWEN21['turbo'])
  self.assertEqual(g['30']['inputs']['lora_name'],BFS['lora']);self.assertEqual(g['30']['inputs']['model'],['9',0]);self.assertEqual(g['6']['inputs']['model'],['30',0])
  self.assertEqual(g['5']['inputs']['images.image_1'],['31',0]);self.assertEqual(g['31']['inputs']['megapixels'],2.)
  self.assertEqual(g['5']['inputs']['images.image_2'],['32',0]);self.assertEqual(g['32']['inputs']['megapixels'],.59);self.assertEqual(g['32']['inputs']['image'],['22',0])
  self.assertEqual(g['5']['inputs']['prompt'],BFS['prompt']);self.assertEqual(g['5']['inputs']['resolution'],0)
  self.assertTrue(BFS['prompt'].startswith('body_swap: start with <image1> as the base image'))
  with self.assertRaises(ValueError):bfs_graph('henge/j/frame.png',[],'',7)
  # Without the turbo LoRA the BFS LoRA loads straight on the checkpoint.
  self.assertEqual(bfs_graph('f.png',['p.png'],'',1)['30']['inputs']['model'],['1',0])
  from server import editor_instruction,EDITORS
  self.assertEqual(editor_instruction('bfs','swap','','',1),BFS['prompt']);self.assertTrue(editor_instruction('bfs','swap','','keep the microphone',1).endswith('. keep the microphone'))
  self.assertIn('magenta',editor_instruction('fibo','swap','','',1,True));self.assertEqual(EDITORS[-1][0],'bfs')
 def test_the_picker_tags_say_what_each_model_was_trained_for(self):
  # The model names cannot carry every caveat, so each model ships tags and the picker spells them out.
  # The point is honesty: a model that handles a task without having been trained for it must not look
  # like one that was, and every tag has to have words in every interface language.
  import json,workflows
  from pathlib import Path
  wording=json.loads((Path(__file__).resolve().parents[2]/'lib'/'model-tags.json').read_text())
  self.assertEqual(workflows.MODELS['motion']['tags'],['multi-ref','ffp-strong'])
  self.assertEqual(workflows.MODELS['motion_tara']['tags'],['multi-ref','ffp-works'])
  # Trained on one reference but able to take more: that is a weaker multi-reference, not "no multi-reference".
  self.assertEqual(workflows.MODELS['character']['tags'],['multi-ref-weak'])
  self.assertEqual(workflows.MODELS['headswap']['tags'],['single-ref'])
  # The first-frame model's whole point is FFP, so that is the only claim it needs.
  self.assertEqual(workflows.MODELS[workflows.FFP_PROFILE]['tags'],['ffp-strong','multi-ref-weak'])
  for name,model in workflows.MODELS.items():
    for tag in model.get('tags',[]):
      for language in ('en','pt','es'):
        self.assertIn(tag,wording[language],f'{language} has no wording for the {tag} tag')
        self.assertTrue(wording[language][tag]['tag'] and wording[language][tag]['tip'])

 def test_solarrenderer_ffp_needs_a_first_frame(self):
  import workflows
  from edit_modes import ffp_prompt
  m=workflows.MODELS['motion_solar_ffp']
  self.assertEqual(m['label'],'Motion Transfer SolarRenderer FFP v1.0');self.assertEqual(m['lora'],'henge/solar_control.safetensors')
  self.assertTrue(m['first_frame_only']);self.assertFalse(m.get('ffp'));self.assertEqual(m['tags'],['ffp-only'])
  # Always offered, but it cannot run without its edited frame; with one it is a normal choice.
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'motion','prompt':'Add rain.'},{'profile':'motion_solar_ffp'},[1])
  validate_request({**self.request(),'mode':'motion','prompt':'Add rain.','first_frame_slot':1},{'profile':'motion_solar_ffp'},[1])
  # A First Frame still defaults to Motion Transfer FFP v1.0, not to this one.
  options={};validate_request({**self.request(),'mode':'motion','prompt':'Add rain.','first_frame_slot':1},options,[1]);self.assertEqual(options['profile'],workflows.FFP_PROFILE)
  # Its prompt is the FFP sentence without the VFX Edit trigger.
  self.assertEqual(ffp_prompt('Add rain.',None,None),'Add rain.');self.assertTrue(ffp_prompt('vfx_edit: Add rain.',2,None).startswith('Add rain. <Picture 2> is the edited first frame'))
  g=h3_graph('v.mp4',['f.png'],'Add rain.',512,288,107,107,'motion_solar_ffp',1,4,'original',[],'human',0,turbo=m['turbo_default'])
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/solar_control.safetensors');self.assertFalse(g['9']['inputs']['guide_context'])

 def test_motion_model_list_and_first_frame_default(self):
  import json,workflows
  # The studio offers three Motion models: the two trained ones and the Edit merge. The superseded comparison LoRAs are
  # gone from the collection entirely.
  self.assertEqual([key for key,model in workflows.MODELS.items() if model.get('task')=='motion'],['motion','motion_tara','motion_mix_dyn99','motion_solar_ffp'])
  self.assertFalse([key for key in ('motion_ffp','motion_ffp_dyn95','motion_mix_dyn95','motion_solar_dyn95','motion_solar_dyn99') if key in workflows.MODELS])
  # An API/MCP call that attaches a First Frame gets the Edit model, which propagates it.
  options={};validate_request({**self.request(),'mode':'motion','prompt':'Add rain to the scene.','first_frame_slot':1},options,[1])
  self.assertEqual(options['profile'],workflows.FFP_PROFILE)
  # Without a First Frame the plain Motion Transfer LoRA stays the default.
  options={};validate_request({**self.request(),'mode':'motion','prompt':'Follow this performance.'},options,[1])
  self.assertEqual(options['profile'],'motion')
  # The Edit model declares the standard 4-step turbo and the LoRA ships under the same name the download manifest uses.
  self.assertEqual(workflows.MODELS[workflows.FFP_PROFILE]['turbo_default'],workflows.DEFAULT_TURBO)
  g=h3_graph('v.mp4',['f.png'],'vfx_edit: Add rain.',512,288,107,107,workflows.FFP_PROFILE,1,4,'original',[],'human',0,turbo=workflows.MODELS[workflows.FFP_PROFILE]['turbo_default'])
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors')
  self.assertEqual(g['2']['inputs']['lora_name'],workflows.TURBOS[workflows.DEFAULT_TURBO]['lora'])
  self.assertFalse(g['9']['inputs']['guide_context'])
  manifest=json.loads((Path(__file__).resolve().parents[2]/'config/model-repos.example.json').read_text())
  by_id={item['id']:item for item in manifest['models']}
  self.assertEqual(by_id['ffp']['destination'],'loras/henge/minimax_h3_motion_transfer_ffp_v1.0_ref2va.safetensors')
  # Installing the First Frame model also offers the optional SolarRenderer turbo.
  self.assertIn('ffp',by_id['turbo_solar4']['profiles'])
  self.assertEqual([item['id'] for item in manifest['models'] if 'Minimax-H3-ComfyUI/resolve/main/loras/experimental/' in item.get('url','')],[])
  offered={item['destination'] for item in manifest['models']}
  for key in ('motion','motion_tara',workflows.FFP_PROFILE):
    self.assertIn('loras/'+workflows.MODELS[key]['lora'],offered)
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
  self.assertNotIn('2',g);self.assertEqual(g['3']['inputs']['model'],['1',0])
 def test_cfg_adds_zeroed_negative(self):
  g=h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,30,'original',[],'human',0,turbo='none',cfg=4)
  self.assertEqual(g['24']['class_type'],'ConditioningZeroOut');self.assertEqual(g['10']['inputs']['negative'],['24',0]);self.assertEqual(g['10']['inputs']['cfg'],4.)
  self.assertNotIn('24',h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'character',1,8,'original',[],'human',0))
 def test_reference_order_is_explicit(self):
  g=fibo_graph('guide.png',['identity.png','background.png'],'edit',42);self.assertEqual(g['22']['inputs']['image'],'identity.png');self.assertEqual(g['23']['inputs']['image'],'background.png');self.assertEqual(g['5']['inputs']['images.image_1'],['4',0]);self.assertEqual(g['5']['inputs']['images.image_2'],['22',0]);self.assertNotIn('image_1',g['5']['inputs'])
if __name__=='__main__':unittest.main()
