"""Real FFmpeg checks for joining shots without loading their RGB videos into RAM."""
import os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class StreamingJoinTests(unittest.TestCase):
 def clip(self,path,frames,color='red'):
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color={color}:size=96x64:rate=24','-frames:v',str(frames),'-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-y',str(path)],check=True)
 def test_preserves_total_duration_and_drops_overlap_once(self):
  with tempfile.TemporaryDirectory() as folder:
   a=Path(folder)/'a.mp4';b=Path(folder)/'b.mp4';self.clip(a,24);self.clip(b,20)
   with patch.object(server,'read_overlap_frames',wraps=server.read_overlap_frames) as read:
    server.seam_join(a,b,8)
   self.assertEqual((server.frame_count(a),server.frame_count(b)),(24,12))
   self.assertEqual([c.args[1:3] for c in read.call_args_list],[(16,8),(0,8)])
   self.assertFalse(list(Path(folder).glob('*.joining.mp4')))
 def test_empty_prefix_at_seam_zero_preserves_timeline(self):
  with tempfile.TemporaryDirectory() as folder:
   a=Path(folder)/'a.mp4';b=Path(folder)/'b.mp4';self.clip(a,8);self.clip(b,20,'blue')
   with patch('video_join.overlap_match',return_value=0):server.seam_join(a,b,8)
   self.assertEqual((server.frame_count(a),server.frame_count(b)),(8,12))
 def test_failed_encode_leaves_both_inputs_untouched(self):
  with tempfile.TemporaryDirectory() as folder:
   a=Path(folder)/'a.mp4';b=Path(folder)/'b.mp4';self.clip(a,24);self.clip(b,20);before=[p.read_bytes() for p in (a,b)]
   with patch.object(server,'run',side_effect=RuntimeError('encoder failed')),self.assertRaises(RuntimeError):server.seam_join(a,b,8)
   self.assertEqual([p.read_bytes() for p in (a,b)],before)
 def test_sampling_memory_depends_on_overlap_and_thumbnail_not_full_video(self):
  with tempfile.TemporaryDirectory() as folder:
   a=Path(folder)/'a.mp4';self.clip(a,100)
   samples=server.read_overlap_frames(a,92,8,96,64)
   self.assertEqual(samples.shape,(8,64,96,3))
   self.assertLessEqual(samples.nbytes,8*256*256*3)

 def test_incoming_shot_keeps_its_colour(self):
  import numpy as np
  with tempfile.TemporaryDirectory() as folder:
   a=Path(folder)/'a.mp4';b=Path(folder)/'b.mp4';self.clip(a,24,'red');self.clip(b,20,'blue')
   before=server.read_overlap_frames(b,8,1,96,64).mean((0,1,2))
   server.seam_join(a,b,8)
   after=server.read_overlap_frames(b,0,1,96,64).mean((0,1,2))
   np.testing.assert_allclose(after,before,atol=3)
