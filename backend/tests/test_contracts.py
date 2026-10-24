import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflows import split_frames,h3_graph,fibo_graph,split_on_cuts
from server import validate_request,validate_plan,training_busy
from unittest.mock import patch,Mock
def structured_prompt(description='Transfer the guide performance.'):
 return 'motion_transfer: subject_definitions: <Subject 1> uses <Picture 1>. summary: [reference generation] '+description+' retention_analysis: <Subject 1>: fully_preserved - stable identity. detailed_description: [Shot 1] Transfer the guide timing and gestures. overall_soundscape: N/A non_diegetic_music: N/A'

class WorkflowContracts(unittest.TestCase):
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
 def test_reference_order_is_explicit(self):
  g=fibo_graph('guide.png',['identity.png','background.png'],'edit',42);self.assertEqual(g['22']['inputs']['image'],'identity.png');self.assertEqual(g['23']['inputs']['image'],'background.png')
if __name__=='__main__':unittest.main()
