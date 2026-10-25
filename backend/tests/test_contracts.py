import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflows import split_frames,h3_graph,fibo_graph,split_on_cuts
from server import validate_request,validate_plan,training_busy
from unittest.mock import patch,Mock
def structured_prompt(description='Transfer the guide performance.'):
 return 'motion_transfer: subject_definitions: <Subject 1> uses <Picture 1>. summary: [reference generation] '+description+' retention_analysis: <Subject 1>: fully_preserved - stable identity. detailed_description: [Shot 1] Transfer the guide timing and gestures. overall_soundscape: N/A non_diegetic_music: N/A'

class WorkflowContracts(unittest.TestCase):
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
  for profile in ['motion','motion_tara4500']:
   g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0)
   # adapter V2 -> turbo (default dmd8) -> motion LoRA
   self.assertEqual(g['2']['inputs']['lora_name'],'henge/training_adapter_v2.safetensors')
   self.assertEqual(g['25']['inputs'],{'model':['2',0],'lora_name':'henge/dmd_ref2va_8step.safetensors','strength_model':1.})
   self.assertEqual(g['3']['inputs']['model'],['25',0])
   self.assertEqual(h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0,turbo='none')['3']['inputs']['model'],['2',0])
 def test_adapterless_motion_profiles_skip_adapter_v2(self):
  for profile in ['motion_solar','motion_solar_control']:
   # turbo straight on the base, then the LoRA (which already holds the adapter, or needs none)
   g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0,conditioning_mode='tara')
   self.assertEqual(g['2']['inputs'],{'model':['1',0],'lora_name':'henge/dmd_ref2va_8step.safetensors','strength_model':1.})
   self.assertNotIn('25',g);self.assertEqual(g['3']['inputs']['model'],['2',0]);self.assertEqual(g['10']['inputs']['model'],['21',0])
   g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,4,'original',[],'human',0,turbo='solar4')
   self.assertEqual(g['2']['inputs']['lora_name'],'henge/turbo_solar_4step.safetensors')
   g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,profile,42,8,'original',[],'human',0,turbo='none')
   self.assertNotIn('2',g);self.assertEqual(g['3']['inputs']['model'],['1',0])
  g=h3_graph('test.mp4',['ref.png'],'test',512,288,107,107,'motion_tara4500_solar',42,8,'original',[],'human',0)
  self.assertEqual(g['2']['inputs']['lora_name'],'henge/training_adapter_v2.safetensors');self.assertEqual(g['3']['inputs']['model'],['25',0])
 def test_fixed_recipe_modes_pick_profile_and_picture_count(self):
  for mode,slots,profile in [('headswap',[1],'headswap'),('sharpness',[],'sharpness')]:
   r={**self.request(),'mode':mode,'prompt':''};options={'profile':'motion','conditioning_mode':'tara'}
   validate_request(r,options,slots);self.assertEqual(options['profile'],profile);self.assertEqual(options['conditioning_mode'],'tara')
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'headswap'},{},[1,2])
  with self.assertRaises(ValueError):validate_request({**self.request(),'mode':'sharpness'},{},[1])
  with self.assertRaises(ValueError):validate_request(self.request(),{'profile':'sharpness'},[1])
 def test_fixed_recipe_graphs(self):
  g=h3_graph('v.mp4',[],'Enhance this video.',512,288,107,107,'sharpness',42,8,'original',[],'human',0)
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/lms_v1_fro_dyn95.safetensors');self.assertEqual(g['7']['inputs']['pictures'],'[]');self.assertEqual(g['13']['inputs']['scheduler'],'simple')
  g=h3_graph('v.mp4',['face.png'],'head_swap:',512,288,107,107,'headswap',42,8,'original',[],'human',0)
  self.assertEqual(g['3']['inputs']['lora_name'],'henge/head_swap_v1_0_r32.safetensors');self.assertEqual(g['13']['inputs']['scheduler'],'beta');self.assertFalse(g['9']['inputs']['guide_context'])
 def test_sharpness_latent_upscale_two_pass(self):
  g=h3_graph('v.mp4',[],'Enhance.',544,1024,73,72,'sharpness',1,8,'original',[],'human',0,lora_strength=1.4,upscale={'width':1088,'height':2048,'denoise':.5})
  self.assertEqual(g['3']['inputs']['strength_model'],1.4);self.assertEqual(g['30']['inputs']['latent'],['15',0]);self.assertEqual((g['30']['inputs']['mode.width'],g['30']['inputs']['mode.height']),(1088,2048))
  self.assertEqual(g['32']['inputs']['guide'],['31',0]);self.assertEqual(g['37']['inputs']['latent_image'],['33',0]);self.assertEqual(g['34']['inputs']['denoise'],.5);self.assertEqual(g['16']['inputs']['samples'],['38',0])
  self.assertNotIn('30',h3_graph('v.mp4',[],'Enhance.',544,1024,73,72,'sharpness',1,8,'original',[],'human',0))
 def test_tara_structure_guidance(self):
  g=h3_graph('v.mp4',['r.png'],'p',512,288,107,107,'motion_tara4500',1,8,'original',[],'human',0,conditioning_mode='tara',structure_cfg=1.5)
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
