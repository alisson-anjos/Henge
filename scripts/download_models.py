"""Download selected profiles from a local manifest; never publish model weights."""
import argparse,json,os,re
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

def selected_models(manifest,profiles):
    profiles={p.strip() for p in profiles if p.strip()}
    known={p for item in manifest['models'] for p in item.get('profiles',[])}
    if profiles-known:raise ValueError('Unknown model profiles: '+', '.join(sorted(profiles-known)))
    active=profiles|{'common'}
    for item in manifest['models']:
        dest=PurePosixPath(item['destination'])
        if dest.is_absolute() or '..' in dest.parts:raise ValueError('Model destinations must stay inside the models folder')
        if active.intersection(item.get('profiles',[])):yield item

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',default=os.environ.get('KAWARIMI_MODEL_MANIFEST','config/model-repos.example.json'));parser.add_argument('--models-dir',default=os.environ.get('KAWARIMI_MODELS_DIR','/opt/ComfyUI/models'));parser.add_argument('--profiles',default=os.environ.get('KAWARIMI_MODEL_PROFILES','character'));parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    manifest=json.loads(Path(args.manifest).read_text());root=Path(args.models_dir)
    # KAWARIMI_MODEL_OVERRIDES='{"motion10500":{"repo_id":"user/repo","filename":"x.safetensors"}}'
    # fills or replaces entries without editing the manifest (handy for RunPod env vars).
    overrides=json.loads(os.environ.get('KAWARIMI_MODEL_OVERRIDES') or '{}')
    for item in manifest['models']:item.update(overrides.get(item['id'],{}))
    items=[resolve_source(item) for item in selected_models(manifest,args.profiles.split(','))]
    if args.dry_run:
        for item in items:print(item['id'],item.get('repo_id') and f"{item['repo_id']}:{item['filename']}" or item.get('url') or 'LOCAL/PRIVATE REPOSITORY REQUIRED','->',item['destination'])
        return
    from huggingface_hub import hf_hub_download
    token=os.environ.get('HF_TOKEN') or None
    if os.environ.get('HF_TOKEN_FILE'):token=Path(os.environ['HF_TOKEN_FILE']).read_text().strip()
    failed=[]
    for item in items:
        dest=root/item['destination'];dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.is_file() and dest.stat().st_size>0:print('Already installed:',item['id'],flush=True);continue
        hub=item.get('repo_id') and item.get('filename')
        if not hub and not item.get('url'):
            print(f"Skipped {item['id']}: set a url (or repo_id/filename) in the manifest or KAWARIMI_MODEL_OVERRIDES, or mount {dest}. This artifact is not publicly bundled.",flush=True);failed.append(item['id']);continue
        print('Downloading:',item['id'],flush=True)
        try:
            if hub:
                staging=root/'.downloads'/item['id']
                downloaded=hf_hub_download(repo_id=item['repo_id'],filename=item['filename'],repo_type=item.get('repo_type','model'),revision=item.get('revision','main'),local_dir=str(staging),token=token)
                os.replace(downloaded,dest)
            else:download_url(item['url'],dest,token)
        except Exception as error:print(f"Failed {item['id']}: {error}",flush=True);failed.append(item['id']);continue
        print('Installed:',item['destination'],flush=True)
    if failed:raise SystemExit('Models not installed: '+', '.join(failed))
if __name__=='__main__':main()
