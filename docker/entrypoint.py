"""Fetch configured weights, then supervise ComfyUI, bridge and web UI.

On RunPod (or any host that mounts a volume at /workspace), models, inputs,
outputs and job state live on that volume so pods can be stopped, recreated or
moved to another GPU without re-downloading ~60 GB of weights.
"""
import os,shlex,shutil,signal,subprocess,sys,time
from pathlib import Path
APP=Path('/app');COMFY=Path(os.environ.get('COMFY_ROOT','/opt/ComfyUI'));processes=[];stopping=False

def shutdown(*_):
    global stopping
    stopping=True
    for p in reversed(processes):
        if p.poll() is None:p.terminate()

def link_to_workspace(workspace):
    """Point ComfyUI's models/input/output and the job state at the volume."""
    root=workspace/'kawarimi';root.mkdir(parents=True,exist_ok=True)
    for name in ['models','input','output']:
        target=root/name;source=COMFY/name;target.mkdir(parents=True,exist_ok=True)
        if source.is_symlink():source.unlink()
        elif source.is_dir():
            # Keep the image's placeholder folders (and anything baked in) on first boot.
            for item in source.iterdir():
                if not (target/item.name).exists():shutil.move(str(item),str(target/item.name))
            shutil.rmtree(source)
        source.symlink_to(target,target_is_directory=True)
    os.environ['KAWARIMI_DATA_DIR']=str(root/'state/jobs');Path(os.environ['KAWARIMI_DATA_DIR']).mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('HF_HOME',str(root/'huggingface'))
    manifest=root/'model-repos.json'
    if manifest.is_file() and 'KAWARIMI_MODEL_MANIFEST_FORCE' not in os.environ:
        os.environ['KAWARIMI_MODEL_MANIFEST']=str(manifest)
    print('[kawarimi] persistent data on',root,flush=True)

def start_sshd():
    """RunPod convention: PUBLIC_KEY env enables SSH over the exposed TCP 22."""
    key=os.environ.get('PUBLIC_KEY')
    if not key or not shutil.which('sshd'):return
    ssh=Path('/root/.ssh');ssh.mkdir(mode=0o700,exist_ok=True)
    (ssh/'authorized_keys').write_text(key.strip()+'\n');(ssh/'authorized_keys').chmod(0o600)
    subprocess.run(['ssh-keygen','-A'],check=False)
    Path('/run/sshd').mkdir(exist_ok=True)
    subprocess.Popen(['/usr/sbin/sshd'])
    print('[kawarimi] sshd started',flush=True)

def main():
    signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
    workspace=Path(os.environ.get('KAWARIMI_WORKSPACE','/workspace'))
    if workspace.is_dir() and os.environ.get('KAWARIMI_WORKSPACE')!='off':link_to_workspace(workspace)
    start_sshd()
    # A model that fails to download (e.g. a private LoRA without HF_TOKEN) must not
    # put the pod into a restart loop; /health reports the missing profile instead.
    result=subprocess.run([sys.executable,str(APP/'scripts/download_models.py')],cwd=APP)
    if result.returncode:print('[kawarimi] WARNING: some models failed to download; affected profiles stay unavailable',flush=True)
    comfy_host='0.0.0.0' if os.environ.get('KAWARIMI_EXPOSE_COMFY')=='1' else '127.0.0.1'
    comfy_args=shlex.split(os.environ.get('KAWARIMI_COMFY_ARGS','--lowvram'))
    commands=[([sys.executable,'main.py','--listen',comfy_host,'--port','8189','--preview-method','taesd',*comfy_args,'--disable-all-custom-nodes','--whitelist-custom-nodes','kawarimi','bfsnodes'],COMFY),([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port','8766'],APP/'backend'),(['node','node_modules/next/dist/bin/next','start','--hostname','0.0.0.0','--port','8188'],APP)]
    for command,cwd in commands:processes.append(subprocess.Popen(command,cwd=cwd))
    try:
        while not stopping:
            if any(p.poll() is not None for p in processes):raise RuntimeError('A Kawarimi service stopped; inspect the container logs')
            time.sleep(1)
    finally:
        shutdown()
        for p in processes:
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:p.kill()
if __name__=='__main__':main()
