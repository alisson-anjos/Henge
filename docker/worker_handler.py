"""RunPod Serverless worker: runs one Henge ComfyUI API graph per request.

Request input:  {"graph": {...API graph...}, "files": {"henge/<job>/x.mp4": "<base64>", ...}}
                or {"op": "inventory"} to list nodes and model choices without running anything.
Response:       {"outputs": <ComfyUI history outputs>, "files": {"<subfolder>/<filename>": "<base64>"},
                 "inventory": {...}}
Progress:       runpod progress_update with {"node", "class_type", "value", "max"}.

ComfyUI runs next to this handler on 127.0.0.1:8189 (started by docker/entrypoint.py with HENGE_ROLE=worker);
models come from the network volume at /runpod-volume/henge/models.
"""
import asyncio,base64,json,os,time,uuid
from pathlib import Path
import aiohttp,requests,runpod

URL=os.environ.get('COMFY_BASE_URL','http://127.0.0.1:8189').rstrip('/')
COMFY=Path(os.environ.get('COMFY_ROOT','/opt/ComfyUI'))
# What the bridge's /health needs to know: which nodes exist and which model files ComfyUI lists.
CHOICES=[('LoraLoaderModelOnly','lora_name'),('UNETLoader','unet_name'),('MinimaxH3LatentUpscaler3D','model_name')]
INVENTORY=None


def wait_for_comfy(timeout=1800):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            if requests.get(URL+'/system_stats',timeout=5).ok:return
        except requests.RequestException:pass
        time.sleep(2)
    raise RuntimeError('ComfyUI did not start')


def inventory():
    global INVENTORY
    if INVENTORY is None:
        info=requests.get(URL+'/object_info',timeout=60).json()
        def choices(node,name):
            spec=info.get(node,{}).get('input',{}).get('required',{}).get(name,[[]])
            if spec and isinstance(spec[0],list):return spec[0]
            return spec[1].get('options',[]) if len(spec)>1 and isinstance(spec[1],dict) else []
        INVENTORY={'nodes':sorted(info),'choices':{f'{node}.{name}':choices(node,name) for node,name in CHOICES}}
    return INVENTORY


def staged(root,relative):
    p=(root/relative).resolve()
    if not relative.startswith('henge/') or not p.is_relative_to(root.resolve()):raise ValueError(f'Refusing path {relative}')
    return p


async def run(job,graph):
    client='henge-worker-'+uuid.uuid4().hex
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(URL.replace('http://','ws://')+'/ws?clientId='+client,heartbeat=30) as ws:
            async with session.post(URL+'/prompt',json={'prompt':graph,'client_id':client}) as res:
                reply=await res.json()
                if res.status!=200:raise ValueError(json.dumps(reply)[:1800])
            pid=reply['prompt_id'];last_poll=0
            while True:
                try:
                    message=await ws.receive(timeout=1)
                    if message.type==aiohttp.WSMsgType.TEXT:
                        event=json.loads(message.data);data=event.get('data',{})
                        if data.get('prompt_id',pid)==pid and event.get('type') in ('executing','progress'):
                            node=str(data.get('node'))
                            if node in graph:
                                runpod.serverless.progress_update(job,{'node':node,'class_type':graph[node]['class_type'],'value':data.get('value'),'max':data.get('max')})
                    elif message.type in (aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.ERROR):raise RuntimeError('ComfyUI progress connection closed')
                except asyncio.TimeoutError:pass
                if time.monotonic()-last_poll>=2:
                    last_poll=time.monotonic()
                    async with session.get(URL+'/history/'+pid) as response:history=await response.json()
                    if pid in history:
                        entry=history[pid]
                        if entry.get('status',{}).get('status_str')=='error':
                            errors=[m[1].get('exception_message','Execution failed') for m in entry['status'].get('messages',[]) if m[0]=='execution_error']
                            raise RuntimeError('; '.join(errors) or 'ComfyUI execution failed')
                        return entry.get('outputs',{})


async def handler(job):
    request=job['input']
    if request.get('op')=='inventory':return {'inventory':inventory()}
    graph=request['graph'];inputs=COMFY/'input';outputs_dir=COMFY/'output'
    for relative,data in (request.get('files') or {}).items():
        p=staged(inputs,relative);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))
    outputs=await run(job,graph)
    files={}
    for result in outputs.values():
        for items in result.values():
            for item in items if isinstance(items,list) else []:
                if isinstance(item,dict) and item.get('type')=='output' and 'filename' in item:
                    key=(item.get('subfolder','')+'/'+item['filename']).lstrip('/')
                    files[key]=base64.b64encode((outputs_dir/key).read_bytes()).decode()
    return {'outputs':outputs,'files':files,'inventory':inventory()}


if __name__=='__main__':
    wait_for_comfy();inventory()
    runpod.serverless.start({'handler':handler})
