import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vlm_pipeline import prompt_pipeline,composition_instruction
from workflows import plan_graph

FINAL='motion_transfer: subject_definitions: Goblin from <Picture 2>. summary: [reference generation] New scene. retention_analysis: Stable. detailed_description: [Shot 1] Transfer motion. overall_soundscape: N/A non_diegetic_music: N/A'

class VlmPipelineTests(unittest.TestCase):
 def test_single_image_calls_then_guide_then_text_only_composition(self):
  calls=[];replies=iter(['beach scene','green goblin','Pianist in a hall, hands on keys.',FINAL])
  def ask(instruction,image,stage,tokens):calls.append((instruction,image,stage,tokens));return next(replies)
  result=prompt_pipeline(ask,'Use <Picture 2> as performer and <Picture 1> as setting','motion',[(1,'beach.jpg'),(2,'goblin.jpg')],'guide-only.jpg',{'frames':107})
  self.assertEqual([c[1] for c in calls],['beach.jpg','goblin.jpg','guide-only.jpg',None])
  self.assertEqual([c[2] for c in calls],['vlm_picture_1','vlm_picture_2','vlm_guide','vlm_prompt'])
  self.assertIn('ONLY this single image',calls[0][0]);self.assertNotIn('green goblin',calls[0][0])
  self.assertIn('<Picture 1>: beach scene',calls[-1][0]);self.assertIn('<Picture 2>: green goblin',calls[-1][0])
  self.assertIn('Pianist in a hall',calls[-1][0]);self.assertIn('do not copy source hoodie',calls[-1][0]);self.assertEqual(result['prompt'],FINAL)
 def test_enhancement_off_does_not_call_writer_or_change_whitespace(self):
  calls=[]
  def ask(*args):calls.append(args);return 'observations'
  raw='  Meu texto <Picture 1>\n sem mudar. '
  self.assertEqual(prompt_pipeline(ask,raw,'motion',[(1,'identity.jpg')],'guide.jpg',{},False)['prompt'],raw)
  self.assertEqual(len(calls),2);self.assertNotIn('vlm_prompt',[c[2] for c in calls])
 def test_text_only_graph_has_no_image_node_or_image_port(self):
  graph=plan_graph(None,'compose',3072)
  self.assertNotIn('2',graph);self.assertNotIn('image',graph['3']['inputs'])
  self.assertFalse(graph['3']['inputs']['thinking']);self.assertEqual(graph['3']['inputs']['max_length'],3072)
  self.assertEqual(plan_graph('one.jpg','describe',384)['2']['inputs']['image'],'one.jpg')
 def test_template_substitution_does_not_expand_evidence_markers(self):
  text=composition_instruction('motion','keep {inventory}',[1],'<Picture 1>: actual','guide','{}')
  self.assertIn('keep {inventory}',text);self.assertIn('preserve the source video',text.lower())

if __name__=='__main__':unittest.main()

class PlanningIntegrationTests(unittest.TestCase):
 def test_bridge_runs_isolated_stages_and_does_not_let_router_rewrite_prompt(self):
  import os,server
  from test_contracts import WorkflowContracts,structured_prompt
  fixtures=WorkflowContracts();calls=[]
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'job').mkdir();(root/'input').mkdir()
   request=fixtures.request();job=dict(id='a'*32,request=request,options={'enhance_prompt':True},status='running')
   expected=structured_prompt('Writer output')
   def execute(job,graph,stage):
    calls.append((stage,graph));reply={'vlm_picture_1':'man in a jacket','vlm_guide':'a performer moves in a room','vlm_prompt':expected,'vlm_routing':json.dumps(dict(fixtures.plan(),prompt='wrong router prompt'))}[stage]
    return {'4':{'text':[reply]}}
   def save(job,**patches):job.update(patches);return job
   with patch.dict(os.environ,{'VLM_CHAT_URL':'','VLM_MODEL':''}),patch.object(server,'INPUT',root/'input'),patch.object(server,'job_path',return_value=root/'job'),patch.object(server,'load',return_value=job),patch.object(server,'save',side_effect=save),patch.object(server,'prepare_evidence',return_value=([(1,root/'input'/'one.jpg')],root/'input'/'guide.jpg',{})),patch.object(server,'execute_graph',side_effect=execute):
    server.planning(job)
   self.assertEqual([s for s,_ in calls],['vlm_picture_1','vlm_guide','vlm_prompt','vlm_routing'])
   self.assertEqual(job['plan']['prompt'],expected);self.assertEqual(job['status'],'awaiting_approval')
   for _,graph in calls[-2:]:self.assertNotIn('image',graph['3']['inputs'])
   self.assertTrue((root/'job'/'vlm_evidence.json').is_file())
 def test_evidence_sheet_has_only_guide_frames(self):
  import server
  from PIL import Image
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);inp=root/'input';inp.mkdir();work=root/'job';work.mkdir()
   Image.new('RGB',(40,30),'red').save(inp/'identity.png')
   def ffmpeg(args):Image.new('RGB',(80,50),'green').save(args[-1])
   job=dict(id='a'*32,request={'video':{'start_seconds':2.,'end_seconds':3.}},assets={'pictures':{'1':'identity.png'},'video':'guide.mp4'},video_info={'width':80,'height':50})
   with patch.object(server,'INPUT',inp),patch.object(server,'job_path',return_value=work),patch.object(server,'run',side_effect=ffmpeg):pictures,guide,meta=server.prepare_evidence(job)
   self.assertEqual(len(pictures),1);self.assertNotEqual(pictures[0][1],guide)
   with Image.open(guide) as image:self.assertGreater(image.getpixel((100,100))[1],image.getpixel((100,100))[0])
   self.assertEqual(len(meta['sampled_timestamps']),12)
   self.assertEqual(meta['sampled_timestamps'][0],2.)
