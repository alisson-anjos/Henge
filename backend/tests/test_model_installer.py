"""On-demand model installation contracts; tiny byte fixtures, no real model downloads."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import requests
from filelock import FileLock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import model_installer as installer
from model_installs import InstallManager

class Response:
    def __init__(self,data=b'weights',status=200,headers=None):
        self.data=data;self.status_code=status;self.headers=headers or {'Content-Length':str(len(data))}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def close(self):pass
    def raise_for_status(self):
        if self.status_code>=400:raise requests.HTTPError(str(self.status_code))
    def iter_content(self,*args):yield self.data


def manifest():
    return {'models':[{'id':'test','url':'https://huggingface.co/example/model/resolve/main/model.safetensors','destination':'loras/model.safetensors','profiles':['common']}]}

class ModelInstallerTests(unittest.TestCase):
    def test_atomic_publication_and_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);m=manifest();m['models'][0]['sha256']=hashlib.sha256(b'weights').hexdigest()
            updates=[]
            def progress(value):
                updates.append(value)
                if value['stage']=='downloading':self.assertFalse((root/'loras/model.safetensors').exists())
            with patch.object(installer.requests,'get',return_value=Response()):installer.install(root,m,'test',progress)
            self.assertEqual((root/'loras/model.safetensors').read_bytes(),b'weights')
            self.assertTrue(any(v['stage']=='verifying' for v in updates))
            with patch.object(installer.requests,'get') as download:installer.install(root,m,'test',lambda v:None)
            download.assert_not_called()

    def test_cancel_retains_partial_and_retry_resumes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);part=root/'loras/model.safetensors.part';part.parent.mkdir();part.write_bytes(b'wei')
            with patch.object(installer.requests,'get',return_value=Response(b'ghts',206,{'Content-Range':'bytes 3-6/7'})) as download:
                installer.install(root,manifest(),'test',lambda v:None)
            self.assertEqual(download.call_args.kwargs['headers']['Range'],'bytes=3-')
            self.assertEqual((root/'loras/model.safetensors').read_bytes(),b'weights')
        with tempfile.TemporaryDirectory() as folder:
            stopped=threading.Event()
            with patch.object(installer.requests,'get',return_value=Response()):
                def progress(value):
                    if value['stage']=='downloading':stopped.set()
                # Cancellation after the last chunk must not publish a model.
                with self.assertRaises(InterruptedError):installer.install(Path(folder),manifest(),'test',progress,stopped.is_set)
            self.assertFalse((Path(folder)/'loras/model.safetensors').exists())
            self.assertTrue((Path(folder)/'loras/model.safetensors.part').exists())

    def test_invalid_download_does_not_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            m=manifest();m['models'][0]['sha256']='0'*64
            with patch.object(installer.requests,'get',return_value=Response()),self.assertRaisesRegex(ValueError,'checksum'):
                installer.install(Path(folder),m,'test',lambda v:None)
            self.assertFalse((Path(folder)/'loras/model.safetensors').exists())

    def test_unknown_id_path_escape_and_concurrent_install_are_refused(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(installer.requests,'get') as download:
            root=Path(folder)
            with self.assertRaises(ValueError):installer.install(root,manifest(),'unknown',lambda v:None)
            m=manifest();m['models'][0]['destination']='../outside'
            with self.assertRaises(ValueError):installer.install(root,m,'test',lambda v:None)
            with FileLock(str(root/'.henge-model-install.lock')):
                with self.assertRaisesRegex(ValueError,'Another'):installer.install(root,manifest(),'test',lambda v:None)
            download.assert_not_called()

    def test_worker_operation_downloads_without_submitting_graph(self):
        spec=importlib.util.spec_from_file_location('henge_test_worker',Path(__file__).resolve().parents[2]/'docker/worker_handler.py')
        worker=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'runpod':Mock()}):spec.loader.exec_module(worker)
        with patch.object(worker.model_installer,'catalog',return_value=manifest()),patch.object(worker.model_installer,'install',return_value={'model_id':'test'}) as install,patch.object(worker,'inventory',return_value={'capabilities':{'model_install':1}}),patch.object(worker,'run') as generate:
            result=asyncio.run(worker.handler({'input':{'op':'install_models','model_id':'test'}}))
        self.assertEqual(result['installation']['model_id'],'test');install.assert_called_once();generate.assert_not_called()

    def test_local_manager_and_remote_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=InstallManager(folder)
            with patch.object(installer,'install',return_value={}) as download:
                manager.start('test',manifest(),None,models_dir=Path(folder)/'models');manager.thread.join(3)
            self.assertEqual(manager.public()['status'],'completed');download.assert_called_once()
            manager.update(status='running',backend='https://worker.example',request_id='request',model_id='test')
            recovered=InstallManager(folder);backend=Mock(base='https://worker.example')
            recovered.recover(backend);recovered.thread.join(3)
            backend.wait.assert_called_once();backend.call.assert_not_called()
            self.assertNotIn('request_id',recovered.public())
