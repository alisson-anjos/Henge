"""Explicit downloads of catalogued weights; shared by local bridge and Serverless worker. No torch imports."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
from urllib.parse import quote, urlsplit
import requests
from filelock import FileLock, Timeout

ROOT=Path(__file__).resolve().parents[1]
FOLDERS={'diffusion_models','text_encoders','vae','vae_approx','loras','latent_upscale_models','background_removal','sam','sam3','sam3d','sams','checkpoints','licenses','detection','geometry_estimation'}


def source_url(item):
    if item.get('repo_id') and item.get('filename'):
        repo=item['repo_id'];revision=item.get('revision','main');name=item['filename']
        if not re.fullmatch(r'[\w.-]+/[\w.-]+',repo):raise ValueError('Invalid model repository')
        return f'https://huggingface.co/{repo}/resolve/{quote(revision,safe="")}/{quote(name,safe="/")}'
    url=item.get('url','')
    if urlsplit(url).scheme!='https' or urlsplit(url).hostname!='huggingface.co':raise ValueError('Only catalogued Hugging Face downloads are supported')
    return url.replace('/blob/','/resolve/',1)


def destination(root,item):
    relative=PurePosixPath(item['destination'])
    if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0] not in FOLDERS:
        raise ValueError('Invalid model destination')
    path=(root/str(relative)).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Model destination escapes models folder')
    return path


def catalog(revision=None):
    if revision:
        if not re.fullmatch(r'[0-9a-f]{40}',revision):raise ValueError('Invalid catalog revision')
        response=requests.get(f'https://raw.githubusercontent.com/alisson-anjos/Henge/{revision}/config/model-repos.example.json',timeout=20)
        response.raise_for_status()
        if len(response.content)>4_000_000:raise ValueError('Model catalog is too large')
        return response.json()
    return json.loads((ROOT/'config/model-repos.example.json').read_text())


def selected(manifest,model_id):
    by_id={item['id']:item for item in manifest['models']}
    if model_id not in by_id:raise ValueError('Model is not in this catalog; refresh Models')
    ids=[model_id]
    if model_id in ('turbo_pika6','turbo_pika6_kijai'):ids+=['pika_license','pika_notice','pika_upstream_license']
    return [by_id[key] for key in ids]


def installed(root,item):
    return destination(root,item).is_file() and destination(root,item).stat().st_size>0


def install(root,manifest,model_id,progress,cancelled=lambda:False):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    items=selected(manifest,model_id)
    # Validate the complete pack before making any network request or writing a file.
    for item in items:destination(root,item);source_url(item)
    try:
        with FileLock(str(root/'.henge-model-install.lock'),timeout=0):
            results=[]
            for item in items:
                if cancelled():raise InterruptedError('Installation cancelled')
                path=destination(root,item);path.parent.mkdir(parents=True,exist_ok=True)
                if installed(root,item):
                    results.append({'id':item['id'],'state':'installed'});continue
                part=path.with_name(path.name+'.part');offset=part.stat().st_size if part.exists() else 0
                if part.resolve().parent!=path.parent or part.is_symlink():raise ValueError('Invalid partial model path')
                headers={'Range':f'bytes={offset}-'} if offset else {}
                token=os.environ.get('HF_TOKEN','')
                if token and not token.startswith('{{'):headers['Authorization']='Bearer '+token
                response=requests.get(source_url(item),headers=headers,stream=True,timeout=(20,90))
                if response.status_code==416:
                    response.close();headers.pop('Range',None);offset=0
                    response=requests.get(source_url(item),headers=headers,stream=True,timeout=(20,90))
                with response:
                    if response.status_code in (401,403):raise ValueError('Model access denied: accept its license and configure HF_TOKEN on the download host')
                    response.raise_for_status()
                    if response.status_code==206:
                        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
                        if not match or int(match[1])!=offset:raise ValueError('Invalid resumed model response')
                        total=int(match[3])
                    else:offset=0;total=int(response.headers.get('Content-Length','0'))
                    if total and total-offset>shutil.disk_usage(path.parent).free:raise ValueError('Not enough free space in the models volume')
                    received=offset;last=0
                    with part.open('ab' if offset else 'wb') as output:
                        for chunk in response.iter_content(4<<20):
                            if cancelled():raise InterruptedError('Installation cancelled')
                            if not chunk:continue
                            output.write(chunk);received+=len(chunk)
                            if time.monotonic()-last>=1:
                                progress({'stage':'downloading','model_id':model_id,'file':item['id'],'received':received,'total':total});last=time.monotonic()
                    if not received or (total and received!=total):raise ValueError('Incomplete model download; retry resumes the partial file')
                if cancelled():raise InterruptedError('Installation cancelled')
                digest=item.get('sha256')
                if digest:
                    progress({'stage':'verifying','model_id':model_id,'file':item['id'],'received':received,'total':received})
                    with part.open('rb') as data:actual=hashlib.file_digest(data,'sha256').hexdigest()
                    if actual!=digest:part.unlink();raise ValueError('Model checksum mismatch; retry the download')
                if cancelled():raise InterruptedError('Installation cancelled')
                part.replace(path);results.append({'id':item['id'],'state':'installed'})
            progress({'stage':'refreshing','model_id':model_id})
            return {'model_id':model_id,'files':results}
    except Timeout:raise ValueError('Another model installation is using this volume; retry when it finishes')
