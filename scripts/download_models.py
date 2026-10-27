"""Download selected profiles from a local manifest; never publish model weights."""
import argparse,json,os,re,shutil,time
from pathlib import Path,PurePosixPath
from urllib.parse import unquote

HF_URL=re.compile(r'https://huggingface\.co/(?:(datasets|spaces)/)?([^/]+/[^/]+)/(?:resolve|blob)/([^/]+)/(.+?)(?:\?.*)?$')

def resolve_source(item):
    """Turn a Hugging Face `url` into repo fields (keeps the fast HF/Xet path)."""
    match=HF_URL.match(item.get('url') or '')
    if match and not item.get('repo_id'):
        kind,repo,revision,filename=match.groups()
        item.update(repo_id=repo,repo_type=(kind or 'models').rstrip('s'),revision=revision,filename=unquote(filename))
    return item

def download_url(url,dest,token=None):
    """Stream any HTTP(S) URL to dest, resuming a partial .part file."""
    import requests
    part=dest.with_name(dest.name+'.part');start=part.stat().st_size if part.exists() else 0
    headers={'Range':f'bytes={start}-'} if start else {}
    if token and 'huggingface.co' in url:headers['Authorization']='Bearer '+token
    with requests.get(url,headers=headers,stream=True,timeout=60,allow_redirects=True) as response:
        if response.status_code==416:part.replace(dest);return
        response.raise_for_status()
        mode='ab' if start and response.status_code==206 else 'wb'
        with open(part,mode) as handle:
            for chunk in response.iter_content(8<<20):handle.write(chunk)
    part.replace(dest)

