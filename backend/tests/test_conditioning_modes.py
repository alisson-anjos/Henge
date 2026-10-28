import ast,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflows import h3_graph

class ConditioningModes(unittest.TestCase):
 def test_tara_model_is_used_by_guider_and_scheduler(self):
  g=h3_graph('clip.mp4',['identity.png'],'text',512,288,22,22,'motion',42,8,'original',[],'human',0,conditioning_mode='tara',reference_scale=.5)
  self.assertEqual(g['21']['class_type'],'BFSMiniMaxH3NativeTemporal');self.assertEqual(g['10']['inputs']['model'],['21',0]);self.assertEqual(g['13']['inputs']['model'],['21',0]);self.assertEqual(g['9']['inputs']['reference_scale'],.5)
 def test_guide_default_and_raw_context_prompt_are_preserved(self):
  args=('clip.mp4',['identity.png'],'  raw text  ',512,288,22,22,'motion',42,8,'original',[],'human',0)
  self.assertNotIn('21',h3_graph(*args))
  g=h3_graph(*args,conditioning_mode='tara',context_video='context.mp4',context_count=5,context_prompt=False)
  self.assertEqual(g['9']['inputs']['prompt'],'  raw text  ')
 def test_native_branch_uses_guide_only_for_history_and_keeps_picture_roles(self):
  source=Path(__file__).resolve().parents[1]/'comfy_nodes/henge/__init__.py'
  cls=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='HengeH3Conditioning')
  calls=[]
  class Native:
   @classmethod
   def execute(c,**kw):calls.append(('native',kw));return 'cond',{}
  class Guide:
   @classmethod
   def execute(c,**kw):calls.append(('guide',kw));return ('guided',)
  def clip_context(*a,**kw):calls.append(('clip_context',kw));return a[0]
  scope={'torch':torch,'clip_with_video_context':clip_context}
  exec(compile(ast.Module(body=[cls],type_ignores=[]),str(source),'exec'),scope)
  with patch.dict(sys.modules,{'comfy_extras.nodes_minimax_h3':SimpleNamespace(MiniMaxH3ReferenceToVideo=Native,MiniMaxH3AddGuide=Guide)}):
   refs=[torch.zeros(1,64,64,3),torch.ones(1,64,64,3)];video=torch.zeros(5,64,128,3)
   args=dict(clip=object(),vae=object(),guide=video,references=refs,prompt='test',width=128,height=64,length=5,clip_video_fps=2,reference_size='match',guide_context=True,audio_conditioning=False,audio_video='',context_images=torch.ones(5,64,128,3),context_count=5)
   scope['HengeH3Conditioning']().encode(**args,conditioning_mode='tara',reference_scale=.5)
   self.assertEqual([name for name,_ in calls],['native','guide'])
   self.assertEqual(calls[1][1]['frame_idx'],0)
   self.assertEqual(len(calls[1][1]['image']),5)
   kw=calls[0][1];self.assertEqual(tuple(kw['ref_videos']['ref_video_1'].shape),(5,32,64,3));self.assertIs(kw['ref_images']['ref_image_1'],refs[0]);self.assertEqual(len(kw['ref_images']),3)
   calls.clear();scope['HengeH3Conditioning']().encode(**args)
   self.assertEqual([name for name,_ in calls],['clip_context','native','guide','guide'])
   self.assertNotIn('ref_videos',calls[1][1])

if __name__=='__main__':unittest.main()

class MotionModelSelection(unittest.TestCase):
 def test_both_motion_models_support_both_methods(self):
  for profile,filename in [('motion','minimax_h3_motion_transfer_v1.0_ref2va.safetensors'),('motion_mix_dyn95','minimax_h3_motion_transfer_combined_v1.0_dyn95.safetensors'),('motion_tara','minimax_h3_motion_transfer_tara_v1.0_ref2va.safetensors')]:
   for method in ['guide','tara']:
    g=h3_graph('clip.mp4',['identity.png'],'text',512,288,22,22,profile,42,8,'original',[],'human',0,conditioning_mode=method)
    self.assertTrue(g['3']['inputs']['lora_name'].endswith(filename))
    self.assertEqual('21' in g,method=='tara')
 def test_character_swap_uses_v11(self):
  g=h3_graph('clip.mp4',['identity.png'],'text',512,288,22,22,'character',42,8,'original',[],'human',0)
  self.assertTrue(g['3']['inputs']['lora_name'].endswith('minimax_h3_character_swap_v1.1_ref2va_fro.safetensors'))

class PreparationChoice(unittest.TestCase):
 def test_choice_updates_only_awaiting_plan_and_preserves_original_prompt(self):
  from fastapi.testclient import TestClient
  import server
  job={'id':'a'*32,'status':'awaiting_approval','options':{'adapt':'auto'},'plan':{'adapt_reference':True,'prompt':'original text','adapt_picture_slots':[1],'adapt_instruction':'Prepare upright dog'}}
  def save(current,**patches):current.update(patches);return current
  with patch.object(server,'load',return_value=job),patch.object(server,'save',side_effect=save),patch.object(server,'frame_editor',return_value='klein3'):
   client=TestClient(server.app)
   for enabled in [False,True]:
    result=client.post('/jobs/'+job['id']+'/preparation',json={'enabled':enabled})
    self.assertEqual(result.status_code,200);self.assertEqual(result.json()['plan']['adapt_reference'],enabled)
    self.assertEqual(job['plan']['prompt'],'original text')
   job['status']='rendering'
   self.assertEqual(client.post('/jobs/'+job['id']+'/preparation',json={'enabled':False}).status_code,409)
 def test_adaptation_refused_without_image_editor(self):
  from fastapi.testclient import TestClient
  import server
  job={'id':'b'*32,'status':'awaiting_approval','options':{'adapt':'auto'},'plan':{'adapt_reference':False,'prompt':'p','adapt_picture_slots':[1],'adapt_instruction':'Prepare upright dog'}}
  self.assertIsNone(server.frame_editor({'TextEncodeFibo2':{},'UNETLoader':{'input':{'required':{'unet_name':[['fibo2_edit_turbo_int8_convrot.safetensors']]}}}}))
  with patch.object(server,'load',return_value=job),patch.object(server,'save'),patch.object(server,'frame_editor',return_value=None):
   self.assertEqual(TestClient(server.app).post('/jobs/'+job['id']+'/preparation',json={'enabled':True}).status_code,409)
