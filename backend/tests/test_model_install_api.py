import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import server
from model_installs import InstallManager

class ModelInstallAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'models').mkdir()
        self.manager=InstallManager(self.root/'state')
        self.manifest={'models':[{'id':'test','url':'https://huggingface.co/example/model/resolve/main/test.safetensors','destination':'loras/test.safetensors'}]}
        self.snapshot={'manifest':self.manifest,'check_ok':True,'catalog_revision':None,'current':'a'*40,'latest':'b'*40,'changelog':'notes'}
        self.patches=[patch.object(server,'COMFY',self.root),patch.object(server,'REMOTE',None),patch.object(server,'MODEL_INSTALL',self.manager),patch.object(server.app_updates,'snapshot',return_value=self.snapshot),patch.object(server,'active_jobs',return_value=[])]
        for p in self.patches:p.start()
        self.client=TestClient(server.app)
    def tearDown(self):
        if self.manager.thread:self.manager.thread.join(3)
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_local_install_stays_background_and_refreshes_inventory(self):
        with patch.object(server.model_installer,'install',return_value={}) as install,patch.object(server,'refresh_info_later') as refresh:
            response=self.client.post('/models/install',json={'model_id':'test'})
            self.manager.thread.join(3)
        self.assertEqual(response.status_code,200);install.assert_called_once();refresh.assert_called_once()
        self.assertEqual(self.client.get('/models').json()['installation']['status'],'completed')
    def test_active_generation_and_unknown_model_are_rejected(self):
        with patch.object(server,'active_jobs',return_value=['active']):
            self.assertEqual(self.client.post('/models/install',json={'model_id':'test'}).status_code,409)
        self.assertEqual(self.client.post('/models/install',json={'model_id':'not-catalogued'}).status_code,409)
        self.manager.update(status='running')
        self.assertEqual(self.client.post('/jobs',json={}).status_code,409)
    def test_updates_do_not_expose_internal_manifest(self):
        data=self.client.get('/updates').json()
        self.assertNotIn('manifest',data);self.assertNotIn('catalog_revision',data)
        self.assertEqual(data['current'],'a'*40)
    def test_unsupported_catalog_destinations_are_not_installable(self):
        self.manifest['models'][0]['destination']='../escape'
        data=self.client.get('/models').json()
        self.assertFalse(data['models'][0]['installable'])
