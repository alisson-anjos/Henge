"""Start the isolated services without stopping or reconfiguring training."""
import os,subprocess,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for file in [ROOT/'.env',ROOT/'.env.local']:
 if file.exists():
  for line in file.read_text().splitlines():
   if line.strip() and not line.lstrip().startswith('#') and '=' in line:
    key,value=line.split('=',1)
    if key.strip() in ['VLM_CHAT_URL','VLM_MODEL','VLM_API_KEY','KAGEMANE_VLM_CLIP','COMFY_BASE_URL','COMFY_ROOT','KAGEMANE_DATA_DIR']:os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))
PYTHON=os.environ.get('KAGEMANE_PYTHON','/data/comfyui/.venv/bin/python');COMFY=os.environ.get('COMFY_ROOT','/data/kagemane-comfy-backend');DEPS=ROOT/'.runtime/comfy-deps'
if not DEPS.exists():
 DEPS.mkdir(parents=True)
 subprocess.run(['uv','pip','install','--python',PYTHON,'--target',str(DEPS),'--no-deps','comfy-kitchen==0.2.39','comfy-aimdo==0.5.6','comfyui-frontend-package==1.57.1'],check=True)
services=[('comfy','http://127.0.0.1:8189/system_stats',[PYTHON,'-u',COMFY+'/main.py','--listen','127.0.0.1','--port','8189','--disable-all-custom-nodes','--whitelist-custom-nodes','kagemane','--extra-model-paths-config',str(ROOT/'backend/extra_model_paths.yaml'),'--disable-api-nodes','--lowvram','--preview-method','none'],COMFY),('bridge','http://127.0.0.1:8766/health',[PYTHON,'-m','uvicorn','server:app','--host','127.0.0.1','--port','8766'],str(ROOT/'backend'))]
state=ROOT/'backend/services.json';pids=json.loads(state.read_text()) if state.exists() else {}
for name,url,args,cwd in services:
 try:urllib.request.urlopen(url,timeout=2);print(name,'already online');continue
 except Exception:pass
 env={**os.environ,'PYTHONPATH':str(DEPS)+':/tmp/caption-runtime-site','COMFY_ROOT':COMFY}
 with (ROOT/'backend'/f'{name}.log').open('ab',buffering=0) as log:p=subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 pids[name]=p.pid;print(name,p.pid)
state.write_text(json.dumps(pids,indent=2))
