"""Download selected profiles from a local manifest; never publish model weights."""
import argparse,json,os
from pathlib import Path,PurePosixPath

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
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',default=os.environ.get('KAGEMANE_MODEL_MANIFEST','config/model-repos.example.json'));parser.add_argument('--models-dir',default=os.environ.get('KAGEMANE_MODELS_DIR','/opt/ComfyUI/models'));parser.add_argument('--profiles',default=os.environ.get('KAGEMANE_MODEL_PROFILES','character'));parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    manifest=json.loads(Path(args.manifest).read_text());root=Path(args.models_dir)
    items=list(selected_models(manifest,args.profiles.split(',')))
    if args.dry_run:
        for item in items:print(item['id'],item.get('repo_id') or 'LOCAL/PRIVATE REPOSITORY REQUIRED','->',item['destination'])
        return
    from huggingface_hub import hf_hub_download
    token=os.environ.get('HF_TOKEN') or None
    if os.environ.get('HF_TOKEN_FILE'):token=Path(os.environ['HF_TOKEN_FILE']).read_text().strip()
    for item in items:
        dest=root/item['destination'];dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.is_file() and dest.stat().st_size>0:print('Already installed:',item['id'],flush=True);continue
        if not item.get('repo_id') or not item.get('filename'):raise ValueError(f"Configure a repository/file for {item['id']} in your local model manifest, or mount {dest}. This artifact is not publicly bundled.")
        print('Downloading:',item['id'],flush=True)
        staging=root/'.downloads'/item['id']
        downloaded=hf_hub_download(repo_id=item['repo_id'],filename=item['filename'],repo_type=item.get('repo_type','model'),revision=item.get('revision','main'),local_dir=str(staging),token=token)
        os.replace(downloaded,dest)
        print('Installed:',item['destination'],flush=True)
if __name__=='__main__':main()
