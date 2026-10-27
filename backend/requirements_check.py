"""What each mode needs on disk, merged with the downloader's live status.

The downloader (scripts/download_models.py) writes models/.henge-downloads.json;
this module turns it into the checklist the UI shows while the pod is preparing.
"""
import json,os,shutil
from pathlib import Path

LEGACY_LORAS=json.loads(Path(__file__).with_name('legacy_loras.json').read_text())

# Matched on the file name's ending, so both the published names (minimax_h3_…) and the old short ones get a label.
ADAPTER_LABELS={'training_adapter_v2.safetensors':'Motion training adapter V2','dmd_ref2va_8step.safetensors':'Turbo LoRA · DMD 8-step',
                'dmd_ref2va_8step_turbo_pruned.safetensors':'Turbo LoRA · DMD 8-step'}

def adapter_label(path):
    name=path.rsplit('/',1)[-1]
    return next((label for end,label in ADAPTER_LABELS.items() if name.endswith(end)),'Adapter LoRA')

def base_files():
    planner=os.environ.get('HENGE_VLM_CLIP','qwen3.5_9b_w4a8_gptq.safetensors')
    return [
        ('h3','MiniMax-H3 video model','diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors'),
        ('h3_text','H3 text encoder','text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors'),
        ('h3_vae','H3 video VAE','vae/minimax_h3_video_vae_fp16.safetensors'),
        ('planner','Prompt planner (VLM)','text_encoders/'+planner),
        ('preview','Live preview (TAEH3)','vae_approx/taeh3.safetensors'),
        ('bg_removal','Reference background removal (BiRefNet)','background_removal/birefnet.safetensors'),
    ]

def _folder_size(path):
    path=Path(path)
    if path.is_file():return path.stat().st_size
    if not path.is_dir():return 0
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())

def _status(models_dir):
    try:return json.loads((models_dir/'.henge-downloads.json').read_text())
    except (OSError,ValueError):return {}

def check(models_dir,models):
    """Return (requirements, mode_ready, setup) for /health."""
    models_dir=Path(models_dir);status=_status(models_dir)
    by_destination={row['destination']:row for row in status.get('models',[])}
    rows={}
    def installed_path(relative):
        path=models_dir/relative
        if path.is_file():return path
        if relative.startswith('loras/'):
            legacy=LEGACY_LORAS.get(relative.removeprefix('loras/'))
            if legacy and (models_dir/'loras'/legacy).is_file():return models_dir/'loras'/legacy
        return path
    def add(key,label,relative,group):
        if relative in rows:rows[relative]['groups'].append(group);return
        row={'id':key,'label':label,'file':relative,'groups':[group]}
        path=installed_path(relative);download=by_destination.get(relative,{})
        if path.is_file() and path.stat().st_size>0:row.update(state='installed',total=path.stat().st_size)
        else:
            row['state']=download.get('state') if download.get('state') in ('pending','downloading','failed') else 'missing'
            if download.get('total'):row['total']=download['total']
            if download.get('error'):row['error']=download['error']
            if row['state']=='downloading' and download.get('staging'):row['downloaded']=_folder_size(download['staging'])
        rows[relative]=row
    for key,label,relative in base_files():add(key,label,relative,'common')
    for profile,model in models.items():
        lora='loras/'+model['lora']
        # Profiles the downloader was not asked to fetch (e.g. local-only mixes) stay out of the checklist;
        # they still report available=False in /health.
        if lora not in by_destination and not installed_path(lora).is_file():continue
        if model.get('adapter'):
            adapter=model['adapter'];add(profile+'_adapter',adapter_label(adapter),'loras/'+adapter,profile)
        add(profile+'_lora',f"{model.get('label',profile)} LoRA",lora,profile)
        for key,label,relative in model.get('files',[]):add(profile+'_'+key,label,relative,profile)
    requirements=list(rows.values())
    def ok(group):
        needed=[r for r in requirements if group in r['groups']]
        return bool(needed) and all(r['state']=='installed' for r in needed)
    base_ready=ok('common')
    mode_ready={profile:base_ready and ok(profile) for profile in models}
    listed={g for r in requirements for g in r['groups']}-{'common'}
    active=any(r['state'] in ('pending','downloading') for r in requirements)
    try:usage=shutil.disk_usage(models_dir);free=round(usage.free/1e9,1)
    except OSError:free=None
    workspace=Path(os.environ.get('HENGE_WORKSPACE','/workspace'))
    setup={'downloading':active,'base_ready':base_ready,'all_ready':base_ready and not active and all(mode_ready[p] for p in listed),'free_gb':free,
           'persistent_volume':workspace.is_mount() if workspace.exists() else None}
    return requirements,mode_ready,setup
