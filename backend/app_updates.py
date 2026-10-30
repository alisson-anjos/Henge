"""Cached public update/catalog metadata. Reading this never wakes a GPU worker."""
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import requests

ROOT=Path(__file__).resolve().parents[1]
REPO='alisson-anjos/Henge'
API=f'https://api.github.com/repos/{REPO}'
RAW=f'https://raw.githubusercontent.com/{REPO}'
LOCK=threading.Lock()
CACHE={}


def current_version():
    value=os.environ.get('HENGE_BUILD_SHA','')
    if re.fullmatch(r'[0-9a-f]{40}',value):return value
    try:return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,stderr=subprocess.DEVNULL,timeout=3,text=True).strip()
    except (OSError,subprocess.SubprocessError):return None


def fetch(url):
    response=requests.get(url,timeout=12,headers={'Accept':'application/vnd.github+json','User-Agent':'Henge-update-check'})
    response.raise_for_status()
    if len(response.content)>4_000_000:raise ValueError('Update metadata is too large')
    return response


def latest_published():
    """The commit of the newest successful image build (a v* release tag or a manual run): updating to a newer
    commit is not possible until it is released."""
    runs=fetch(API+'/actions/workflows/docker.yml/runs?status=success&per_page=1').json().get('workflow_runs') or []
    sha=runs[0].get('head_sha') if runs else None
    return sha if isinstance(sha,str) and re.fullmatch(r'[0-9a-f]{40}',sha) else None


def docs_only(path):
    """Changes that ship nothing to a running Henge (the in-app changelog is read from GitHub anyway)."""
    return path.endswith('.md') or path.startswith('docs/')


def snapshot():
    with LOCK:
        if CACHE and time.monotonic()-CACHE['at']<300:return CACHE['data']
        current=current_version()
        data={'current':current,'latest':None,'published':None,'update_available':False,'check_ok':False,
              'changelog':(ROOT/'CHANGELOG.md').read_text()[:24000],
              'changelog_url':f'https://github.com/{REPO}/blob/main/CHANGELOG.md',
              'update_url':f'https://github.com/{REPO}#updating','catalog_revision':None,
              'manifest':json.loads((ROOT/'config/model-repos.example.json').read_text())}
        try:
            latest=fetch(API+'/commits/main').json()['sha']
            if not re.fullmatch(r'[0-9a-f]{40}',latest):raise ValueError('Invalid upstream revision')
            # Pin changelog and model catalog to the same revision, rather than racing moving main URLs.
            manifest=fetch(f'{RAW}/{latest}/config/model-repos.example.json').json()
            if not isinstance(manifest.get('models'),list):raise ValueError('Invalid model catalog')
            data.update(latest=latest,catalog_revision=latest,manifest=manifest,
                        changelog=fetch(f'{RAW}/{latest}/CHANGELOG.md').text[:24000],check_ok=True)
            # Offer an update only to an image that exists and that changes something besides documentation.
            try:published=latest_published()
            except (requests.RequestException,ValueError,KeyError,TypeError):published=None
            target=published or latest;data['published']=target
            if current and current!=target:
                comparison=fetch(f'{API}/compare/{current}...{target}').json()
                files=[f.get('filename','') for f in comparison.get('files') or []]
                data['update_available']=comparison.get('status')=='ahead' and (not files or not all(map(docs_only,files)))
        except (requests.RequestException,ValueError,KeyError,TypeError):pass
        revision=data.get('latest') or 'main'
        data['changelog']=re.sub(r'\]\((?!https?://|#)([^)]+)\)',lambda match: f'](https://github.com/{REPO}/blob/{revision}/'+match[1]+')',data['changelog'])
        CACHE.update(at=time.monotonic(),data=data)
        return data
