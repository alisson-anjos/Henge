"""Redo one shot with an adjusted prompt (no GPU)."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ShotRedoPrompt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, {'HENGE_DATA_DIR': cls.folder.name, 'HENGE_BACKEND': 'comfyui'}); cls.env.start()
        import server
        from fastapi.testclient import TestClient
        cls.server = server; cls.client = TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop(); cls.folder.cleanup()

    def job(self):
        jid = 'a' * 32; work = self.server.job_path(jid); work.mkdir(parents=True, exist_ok=True)
        graph = {'9': {'class_type': 'HengeH3Conditioning', 'inputs': {'prompt': 'Replace the woman with <Picture 1>.'}},
                 '11': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': 1}}}
        (work / 'h3_segment_002.api.json').write_text(json.dumps(graph))
        self.server.save({'id': jid, 'created': 0, 'status': 'completed', 'stage': 'complete', 'progress': 1, 'request': {'mode': 'swap'}, 'options': {}})
        return jid

    def test_prompt_is_read_and_a_redo_can_replace_it(self):
        jid = self.job()
        r = self.client.get(f'/jobs/{jid}/shots/3/prompt')
        self.assertEqual(r.status_code, 200, r.text); self.assertEqual(r.json()['prompt'], 'Replace the woman with <Picture 1>.')
        self.assertEqual(self.client.get(f'/jobs/{jid}/shots/4/prompt').status_code, 404)
        self.assertEqual(self.client.post(f'/jobs/{jid}/shots/3/redo', json={'prompt': '  '}).status_code, 400)
        r = self.client.post(f'/jobs/{jid}/shots/3/redo', json={'prompt': 'The camera is upside down: the creature appears upside down.'})
        self.assertEqual(r.status_code, 200, r.text)
        job = self.server.load(jid)
        self.assertEqual(job['redo'], {'shot': 2, 'seed': None, 'prompt': 'The camera is upside down: the creature appears upside down.'})
        # The redo runs the saved graph with that prompt in the conditioning node.
        sent = {}
        def run(job_, graph, stage):
            sent.update(graph); raise RuntimeError('stop after capture')
        with patch.object(self.server, 'plan_shots', return_value=([{'start': 0, 'frames': 50, 'overlap': 0}] * 3, 22)), patch.object(self.server, 'execute_graph', side_effect=run):
            with self.assertRaises(RuntimeError): self.server.redo_shot(job)
        self.assertEqual(sent['9']['inputs']['prompt'], 'The camera is upside down: the creature appears upside down.')


if __name__ == '__main__':
    unittest.main()
