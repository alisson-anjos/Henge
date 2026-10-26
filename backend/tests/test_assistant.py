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
 def test_repairs_interrupted_tool_turns_and_orphan_results(self):
  history=[{'role':'user','text':'go'},
           {'role':'assistant','text':'','tool_calls':[{'id':'a','name':'view_frame','input':{}},{'id':'b','name':'view_pictures','input':{}}]},
           {'role':'tool','results':[{'id':'a','name':'view_frame','text':'ok'}]},
           {'role':'tool','results':[{'id':'orphan','name':'get_job','text':'ignore'}]},
           {'role':'user','text':'continue'}]
  repaired=assistant.repair_tool_history(history)
  self.assertEqual([m['role'] for m in repaired],['user','assistant','tool','user'])
  self.assertEqual([r['id'] for r in repaired[2]['results']],['a','b'])
  self.assertTrue(repaired[2]['results'][1]['is_error'])
  converted=assistant._to_openai(repaired)
  self.assertEqual([m.get('tool_call_id') for m in converted if m['role']=='tool'],['a','b'])
 def test_openai_token_limit_parameter(self):
  class R:
   def __init__(self,ok,text,payload=None):self.ok=ok;self.status_code=200 if ok else 400;self.text=text;self._p=payload
   def json(self):return self._p
  sent=[]
  def post(url,headers,timeout,json):
   sent.append([k for k in json if 'tokens' in k][0])
   if 'max_tokens' in json:return R(False,"Unsupported parameter: 'max_tokens' is not supported with this model.")
   return R(True,'',{'choices':[{'message':{'content':'hi'}}]})
  with patch.object(assistant.requests,'post',side_effect=post):
   out=assistant._call_openai({'base_url':'','api_key':'k','model':'gpt'},[{'role':'user','text':'hi'}])
  self.assertEqual(sent,['max_completion_tokens']);self.assertEqual(out['text'],'hi')
  sent.clear()
  with patch.object(assistant.requests,'post',side_effect=post):
   assistant._call_openai({'base_url':'http://127.0.0.1:1234/v1','api_key':'','model':'local'},[{'role':'user','text':'hi'}])
  self.assertEqual(sent,['max_tokens','max_completion_tokens'])
 def test_every_tool_is_routed(self):
  self.assertEqual(assistant.STUDIO_NAMES&assistant.JOB_NAMES,set())
  for t in assistant.TOOLS:self.assertEqual(t['input_schema']['type'],'object')

if __name__=='__main__':unittest.main()
