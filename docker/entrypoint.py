"""Fetch configured weights, then supervise ComfyUI, bridge and web UI.

HENGE_ROLE picks what runs: `all` (default: ComfyUI + bridge + UI, one pod), `worker` (ComfyUI + the RunPod
Serverless handler; models from the network volume at /runpod-volume) or `ui` (bridge + UI only, no GPU; the
bridge drives a remote ComfyUI or, with HENGE_BACKEND=runpod, a serverless endpoint).

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

def link_to_workspace(workspace,names=('models','input','output')):
    """Point ComfyUI's models/input/output and the job state at the volume."""
    root=workspace/'henge';root.mkdir(parents=True,exist_ok=True)
    for name in names:
        target=root/name;source=COMFY/name;target.mkdir(parents=True,exist_ok=True)
        if source.is_symlink():source.unlink()
        elif source.is_dir():
            # Keep the image's placeholder folders (and anything baked in) on first boot.
            for item in source.iterdir():
                if not (target/item.name).exists():shutil.move(str(item),str(target/item.name))
            shutil.rmtree(source)
        source.symlink_to(target,target_is_directory=True)
    os.environ['HENGE_DATA_DIR']=str(root/'state/jobs');Path(os.environ['HENGE_DATA_DIR']).mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('HF_HOME',str(root/'huggingface'))
    manifest=root/'model-repos.json'
    if manifest.is_file() and 'HENGE_MODEL_MANIFEST_FORCE' not in os.environ:
        os.environ['HENGE_MODEL_MANIFEST']=str(manifest)
    print('[henge] persistent data on',root,flush=True)

def start_sshd():
    """RunPod convention: PUBLIC_KEY env enables SSH over the exposed TCP 22."""
    key=os.environ.get('PUBLIC_KEY')
    if not key or not shutil.which('sshd'):return
    ssh=Path('/root/.ssh');ssh.mkdir(mode=0o700,exist_ok=True)
    (ssh/'authorized_keys').write_text(key.strip()+'\n');(ssh/'authorized_keys').chmod(0o600)
    subprocess.run(['ssh-keygen','-A'],check=False)
    Path('/run/sshd').mkdir(exist_ok=True)
    subprocess.Popen(['/usr/sbin/sshd'])
    print('[henge] sshd started',flush=True)

def supervise(commands):
    for command,cwd in commands:processes.append(subprocess.Popen(command,cwd=cwd))
    try:
        while not stopping:
            if any(p.poll() is not None for p in processes):raise RuntimeError('A Henge service stopped; inspect the container logs')
            time.sleep(1)
    finally:
        shutdown()
        for p in processes:
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:p.kill()

def comfy_command(host,args):
    return ([sys.executable,'main.py','--listen',host,'--port','8189','--preview-method','taesd',*args,'--disable-all-custom-nodes','--whitelist-custom-nodes','henge','bfsnodes','h3_latent_upscaler'],COMFY)

def install_tara_kernel():
    # TARA's one-pass Kitchen kernel depends on the GPU (SM80...SM120), so it is installed at boot.
    if os.environ.get('HENGE_TARA_KERNEL','1')!='0':
        if subprocess.run([sys.executable,str(APP/'scripts/install_tara_kernel.py')],cwd='/tmp').returncode:
            print('[henge] WARNING: TARA kernel not installed; TARA uses the frame-wise fallback',flush=True)

def main():
    signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
    role=os.environ.get('HENGE_ROLE','all')
    web=[([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port','8766'],APP/'backend'),(['node','node_modules/next/dist/bin/next','start','--hostname','0.0.0.0','--port','8188'],APP)]
    if role=='ui':
        print('[henge] UI only: bridge + web UI, backend',os.environ.get('HENGE_BACKEND','comfy'),flush=True)
        return supervise(web)
    if role=='worker':
        # Serverless worker: models come from the network volume; inputs/outputs stay on the worker's own disk.
        volume=Path(os.environ.get('HENGE_WORKSPACE','/runpod-volume'))
        if not (volume/'henge/models').is_dir():print(f'[henge] WARNING: no models at {volume}/henge/models; populate the network volume first',flush=True)
        link_to_workspace(volume,('models',));install_tara_kernel()
        return supervise([comfy_command('127.0.0.1',shlex.split(os.environ.get('HENGE_COMFY_ARGS',''))),([sys.executable,str(APP/'docker/worker_handler.py')],APP)])
    workspace=Path(os.environ.get('HENGE_WORKSPACE','/workspace'))
    if workspace.is_dir() and os.environ.get('HENGE_WORKSPACE')!='off':link_to_workspace(workspace)
    if not (workspace.is_dir() and workspace.is_mount()):
        print(f'[henge] WARNING: {workspace} is not a mounted volume. Models (~65 GB) will go to the container disk and are lost when the pod is reset. Attach a volume or network volume at {workspace}.',flush=True)
    start_sshd();install_tara_kernel()
    # Services start right away; models download in the background and the UI shows
    # a setup screen with live progress until every required file is installed.
    # A failed model (e.g. a private LoRA without HF_TOKEN) never restarts the pod.
    downloader=subprocess.Popen([sys.executable,str(APP/'scripts/download_models.py')],cwd=APP)
    comfy_host='0.0.0.0' if os.environ.get('HENGE_EXPOSE_COMFY')=='1' else '127.0.0.1'
    comfy_args=shlex.split(os.environ.get('HENGE_COMFY_ARGS','--lowvram'))
    commands=[comfy_command(comfy_host,comfy_args),*web]
    for command,cwd in commands:processes.append(subprocess.Popen(command,cwd=cwd))
    try:
        reported=False
        while not stopping:
            if any(p.poll() is not None for p in processes):raise RuntimeError('A Henge service stopped; inspect the container logs')
            if not reported and downloader.poll() is not None:
                reported=True
                print('[henge] model downloads finished' if downloader.returncode==0 else '[henge] WARNING: some models failed to download; see the setup screen in the UI',flush=True)
            time.sleep(1)
    finally:
        if downloader.poll() is None:downloader.terminate()
        shutdown()
        for p in processes:
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:p.kill()
if __name__=='__main__':main()
