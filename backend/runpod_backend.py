"""Run Henge graphs on a RunPod Serverless endpoint (docker/worker_handler.py) instead of a ComfyUI URL.

Each graph is one request. Small media travel base64 inside it and its reply. RunPod caps a request at about
10 MB, so larger media go through the endpoint's network volume instead: "put" requests write them in chunks
(any worker can read the volume) and "get" requests read large results back. Nothing besides the endpoint and
its volume is involved. The worker's node/model inventory comes back with every reply and is cached, so /health
never wakes a worker."""
import base64,json,os,re,time
from pathlib import Path
import requests
from comfy_client import referenced_files

PAYLOAD_LIMIT=9_500_000
CHUNK=6_000_000


class RunPodBackend:
    def __init__(self,staging,state):
        endpoint=os.environ['RUNPOD_ENDPOINT_ID']
        self.base=os.environ.get('RUNPOD_API_BASE',f'https://api.runpod.ai/v2/{endpoint}').rstrip('/')
        self.headers={'Authorization':'Bearer '+os.environ.get('RUNPOD_API_KEY','')}
        self.staging=Path(staging);self.inventory_file=Path(state)/'runpod_inventory.json';self.received={};self.on_volume={}

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
        rels=referenced_files(graph,self.staging);volume=[]
        files={rel:base64.b64encode((self.staging/rel).read_bytes()).decode() for rel in rels}
        if len(json.dumps({'input':{'graph':graph,'files':files}}))>PAYLOAD_LIMIT:
            self.put_files(rels,on_status,cancelled);files={};volume=rels
        output=self.call({'graph':graph,'files':files,'volume_files':volume},on_status,cancelled)
        self.received=output.get('files') or {};self.on_volume=output.get('volume_outputs') or {}
        return output.get('outputs') or {}

    def put_files(self,rels,on_status,cancelled):
        """Write staged files to the volume in chunks, skipping those already there with the same size."""
        present=self.call({'op':'stat','paths':rels},None,cancelled).get('sizes',{})
        todo=[rel for rel in rels if present.get(rel)!=(self.staging/rel).stat().st_size]
        total=sum((self.staging/rel).stat().st_size for rel in todo);sent=0
        for rel in todo:
            path=self.staging/rel;size=path.stat().st_size
            with path.open('rb') as f:
                for offset in range(0,size,CHUNK):
                    data=f.read(CHUNK)
                    self.call({'op':'put','path':rel,'offset':offset,'size':size,'data':base64.b64encode(data).decode()},None,cancelled)
                    sent+=len(data);on_status('',{'message':f'Sending media to the serverless volume ({sent/1e6:.0f}/{total/1e6:.0f} MB)'})

    def call(self,payload,on_status,cancelled):
        """One request to the endpoint; returns its output. on_status may be None for transfer requests."""
        body=json.dumps({'input':payload})
        job=self.request('POST','/run',data=body,headers={'Content-Type':'application/json'},timeout=120)
        rid=job['id'];errors=0
        if on_status:on_status(rid,None)
        while True:
            if cancelled():
                self.cancel(rid);raise InterruptedError('Cancelled')
            try:status=self.status(rid);errors=0
            except (requests.RequestException,RuntimeError) as e:
                # A dropped poll does not lose the job. RunPod's API also answers 5xx for a while now and then (seen on
                # a completed job), so keep asking for about 3 minutes; an auth or not-found answer will not recover.
                if re.search(r'HTTP (401|403|404)\b',str(e)):raise
                errors+=1
                if errors>=12:raise
                time.sleep(min(5*errors,20));continue
            state=status.get('status')
            if state=='COMPLETED':
                output=status.get('output') or {}
                if output.get('inventory'):self.inventory_file.write_text(json.dumps(output['inventory']))
                return output
            if state in ('FAILED','CANCELLED','TIMED_OUT'):
                raise RuntimeError(f"Serverless job {state.lower()}: {str(status.get('error') or status.get('output'))[:1800]}")
            # IN_QUEUE while a worker starts (cold start loads the models); IN_PROGRESS carries progress_update data.
            if on_status:on_status(rid,status.get('output') if state=='IN_PROGRESS' and isinstance(status.get('output'),dict) else {'queued':True} if state=='IN_QUEUE' else None)
            time.sleep(2 if on_status else .5)

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

    # Same file interface as comfy_client.ComfyFiles: inputs travel with the request, outputs with the reply.
    def upload_graph_inputs(self,graph):return graph

    def download(self,item,dest):
        key=(item.get('subfolder','')+'/'+item['filename']).lstrip('/')
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
        if key in self.received:dest.write_bytes(base64.b64decode(self.received[key]));return dest
        if key not in self.on_volume:raise RuntimeError(f'Serverless reply has no {key}')
        remote=self.on_volume[key];tmp=dest.with_name(dest.name+'.part')
        with tmp.open('wb') as f:
            for offset in range(0,remote['size'],CHUNK):
                for attempt in range(3):
                    # A failed chunk request is simply asked again: the file stays on the volume.
                    try:f.write(base64.b64decode(self.call({'op':'get','path':remote['path'],'offset':offset,'length':CHUNK},None,lambda:False)['data']));break
                    except (requests.RequestException,RuntimeError):
                        if attempt==2:raise
                        time.sleep(10)
        tmp.replace(dest);return dest
