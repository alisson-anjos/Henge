import json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from comfy_client import ComfyFiles,referenced_files,output_files
from workflows import h3_graph,fibo_graph

class ComfyClientTests(unittest.TestCase):
 def setUp(self):
  self.dir=tempfile.TemporaryDirectory();self.staging=Path(self.dir.name)
  for name in ['shot_000.mp4','picture_1.png','picture_2.png','context_001.mp4']:
   p=self.staging/'henge/job'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'x')
 def tearDown(self):self.dir.cleanup()
 def test_graph_references_include_picture_lists_and_context(self):
  g=h3_graph('henge/job/shot_000.mp4',['henge/job/picture_1.png','henge/job/picture_2.png'],'p',512,288,107,107,'motion',1,8,'original',[],'human',0,context_video='henge/job/context_001.mp4',context_count=22)
  self.assertEqual(sorted(referenced_files(g,self.staging)),['henge/job/context_001.mp4','henge/job/picture_1.png','henge/job/picture_2.png','henge/job/shot_000.mp4'])
  # Model names and prompts are never mistaken for files; missing files are not uploaded.
  self.assertEqual(referenced_files(fibo_graph('henge/job/missing.png',['henge/job/picture_1.png'],'edit',1),self.staging),['henge/job/picture_1.png'])
 def test_upload_once_per_file_version(self):
  files=ComfyFiles('http://comfy',self.staging);ok=mock.Mock(ok=True);ok.json.return_value={'name':'picture_1.png','subfolder':'henge/job','type':'input'}
  with mock.patch('comfy_client.requests.post',return_value=ok) as post:
   files.upload('henge/job/picture_1.png');files.upload('henge/job/picture_1.png')
  self.assertEqual(post.call_count,1);self.assertEqual(post.call_args.kwargs['data'],{'subfolder':'henge/job','type':'input','overwrite':'true'})
 def test_renamed_uploads_rewrite_the_graph(self):
  # A backend that ignores subfolders (Comfy Cloud) stores flat names: the graph follows them.
  files=ComfyFiles('http://comfy',self.staging)
  def stored(url,files,data,headers,timeout):
   r=mock.Mock(ok=True);r.json.return_value={'name':'cloud_'+files['image'][0],'subfolder':'','type':'input'};return r
  g=h3_graph('henge/job/shot_000.mp4',['henge/job/picture_1.png'],'p',512,288,107,107,'motion',1,8,'original',[],'human',0)
  with mock.patch('comfy_client.requests.post',side_effect=stored):out=files.upload_graph_inputs(g)
  self.assertEqual(out['7']['inputs']['video'],'cloud_shot_000.mp4');self.assertEqual(json.loads(out['7']['inputs']['pictures']),['cloud_picture_1.png'])
  self.assertEqual(g['7']['inputs']['video'],'henge/job/shot_000.mp4')
 def test_signed_redirect_drops_credentials(self):
  files=ComfyFiles('https://cloud',self.staging,{'X-API-Key':'k'})
  redirect=mock.Mock(is_redirect=True,headers={'location':'https://storage/signed'})
  final=mock.MagicMock(ok=True);final.__enter__.return_value=final;final.iter_content.return_value=[b'video']
  with mock.patch('comfy_client.requests.get',side_effect=[redirect,final]) as get:files.download({'filename':'r.mp4'},self.staging/'out.mp4')
  self.assertEqual(get.call_args_list[1].args,('https://storage/signed',));self.assertNotIn('headers',get.call_args_list[1].kwargs)
  self.assertEqual((self.staging/'out.mp4').read_bytes(),b'video')
 def test_output_files_by_node_and_kind(self):
  outputs={'17':{'videos':[{'filename':'r.mp4','subfolder':'henge/job','type':'output'}]},'18':{'videos':[{'filename':'g.mp4','subfolder':'henge/job','type':'output'}]},'4':{'text':['hi']}}
  self.assertEqual([x['filename'] for x in output_files(outputs,'17','videos')],['r.mp4'])
  self.assertEqual(len(output_files(outputs,kind='videos')),2);self.assertEqual(output_files(outputs,'4'),[])

if __name__=='__main__':unittest.main()
