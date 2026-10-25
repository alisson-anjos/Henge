import base64,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runpod_backend import RunPodBackend
from workflows import h3_graph

def reply(data,ok=True,code=200):
 r=mock.Mock(ok=ok,status_code=code,text=json.dumps(data));r.json.return_value=data;return r

class RunPodBackendTests(unittest.TestCase):
 def setUp(self):
  self.dir=tempfile.TemporaryDirectory();self.root=Path(self.dir.name)
  for name in ['shot_000.mp4','picture_1.png']:
   p=self.root/'input/henge/job'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode())
  with mock.patch.dict(os.environ,{'RUNPOD_ENDPOINT_ID':'ep','RUNPOD_API_KEY':'k'}):self.backend=RunPodBackend(self.root/'input',self.root)
  self.graph=h3_graph('henge/job/shot_000.mp4',['henge/job/picture_1.png'],'p',512,288,107,107,'motion',1,8,'original',[],'human',0)
 def tearDown(self):self.dir.cleanup()
 def test_run_sends_files_reports_progress_and_returns_outputs(self):
  done={'status':'COMPLETED','output':{'outputs':{'17':{'videos':[{'filename':'r.mp4','subfolder':'henge/job','type':'output'}]}},
        'files':{'henge/job/r.mp4':base64.b64encode(b'video').decode()},'inventory':{'nodes':['HengeGuide'],'choices':{'LoraLoaderModelOnly.lora_name':['a.safetensors']}}}}
  calls=[]
  def request(method,url,headers,timeout,**kw):
   calls.append((method,url,kw));self.assertEqual(headers['Authorization'],'Bearer k')
   if url.endswith('/run'):return reply({'id':'r1'})
   return reply({'status':'IN_PROGRESS','output':{'class_type':'SamplerCustomAdvanced','value':3,'max':8}}) if len(calls)==2 else reply(done)
  seen=[]
  with mock.patch('runpod_backend.requests.request',side_effect=request),mock.patch('runpod_backend.time.sleep'):
   outputs=self.backend.run(self.graph,lambda rid,p:seen.append((rid,p)),lambda:False)
  body=json.loads(calls[0][2]['data'])['input']
  self.assertEqual(sorted(body['files']),['henge/job/picture_1.png','henge/job/shot_000.mp4']);self.assertEqual(base64.b64decode(body['files']['henge/job/picture_1.png']),b'picture_1.png')
  self.assertEqual(calls[0][1],'https://api.runpod.ai/v2/ep/run');self.assertEqual(seen[1],('r1',{'class_type':'SamplerCustomAdvanced','value':3,'max':8}))
  self.backend.download(outputs['17']['videos'][0],self.root/'out.mp4');self.assertEqual((self.root/'out.mp4').read_bytes(),b'video')
  # The inventory cached from the reply feeds /health without waking a worker.
  self.assertEqual(self.backend.object_info()['LoraLoaderModelOnly']['input']['required']['lora_name'],[['a.safetensors']])
 def test_failed_job_raises_with_worker_error(self):
  responses=[reply({'id':'r1'}),reply({'status':'FAILED','error':'CUDA out of memory'})]
  with mock.patch('runpod_backend.requests.request',side_effect=responses),self.assertRaisesRegex(RuntimeError,'out of memory'):self.backend.run(self.graph,lambda *a:None,lambda:False)
 def test_cancel_stops_remote_job(self):
  calls=[]
  def request(method,url,**kw):calls.append(url);return reply({'id':'r1'})
  with mock.patch('runpod_backend.requests.request',side_effect=request),self.assertRaises(InterruptedError):self.backend.run(self.graph,lambda *a:None,lambda:True)
  self.assertEqual(calls[-1],'https://api.runpod.ai/v2/ep/cancel/r1')
 def test_large_media_goes_through_the_volume_in_chunks(self):
  big=bytes(range(256))*50_000  # 12.8 MB: over the request cap, so three 6 MB chunks
  (self.root/'input/henge/job/shot_000.mp4').write_bytes(big)
  volume={};inputs=[];result=b'r'*7_000_000
  def request(method,url,headers,timeout,**kw):
   if url.endswith('/run'):
    body=json.loads(kw['data'])['input'];inputs.append(body);op=body.get('op')
    if op=='stat':out={'sizes':{'henge/job/picture_1.png':len(b'picture_1.png')}}
    elif op=='put':
     data=base64.b64decode(body['data']);volume[body['path']]=volume.get(body['path'],b'')+data;out={'written':body['offset']+len(data)}
    elif op=='get':out={'data':base64.b64encode(result[body['offset']:body['offset']+body['length']]).decode(),'size':len(result)}
    else:out={'outputs':{'17':{'videos':[{'filename':'r.mp4','subfolder':'henge/job','type':'output'}]}},'files':{},'volume_outputs':{'henge/job/r.mp4':{'path':'out/x/henge/job/r.mp4','size':len(result)}}}
    self.pending.append(out);return reply({'id':'r'})
   return reply({'status':'COMPLETED','output':self.pending.pop(0)})
  self.pending=[]
  with mock.patch('runpod_backend.requests.request',side_effect=request),mock.patch('runpod_backend.time.sleep'):
   outputs=self.backend.run(self.graph,lambda *a:None,lambda:False)
   self.backend.download(outputs['17']['videos'][0],self.root/'out.mp4')
  ops=[i.get('op','run') for i in inputs]
  self.assertEqual(ops[:5],['stat','put','put','put','run'])  # picture already on the volume: only the shot is sent
  self.assertEqual(volume['henge/job/shot_000.mp4'],big);self.assertEqual(inputs[4]['files'],{});self.assertEqual(sorted(inputs[4]['volume_files']),['henge/job/picture_1.png','henge/job/shot_000.mp4'])
  self.assertEqual(ops[5:],['get','get']);self.assertEqual((self.root/'out.mp4').read_bytes(),result)

if __name__=='__main__':unittest.main()
