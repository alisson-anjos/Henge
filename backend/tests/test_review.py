"""Review of a finished job: source-over-result strips per shot and the camera-cut timing (no GPU)."""
import base64, io, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ReviewJobTests(unittest.TestCase):
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

    def test_each_source_cut_is_on_time_off_or_dropped(self):
        cuts, extra = self.server.cut_timing([48, 120, 200, 300], [49, 108, 230, 310, 400])
        self.assertEqual([(c['frame'], c['verdict'], c.get('offset')) for c in cuts],
                         [(48, 'on time', 1), (120, 'early', -12), (200, 'dropped', None), (300, 'late', 10)])
        self.assertEqual(extra, [{'frame': 230, 'verdict': 'extra'}, {'frame': 400, 'verdict': 'extra'}])

    def clip(self, path, seconds, colour):
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={colour}:s=160x90:r=24:d={seconds}', '-pix_fmt', 'yuv420p', '-y', str(path)], check=True)

    def test_strips_show_each_shot_and_mark_the_keyframe(self):
        s = self.server; jid = 'b' * 32; work = s.job_path(jid); work.mkdir(parents=True, exist_ok=True)
        (s.INPUT / 'henge' / jid).mkdir(parents=True, exist_ok=True)
        self.clip(s.INPUT / 'henge' / jid / 'guide.mp4', 6, 'red'); self.clip(work / 'result.mp4', 4, 'blue')
        (s.INPUT / 'henge' / jid / 'key.png').write_bytes(b'')
        s.save({'id': jid, 'created': 0, 'status': 'completed', 'stage': 'complete', 'progress': 1, 'options': {},
                'request': {'mode': 'swap', 'video': {'start_seconds': 1, 'end_seconds': 5}},
                'assets': {'video': f'henge/{jid}/guide.mp4', 'keyframes': [{'slot': 1, 'time': 3.4, 'image': f'henge/{jid}/key.png'}]}})
        shots = {'cut_mode': 'fit', 'shots': [{'index': 1, 'start': 1.0, 'end': 3.0, 'context_seconds': 0, 'after_cut': False},
                                              {'index': 2, 'start': 3.0, 'end': 5.0, 'context_seconds': 0, 'after_cut': True}]}
        with patch.object(s, 'shot_preview', return_value=shots), patch.object(s, 'camera_cuts', return_value=[48]), patch.object(s, 'detect_camera_cuts', return_value=[40]):
            r = self.client.get(f'/jobs/{jid}/review?shots=2')
        self.assertEqual(r.status_code, 200, r.text)
        info = r.json()
        self.assertEqual([x['shot'] for x in info['shots']], [2])
        row = info['shots'][0]
        self.assertIn(3.4, row['times']); self.assertEqual(len(row['keyframe_columns']), 1)
        self.assertEqual(row['cuts'], [{'frame': 48, 'result_frame': 40, 'offset': -8, 'verdict': 'early'}])
        from PIL import Image
        strip = Image.open(io.BytesIO(base64.b64decode(row['strip'].split(',', 1)[1]))).convert('RGB')
        self.assertEqual(strip.width, 4 * 320)
        top, bottom = strip.getpixel((160, strip.height // 4)), strip.getpixel((160, 3 * strip.height // 4))
        self.assertGreater(top[0], 200); self.assertGreater(bottom[2], 200)        # source on top, result below
        self.assertEqual(self.client.get(f'/jobs/{jid}/review?shots=x').status_code, 400)

    def test_only_after_completion(self):
        s = self.server; jid = 'c' * 32; s.job_path(jid).mkdir(parents=True, exist_ok=True)
        s.save({'id': jid, 'created': 0, 'status': 'running', 'stage': 'render', 'progress': .5, 'options': {}, 'request': {'mode': 'swap'}})
        self.assertEqual(self.client.get(f'/jobs/{jid}/review').status_code, 409)


if __name__ == '__main__':
    unittest.main()
