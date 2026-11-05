"""Pinned keyframes: edited frames of the target video at any time, assigned to the shot that renders them."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from server import validate_request, shot_keyframes, plan_shots
from workflows import h3_graph, pin_frames, pin_opening


def request(**extra):
    return {'mode': 'swap', 'prompt': 'Keep the scene.', 'quality': '480p', 'video': {'start_seconds': 2, 'end_seconds': 12},
            'processing': {'requested_seconds_per_shot': 4.5, 'context_frames': 22},
            'subject_guidance': {'representation': 'original', 'bindings': []}, **extra}


class KeyframeRequestTests(unittest.TestCase):
    def test_accepts_swap_and_motion_keyframes(self):
        validate_request(request(guide_first_frame=True, keyframes=[{'time_seconds': 5, 'slot': 1}, {'time_seconds': 9.5, 'slot': 2}]), {}, [])
        validate_request({**request(keyframes=[{'time_seconds': 5, 'slot': 1}]), 'mode': 'motion', 'prompt': 'motion_transfer: x'}, {'profile': 'motion'}, [1])

    def test_rejects_bad_keyframes(self):
        for bad in ([{'time_seconds': 5}], [{'time_seconds': 'x', 'slot': 1}], [{'time_seconds': 5, 'slot': 1}, {'time_seconds': 6, 'slot': 1}],
                    [{'time_seconds': i, 'slot': i} for i in range(65)]):
            with self.assertRaises(ValueError):
                validate_request(request(guide_first_frame=True, keyframes=bad), {}, [])


class KeyframeShotTests(unittest.TestCase):
    def test_each_keyframe_goes_to_the_shot_that_adds_its_frame(self):
        shots = [{'start': 0, 'frames': 107, 'overlap': 0}, {'start': 85, 'frames': 107, 'overlap': 22}]
        keys = [{'image': 'a.png', 'time': 2.0}, {'image': 'b.png', 'time': 2 + 90 / 24}, {'image': 'c.png', 'time': 2 + 120 / 24}]
        # b (frame 90) is inside the overlap of shot 2, which shot 1 renders; c (frame 120) is new in shot 2.
        self.assertEqual([(i, idx) for i, idx, _ in shot_keyframes(keys, shots[0], 0, 2)], [('a.png', 0), ('b.png', 90)])
        self.assertEqual([(i, idx) for i, idx, _ in shot_keyframes(keys, shots[1], 1, 2)], [('c.png', 35)])

    def test_pins_chain_after_the_opening(self):
        g = h3_graph('v.mp4', ['r.png'], 'p', 512, 288, 107, 107, 'character', 1, 8, 'original', [], 'human', 0)
        pin_frames(pin_opening(g, 'open.png'), [('k1.png', 30), ('k2.png', 80)])
        self.assertEqual(g['pin0']['inputs']['positive'], ['28', 0])
        self.assertEqual(g['pin1']['inputs']['positive'], ['pin0', 0])
        self.assertEqual([g[k]['inputs']['frame_idx'] for k in ('28', 'pin0', 'pin1')], [0, 30, 80])
        self.assertEqual(g['10']['inputs']['positive'], ['pin1', 0])
        self.assertEqual(g['pin1_image']['inputs']['image'], 'k2.png')

    def test_shot_plan_of_a_draft_uses_the_given_cuts(self):
        draft = {'request': request(), 'options': {}}
        shots, _ = plan_shots(draft, [100])
        starts = [s['start'] for s in shots]
        self.assertIn(100, starts)                       # a camera cut opens a clean shot
        self.assertTrue(next(s for s in shots if s['start'] == 100)['reset_context'])


if __name__ == '__main__':
    unittest.main()
