"""Character Swap with an edited first frame and the normal-map guide, and the BFS Body Swap Selective frame editor."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import workflows
from edit_modes import swap_first_frame, NORMALS_NOTE
from server import validate_request
from workflows import h3_graph, normal_guide, pin_opening, bfs_selective_graph, BFS_SELECTIVE


def swap_request(**extra):
    return {'mode': 'swap', 'prompt': 'Keep the scene.', 'quality': '480p', 'video': {'start_seconds': 0, 'end_seconds': 4.5},
            'processing': {'requested_seconds_per_shot': 4.5, 'context_frames': 22},
            'subject_guidance': {'representation': 'original', 'bindings': []}, **extra}


class NormalGuideRequestTests(unittest.TestCase):
    def test_needs_a_character_swap_first_frame(self):
        validate_request(swap_request(guide_first_frame=True, guide_normals=True), {}, [])
        with self.assertRaises(ValueError):
            validate_request(swap_request(guide_normals=True), {}, [1])
        with self.assertRaises(ValueError):
            validate_request({**swap_request(guide_first_frame=True, guide_normals=True), 'mode': 'motion'}, {}, [1])

    def test_motion_transfer_takes_it_too(self):
        motion = {**swap_request(guide_normals=True), 'mode': 'motion', 'prompt': 'motion_transfer: <Picture 1> follows <Video 1>.'}
        validate_request(dict(motion), {'profile': 'motion'}, [1])
        with self.assertRaises(ValueError):      # SolarRenderer already reads a normal map
            validate_request(dict(motion, first_frame_slot=1), {'profile': 'motion_solar_ffp'}, [1])

    def test_replaces_the_guide_representation(self):
        r = swap_request(guide_first_frame=True, guide_normals=True)
        r['subject_guidance']['representation'] = '2d'
        with self.assertRaises(ValueError):
            validate_request(r, {}, [1])

    def test_prompt_says_where_the_look_comes_from(self):
        text = swap_first_frame('body_swap: x', True, 2, normals=True)
        self.assertIn('<Picture 2> is the edited first frame', text)
        self.assertTrue(text.endswith(NORMALS_NOTE))
        self.assertNotIn('normal map', swap_first_frame('body_swap: x', True, 2).lower())


class NormalGuideGraphTests(unittest.TestCase):
    def graph(self):
        return h3_graph('v.mp4', ['r.png', 'first_frame.png'], 'p', 512, 288, 107, 107, 'character', 1, 8, 'original', [], 'human', 0)

    def test_the_model_reads_the_normal_map(self):
        g = normal_guide(self.graph())
        self.assertEqual(g['50']['class_type'], 'LoadMoGeModel')
        self.assertEqual(g['51']['class_type'], 'HengeNormalMap')
        self.assertEqual(g['51']['inputs']['images'], ['8', 0])
        self.assertEqual(g['9']['inputs']['guide'], ['51', 0])
        self.assertEqual(g['18']['inputs']['images'], ['51', 0])     # the saved guide is what the model saw

    def test_the_opening_is_pinned_at_frame_0(self):
        g = pin_opening(normal_guide(self.graph()), 'henge/j/first_frame.png')
        self.assertEqual(g['27']['inputs']['image'], 'henge/j/first_frame.png')
        pin = g['28']['inputs']
        self.assertEqual((g['28']['class_type'], pin['positive'], pin['latent'], pin['image'], pin['frame_idx']),
                         ('MiniMaxH3AddGuide', ['9', 0], ['9', 1], ['27', 0], 0))
        self.assertEqual(g['10']['inputs']['positive'], ['28', 0])
        self.assertEqual(g['10']['inputs']['negative'], ['28', 0])
        self.assertNotIn('first_frame', g['9']['inputs'])            # not the latent mode

    def test_a_continuing_shot_opens_on_the_rendered_frame(self):
        first = server.INPUT / 'henge' / 'j' / 'first_frame.png'
        self.assertEqual(server.opening_frame(0, first, None, {'start': 0}, (0, 0), server.INPUT), 'henge/j/first_frame.png')
        self.assertIsNone(server.opening_frame(1, first, None, {'start': 90}, (0, 0), server.INPUT))   # after a cut


class SelectiveEditorTests(unittest.TestCase):
    def test_graph_reads_scene_marked_scene_and_character(self):
        g = bfs_selective_graph('henge/e/frame.png', ['henge/e/marked.png', 'henge/e/picture_01.png'], '', 7)
        images = {k: v for k, v in g['5']['inputs'].items() if k.startswith('images.')}
        self.assertEqual(images, {'images.image_1': ['31', 0], 'images.image_2': ['32', 0], 'images.image_3': ['33', 0]})
        self.assertEqual([g[k]['inputs']['image'] for k in ('31', '32', '33')], [['10', 0], ['22', 0], ['23', 0]])
        self.assertEqual(g['30']['inputs']['lora_name'], BFS_SELECTIVE['lora'])
        self.assertEqual(g['6']['inputs']['model'], ['30', 0])
        self.assertEqual(g['5']['inputs']['prompt'], BFS_SELECTIVE['prompt'])
        with self.assertRaises(ValueError):
            bfs_selective_graph('f.png', ['picture.png'], '', 7)

    def test_offered_only_with_its_lora(self):
        info = {'TextEncodeQwenImage21': {},
                'UNETLoader': {'input': {'required': {'unet_name': [[workflows.QWEN21['unet']]]}}},
                'CLIPLoader': {'input': {'required': {'clip_name': [[workflows.QWEN21['clip']]]}}},
                'VAELoader': {'input': {'required': {'vae_name': [[workflows.QWEN21['vae']]]}}},
                'LoraLoaderModelOnly': {'input': {'required': {'lora_name': [[workflows.BFS['lora']]]}}}}
        self.assertNotIn('bfs_selective', dict(server.frame_editors(info)))
        info['LoraLoaderModelOnly']['input']['required']['lora_name'][0].append(BFS_SELECTIVE['lora'])
        self.assertIn('bfs_selective', dict(server.frame_editors(info)))
        self.assertEqual(server.editor_instruction('bfs_selective', 'swap', '', '', 1), BFS_SELECTIVE['prompt'])


class H3ImageEditorTests(unittest.TestCase):
    def test_native_edit_reads_the_frame_and_references(self):
        g = workflows.h3image_graph('henge/e/frame.png', ['henge/e/picture_01.png'], 'Edit <Picture 1>. Add a hat.', 3)
        self.assertEqual(g['2']['class_type'], 'LoraLoaderBypassModelOnly')
        self.assertEqual(g['2']['inputs']['lora_name'], workflows.H3IMAGE['lora'])
        cond = g['30']['inputs']
        self.assertEqual((cond['images.image_1'], cond['images.image_2'], cond['prompt']), (['11', 0], ['40', 0], 'Edit <Picture 1>. Add a hat.'))
        self.assertEqual(g['15']['inputs']['vae'], ['5', 0])
        self.assertEqual(g['5']['inputs']['vae_name'], workflows.H3IMAGE['vae'])

    def test_swap_runs_character_swap_on_a_one_frame_latent(self):
        g = workflows.h3image_graph('henge/e/frame.png', ['henge/e/picture_01.png'], workflows.H3IMAGE['swap_prompt'], 3, swap=True)
        self.assertEqual(g['6']['inputs']['lora_name'], workflows.MODELS['character']['lora'])
        self.assertEqual(g['3']['inputs']['model'], ['6', 0])
        self.assertEqual(g['4']['class_type'], 'MolmoH3EncoderLoader')
        self.assertNotIn('images.image_1', g['30']['inputs'])                 # the latent only
        self.assertEqual(g['31']['inputs']['ref_images.ref_image_0'], ['40', 0])
        self.assertEqual(g['31']['inputs']['length'], 5)
        guide = g['32']['inputs']
        self.assertEqual((guide['image'], guide['latent'], guide['frame_idx']), (['11', 0], ['30', 1], 0))
        self.assertEqual(g['8']['inputs']['conditioning'], ['32', 0])
        with self.assertRaises(ValueError):
            workflows.h3image_graph('f.png', [], 'x', 3, swap=True)

    def test_instructions(self):
        from unittest.mock import patch
        with patch.object(server, 'h3image_swap_ready', return_value=True):
            self.assertEqual(server.editor_instruction('h3image', 'swap', '', '', 1), workflows.H3IMAGE['swap_prompt'])
        with patch.object(server, 'h3image_swap_ready', return_value=False):
            self.assertTrue(server.editor_instruction('h3image', 'swap', '', '', 1).startswith('Edit <Picture 1>. Replace'))
        text = server.editor_instruction('h3image', 'replace', 'the cup', 'a red mug', 1)
        self.assertIn('<Picture 2>', text)
        self.assertNotIn('image 2', text)


if __name__ == '__main__':
    unittest.main()
