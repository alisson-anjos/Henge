"""Fetch configured weights, then supervise ComfyUI, bridge and web UI."""
import os,signal,subprocess,sys,time,requests
from pathlib import Path
APP=Path('/app');COMFY=Path(os.environ.get('COMFY_ROOT','/opt/ComfyUI'));processes=[];stopping=False

def shutdown(*_):
    global stopping
    stopping=True
    for p in reversed(processes):
        if p.poll() is None:p.terminate()

def main():
    signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
    subprocess.run([sys.executable,str(APP/'scripts/download_models.py')],cwd=APP,check=True)
    commands=[([sys.executable,'main.py','--listen','127.0.0.1','--port','8189','--lowvram','--preview-method','taesd','--disable-all-custom-nodes','--whitelist-custom-nodes','kagemane','bfsnodes'],COMFY),([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port','8766'],APP/'backend'),(['node','node_modules/next/dist/bin/next','start','--hostname','0.0.0.0','--port','8188'],APP)]
    for command,cwd in commands:processes.append(subprocess.Popen(command,cwd=cwd))
    try:
        while not stopping:
            if any(p.poll() is not None for p in processes):raise RuntimeError('A Kagemane service stopped; inspect docker compose logs')
            time.sleep(1)
    finally:
        shutdown()
        for p in processes:
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:p.kill()
if __name__=='__main__':main()