# Old short local names of the published LoRAs (the same files). Sharpness is not here: the old file was a compressed
# variant, the published r64 is downloaded instead.
import json as _json
LEGACY={k:v for k,v in _json.loads(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','backend','legacy_loras.json')).read()).items() if '_lms_' not in k}

# Mode names expand to the profiles that hold their LoRAs, so "motion" gets every Motion Transfer model.
ALIASES={'motion':['motion_transfer','motion_transfer_tara','ffp'],'swap':['character'],'masks':['sam2d'],
         # names used before 2026-10-27
         'motion10500':['motion_transfer'],'motion4500':['motion_transfer_tara']}

def selected_models(manifest,profiles):
    profiles={q for p in profiles if p.strip() for q in ALIASES.get(p.strip(),[p.strip()])}
    known={p for item in manifest['models'] for p in item.get('profiles',[])}
    if profiles-known:raise ValueError('Unknown model profiles: '+', '.join(sorted(profiles-known)))
    active=profiles|{'common'}
    for item in manifest['models']:
        dest=PurePosixPath(item['destination'])
        if dest.is_absolute() or '..' in dest.parts:raise ValueError('Model destinations must stay inside the models folder')
        if active.intersection(item.get('profiles',[])):yield item

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',default=os.environ.get('HENGE_MODEL_MANIFEST','config/model-repos.example.json'));parser.add_argument('--models-dir',default=os.environ.get('HENGE_MODELS_DIR','/opt/ComfyUI/models'));parser.add_argument('--profiles',default=os.environ.get('HENGE_MODEL_PROFILES','character'));parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    manifest=json.loads(Path(args.manifest).read_text());root=Path(args.models_dir)
    # HENGE_MODEL_OVERRIDES='{"motion_transfer_v1":{"repo_id":"user/repo","filename":"x.safetensors"}}'
    # fills or replaces entries without editing the manifest (handy for RunPod env vars).
    overrides=json.loads(os.environ.get('HENGE_MODEL_OVERRIDES') or '{}')
    for item in manifest['models']:item.update(overrides.get(item['id'],{}))
    items=[resolve_source(item) for item in selected_models(manifest,args.profiles.split(','))]
    if args.dry_run:
        for item in items:print(item['id'],item.get('repo_id') and f"{item['repo_id']}:{item['filename']}" or item.get('url') or 'LOCAL/PRIVATE REPOSITORY REQUIRED','->',item['destination'])
        return
    from huggingface_hub import hf_hub_download
    token=os.environ.get('HF_TOKEN') or None
    if os.environ.get('HF_TOKEN_FILE'):token=Path(os.environ['HF_TOKEN_FILE']).read_text().strip()
    status=DownloadStatus(root,items)
    failed=[]
    for item in items:
        dest=root/item['destination'];dest.parent.mkdir(parents=True,exist_ok=True)
        # Installs from before 2026-10-27 stored the same files under short names: rename instead of downloading again.
        old=root/'loras'/LEGACY.get(item['destination'].removeprefix('loras/'),'-')
        if not dest.exists() and old.is_file() and old.stat().st_size>0:old.rename(dest);print('Renamed:',old.name,'->',dest.name,flush=True)
        if dest.is_file() and dest.stat().st_size>0:
            if has_keys(dest,item.get('require_keys')):print('Already installed:',item['id'],flush=True);status.set(item,'installed',total=dest.stat().st_size);continue
            print(f"Replacing {item['id']}: {dest.name} is an incompatible format",flush=True);dest.unlink()
        hub=item.get('repo_id') and item.get('filename')
        if not hub and not item.get('url'):
            message='No download link configured (set a url in the manifest or HENGE_MODEL_OVERRIDES).'
            print(f"Skipped {item['id']}: {message}",flush=True);status.set(item,'failed',error=message);failed.append(item['id']);continue
        staging=root/'.downloads'/item['id']
        try:
            total=remote_size(item,token)
            free=shutil.disk_usage(dest.parent).free
            if total and total>free:raise OSError(f'Not enough disk space: needs {total/1e9:.1f} GB, {free/1e9:.1f} GB free in {dest.parent}. Attach a larger volume at /workspace.')
            print(f"Downloading: {item['id']}"+(f' ({total/1e9:.2f} GB)' if total else ''),flush=True)
            status.set(item,'downloading',total=total,staging=str(staging if hub else dest.with_name(dest.name+'.part')))
            if hub:
                downloaded=hf_hub_download(repo_id=item['repo_id'],filename=item['filename'],repo_type=item.get('repo_type','model'),revision=item.get('revision','main'),local_dir=str(staging),token=token)
                os.replace(downloaded,dest);shutil.rmtree(staging,ignore_errors=True)
            else:download_url(item['url'],dest,token)
        except Exception as error:
            message=str(error).splitlines()[0]
            if ('401' in message or '403' in message) and not token:message='Access denied: this model is private and HF_TOKEN is not set.'
            elif 'No space left' in message:message=f'No space left on device in {dest.parent}. Attach a larger volume at /workspace.'
            print(f"Failed {item['id']}: {message}",flush=True);status.set(item,'failed',error=message);failed.append(item['id']);continue
        status.set(item,'installed',total=dest.stat().st_size)
        print('Installed:',item['destination'],flush=True)
    if failed:raise SystemExit('Models not installed: '+', '.join(failed))

def has_keys(path,keys):
    """True when a safetensors file contains every required tensor name."""
    if not keys:return True
    try:
        from safetensors import safe_open
        with safe_open(str(path),'pt') as handle:names=set(handle.keys())
    except Exception:return False
    return all(key in names for key in keys)

class DownloadStatus:
    """Shared with the bridge (/health) so the UI can show what is missing and why."""
    def __init__(self,root,items):
        self.path=root/'.henge-downloads.json'
        self.rows={item['id']:{'id':item['id'],'destination':item['destination'],'profiles':item.get('profiles',[]),'state':'pending'} for item in items}
        self.write()
    def set(self,item,state,**extra):
        row=self.rows[item['id']];row.update(state=state,**extra)
        if state!='downloading':row.pop('staging',None)
        self.write()
    def write(self):
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps({'updated':time.time(),'models':list(self.rows.values())},indent=1));tmp.replace(self.path)

def remote_size(item,token):
    try:
        if item.get('repo_id'):
            from huggingface_hub import get_hf_file_metadata,hf_hub_url
            return get_hf_file_metadata(hf_hub_url(item['repo_id'],item['filename'],repo_type=item.get('repo_type','model'),revision=item.get('revision','main')),token=token).size
        import requests
        return int(requests.head(item['url'],allow_redirects=True,timeout=30).headers.get('content-length') or 0) or None
    except Exception as error:
        if '401' in str(error) or '403' in str(error) or '404' in str(error):raise
        return None
if __name__=='__main__':main()
