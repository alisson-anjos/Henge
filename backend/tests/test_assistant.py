import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistant

class AssistantTest(unittest.TestCase):
 def test_config_never_returns_the_key(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'assistant.json'
   cfg=assistant.save_config(p,{'provider':'openai','model':'local-vl','base_url':'http://127.0.0.1:1234/v1','api_key':'sk-secret-123456'})
   self.assertEqual(cfg['api_key'],'sk-secret-123456')
   pub=assistant.public_config(cfg);self.assertNotIn('api_key',pub);self.assertTrue(pub['has_key']);self.assertEqual(pub['key_hint'],'…3456')
   assistant.save_config(p,{'model':'other'});self.assertEqual(assistant.load_config(p)['api_key'],'sk-secret-123456')   # an empty key keeps the saved one
   with self.assertRaises(ValueError):assistant.save_config(p,{'provider':'gemini'})
 def test_step_runs_job_tools_and_returns_studio_calls(self):
  replies=[{'text':'','tool_calls':[{'id':'a','name':'get_job','input':{'job_id':'x'}}],'native':None},
           {'text':'Marking.','tool_calls':[{'id':'b','name':'find_people','input':{'time':1}},{'id':'c','name':'get_job','input':{'job_id':'x'}}],'native':None}]
  with patch.object(assistant,'call_model',side_effect=replies):
   out=assistant.step({},[{'role':'user','text':'hi'}],lambda name,args:('{"status":"completed"}',[]))
  self.assertFalse(out['done']);self.assertEqual([c['name'] for c in out['studio_calls']],['find_people'])
  self.assertEqual([r['id'] for r in out['job_results']],['c'])
  self.assertEqual([m['role'] for m in out['messages']],['user','assistant','tool','assistant'])
 def test_job_tool_errors_reach_the_model(self):
  replies=[{'text':'','tool_calls':[{'id':'a','name':'approve_job','input':{'job_id':'x'}}],'native':None},{'text':'It failed.','tool_calls':[],'native':None}]
  def boom(name,args):raise ValueError('This job has no plan awaiting approval')
  with patch.object(assistant,'call_model',side_effect=replies):out=assistant.step({},[{'role':'user','text':'go'}],boom)
  self.assertTrue(out['done']);self.assertTrue(out['messages'][2]['results'][0]['is_error'])
 def test_provider_formats(self):
  img='data:image/jpeg;base64,AAAA'
  history=[{'role':'user','text':'hi','images':[img]},{'role':'assistant','text':'look','tool_calls':[{'id':'t1','name':'view_frame','input':{'time':2}}]},
           {'role':'tool','results':[{'id':'t1','name':'view_frame','text':'frame','images':[img]}]}]
  a=assistant._to_anthropic(history)
  self.assertEqual(a[0]['content'][0]['type'],'image');self.assertEqual(a[1]['content'][1]['type'],'tool_use')
  self.assertEqual(a[2]['content'][0]['type'],'tool_result');self.assertEqual(a[2]['content'][0]['content'][1]['type'],'image')
  native=[{'type':'thinking','thinking':'','signature':'s'},{'type':'text','text':'look'}]
  self.assertEqual(assistant._to_anthropic([{'role':'assistant','text':'look','native':native,'native_provider':'anthropic'}])[0]['content'],native)
  o=assistant._to_openai(history)
  self.assertEqual(o[0]['role'],'system');self.assertEqual(o[2]['tool_calls'][0]['function']['arguments'],'{"time": 2}')
  self.assertEqual(o[3]['role'],'tool');self.assertEqual(o[4]['role'],'user');self.assertEqual(o[4]['content'][1]['type'],'image_url')
 def test_every_tool_is_routed(self):
  self.assertEqual(assistant.STUDIO_NAMES&assistant.JOB_NAMES,set())
  for t in assistant.TOOLS:self.assertEqual(t['input_schema']['type'],'object')

if __name__=='__main__':unittest.main()
