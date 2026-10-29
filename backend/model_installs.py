"""Durable bridge-side orchestration for explicit local/Serverless model installs."""
import json
from pathlib import Path
import threading
import time
import uuid
import model_installer

ACTIVE={'queued','running','cancelling'}

class InstallManager:
    def __init__(self,root):
        self.path=Path(root)/'model-installation.json';self.lock=threading.RLock();self.thread=None;self.stop=threading.Event()
        try:self.state=json.loads(self.path.read_text())
        except (OSError,ValueError):self.state={'status':'idle'}

    def active(self):return self.state.get('status') in ACTIVE

    def public(self):
        return {k:v for k,v in self.state.items() if k not in ('backend','request_id','catalog_revision')}

    def update(self,**values):
        with self.lock:
            self.state.update(values,updated=time.time());self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.state));temp.replace(self.path)

    def start(self,model_id,manifest,revision,backend=None,models_dir=None,resume=False,on_complete=None):
        with self.lock:
            if not resume:
                if self.active():raise ValueError('A model installation is already running')
                if model_id!='__inventory__':model_installer.selected(manifest,model_id)
                self.state={'id':uuid.uuid4().hex,'model_id':model_id,'status':'queued','stage':'queued',
                            'backend':backend.base if backend else 'local','catalog_revision':revision,'started':time.time()}
            self.stop.clear();self.update()
            def work():
                try:
                    def progress(rid,value):
                        self.update(**({'request_id':rid} if rid else {}),status='running',**(value or {'stage':'queued'}))
                    if backend:
                        if resume:backend.wait(self.state['request_id'],progress,self.stop.is_set)
                        else:backend.call({'op':'inventory'} if model_id=='__inventory__' else {'op':'install_models','model_id':model_id,'catalog_revision':revision},progress,self.stop.is_set)
                    else:
                        if not models_dir:raise ValueError('Configure COMFY_ROOT for local model installation')
                        self.update(status='running')
                        model_installer.install(models_dir,manifest,model_id,lambda value:self.update(**value),self.stop.is_set)
                    if on_complete:on_complete()
                    self.update(status='completed',stage='completed',message='Worker inventory refreshed' if model_id=='__inventory__' else 'Model installed; inventory refreshed')
                except InterruptedError:self.update(status='cancelled',stage='cancelled',message='Installation cancelled; partial download kept for retry')
                except Exception as exc:self.update(status='failed',stage='failed',message=str(exc)[:1000])
            self.thread=threading.Thread(target=work,daemon=True);self.thread.start()
            return self.public()

    def recover(self,backend=None):
        with self.lock:
            if not self.active() or (self.thread and self.thread.is_alive()):return
            if backend and self.state.get('backend')==backend.base and self.state.get('request_id'):
                self.start(self.state['model_id'],None,self.state.get('catalog_revision'),backend=backend,resume=True)
            else:self.update(status='failed',stage='failed',message='Installation was interrupted by a bridge restart; retry to resume the partial download')

    def cancel(self):
        if self.active():self.stop.set();self.update(status='cancelling',message='Cancelling installation')
        return self.public()
