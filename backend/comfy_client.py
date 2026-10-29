"""Files to and from ComfyUI through its HTTP API only (/upload/image, /view), so the bridge needs no
shared disk with ComfyUI: the same code drives a local ComfyUI, a remote one or a hosted backend.

Graph inputs are paths relative to the bridge's staging folder (henge/<job>/...). Before a graph runs,
every staged file it names is uploaded; a ComfyUI that stores it under another name (Comfy Cloud ignores
subfolders) gets the graph rewritten to that name."""
import copy,json
from pathlib import Path
import requests

# Inputs that hold a JSON list of staged paths rather than a single path.
LIST_INPUTS={('HengeLoadShot','pictures')}


def referenced_files(graph,staging):
    """Relative paths of staged files a graph reads (strings under henge/ that exist in staging)."""
    found=[]
    for node in graph.values():
        for name,value in node['inputs'].items():
            values=json.loads(value) if (node['class_type'],name) in LIST_INPUTS and isinstance(value,str) else [value]
            if (node['class_type'],name)==('HengeMolmo','task') and isinstance(value,str):
                # A Molmo2 task names its files inside the JSON: the video, the reference photos and the shot keyframes.
                task=json.loads(value);values=[task.get('video'),*(task.get('refs') or []),*(k.get('path') for k in task.get('keys') or [])]
            for v in values:
                if isinstance(v,str) and v.startswith('henge/') and (staging/v).is_file() and v not in found:found.append(v)
    return found


class ComfyFiles:
    def __init__(self,url,staging,headers=None):
        self.url=url.rstrip('/');self.staging=Path(staging);self.headers=headers or {};self.sent={}

    def upload(self,relative):
        """Upload one staged file; returns the name ComfyUI stored it under (input-relative)."""
        path=self.staging/relative;stamp=(path.stat().st_size,path.stat().st_mtime_ns)
        cached=self.sent.get((self.url,relative))
        if cached and cached[0]==stamp:return cached[1]
        subfolder,name=relative.rsplit('/',1)
        with path.open('rb') as f:
            r=requests.post(self.url+'/upload/image',files={'image':(name,f)},data={'subfolder':subfolder,'type':'input','overwrite':'true'},headers=self.headers,timeout=600)
        if not r.ok:raise RuntimeError(f'ComfyUI upload of {relative} failed: HTTP {r.status_code} {r.text[:500]}')
        stored=r.json();name=stored.get('name')
        if not name:raise RuntimeError(f'ComfyUI upload of {relative} returned {stored}')
        name=stored['subfolder']+'/'+name if stored.get('subfolder') else name
        self.sent[(self.url,relative)]=(stamp,name);return name

    def upload_graph_inputs(self,graph):
        """Upload what the graph reads; returns the graph with references to the stored names."""
        names={relative:self.upload(relative) for relative in referenced_files(graph,self.staging)}
        if all(k==v for k,v in names.items()):return graph
        graph=copy.deepcopy(graph)
        for node in graph.values():
            for key,value in node['inputs'].items():
                if (node['class_type'],key) in LIST_INPUTS and isinstance(value,str):node['inputs'][key]=json.dumps([names.get(v,v) for v in json.loads(value)])
                elif isinstance(value,str) and value in names:node['inputs'][key]=names[value]
        return graph

    def download(self,item,dest):
        """Fetch one output entry ({filename, subfolder, type}) into dest."""
        params={'filename':item['filename'],'subfolder':item.get('subfolder',''),'type':item.get('type','output')}
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_name(dest.name+'.part')
        r=requests.get(self.url+'/view',params=params,headers=self.headers,stream=True,timeout=600,allow_redirects=False)
        if r.is_redirect:
            # Hosted backends redirect to a signed storage URL: fetch it without our API credentials.
            r.close();r=requests.get(r.headers['location'],stream=True,timeout=600)
        with r:
            if not r.ok:raise RuntimeError(f"ComfyUI output {item['filename']} unavailable: HTTP {r.status_code}")
            with tmp.open('wb') as f:
                for chunk in r.iter_content(1<<20):f.write(chunk)
        tmp.replace(dest);return dest


def output_files(outputs,node=None,kind=None):
    """Output entries of a finished prompt, optionally of one node and one kind (images, videos)."""
    return [item for key,result in outputs.items() if node is None or key==str(node)
            for k,items in result.items() if (kind is None or k==kind) and isinstance(items,list)
            for item in items if isinstance(item,dict) and 'filename' in item]
