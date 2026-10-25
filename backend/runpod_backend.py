"""Run Henge graphs on a RunPod Serverless endpoint (docker/worker_handler.py) instead of a ComfyUI URL.

Each graph is one request: the staged files it reads travel base64 in the request, its output files come back
base64 in the response. RunPod caps a /run payload (~10 MB), so this suits short clips; larger media needs the
network volume's S3 API or a bucket (not wired yet). The worker's node/model inventory comes back with every
response and is cached, so /health never wakes a worker."""
import base64,json,os,time
from pathlib import Path
import requests
from comfy_client import referenced_files

PAYLOAD_LIMIT=9_500_000


class RunPodBackend:
    def __init__(self,staging,state):
        endpoint=os.environ['RUNPOD_ENDPOINT_ID']
        self.base=os.environ.get('RUNPOD_API_BASE',f'https://api.runpod.ai/v2/{endpoint}').rstrip('/')
        self.headers={'Authorization':'Bearer '+os.environ.get('RUNPOD_API_KEY','')}
        self.staging=Path(staging);self.inventory_file=Path(state)/'runpod_inventory.json';self.received={}

    def request(self,method,path,**kw):
        r=requests.request(method,self.base+path,headers={**self.headers,**kw.pop('headers',{})},timeout=kw.pop('timeout',60),**kw)
        if not r.ok:raise RuntimeError(f'RunPod {path} HTTP {r.status_code}: {r.text[:800]}')
        return r.json()

    def online(self):
        try:self.request('GET','/health',timeout=10);return True
        except Exception:return False

    def inventory(self):
        try:return json.loads(self.inventory_file.read_text())
        except (OSError,ValueError):return None

    def object_info(self):
        """The slice of /object_info that /health reads, rebuilt from the cached inventory ({} before the first job)."""
        inv=self.inventory()
        if not inv:return {}
        info={name:{'input':{'required':{}}} for name in inv['nodes']}
        for key,options in inv['choices'].items():
            node,name=key.split('.',1)
            info.setdefault(node,{'input':{'required':{}}})['input']['required'][name]=[options]
        return info

    def run(self,graph,on_status,cancelled):
        """Submit one graph and wait. on_status(request_id, progress_or_None); cancelled() -> bool."""
        files={rel:base64.b64encode((self.staging/rel).read_bytes()).decode() for rel in referenced_files(graph,self.staging)}
        body=json.dumps({'input':{'graph':graph,'files':files}})
        if len(body)>PAYLOAD_LIMIT:raise ValueError(f'Serverless request is {len(body)/1e6:.1f} MB; RunPod accepts about 10 MB. Use a shorter or lower-resolution clip.')
        job=self.request('POST','/run',data=body,headers={'Content-Type':'application/json'},timeout=120)
        rid=job['id'];on_status(rid,None);errors=0
        while True:
            if cancelled():
                self.cancel(rid);raise InterruptedError('Cancelled')
            try:status=self.status(rid);errors=0
            except (requests.RequestException,RuntimeError):
                # A dropped poll does not lose the job: retry a few times before giving up on it.
                errors+=1
                if errors>=5:raise
                time.sleep(5);continue
            state=status.get('status')
            if state=='COMPLETED':
                output=status.get('output') or {}
                if output.get('inventory'):self.inventory_file.write_text(json.dumps(output['inventory']))
                self.received=output.get('files') or {}
                return output.get('outputs') or {}
            if state in ('FAILED','CANCELLED','TIMED_OUT'):
                raise RuntimeError(f"Serverless job {state.lower()}: {str(status.get('error') or status.get('output'))[:1800]}")
            # IN_QUEUE while a worker starts (cold start loads the models); IN_PROGRESS carries progress_update data.
            on_status(rid,status.get('output') if state=='IN_PROGRESS' and isinstance(status.get('output'),dict) else {'queued':True} if state=='IN_QUEUE' else None)
            time.sleep(2)

    def status(self,rid):
        # RunPod answers GET /status; the SDK's local test server (--rp_serve_api) only POST.
        # The local server may also hold the request until the job ends, hence the long timeout.
        try:return self.request('GET','/status/'+rid,timeout=900)
        except RuntimeError as e:
            if 'HTTP 405' not in str(e):raise
            return self.request('POST','/status/'+rid,timeout=900)

    def cancel(self,rid):
        try:self.request('POST','/cancel/'+rid,timeout=20)
        except Exception:pass

    # Same file interface as comfy_client.ComfyFiles: inputs travel inside the request, outputs inside the reply.
    def upload_graph_inputs(self,graph):return graph

    def download(self,item,dest):
        key=(item.get('subfolder','')+'/'+item['filename']).lstrip('/')
        if key not in self.received:raise RuntimeError(f'Serverless reply has no {key}')
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(base64.b64decode(self.received[key]));return dest
