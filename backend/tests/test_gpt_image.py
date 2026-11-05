"""GPT Image (OpenAI API) as a frame editor: offered once enabled with a key, sends the frame, references and mask."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistant
import server


class GptImageConfigTests(unittest.TestCase):
    def test_key_comes_from_its_own_field_then_the_openai_assistant(self):
        self.assertEqual(assistant.image_key({'image_api_key': 'sk-img', 'provider': 'openai', 'api_key': 'sk-chat'}), 'sk-img')
        self.assertEqual(assistant.image_key({'provider': 'openai', 'api_key': 'sk-chat', 'base_url': ''}), 'sk-chat')
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            self.assertEqual(assistant.image_key({'provider': 'openai', 'api_key': 'sk-chat', 'base_url': 'http://127.0.0.1:1234/v1'}), '')
            self.assertEqual(assistant.image_key({'provider': 'anthropic', 'api_key': 'sk-ant'}), '')

    def test_ready_needs_enabled_model_and_key(self):
        self.assertFalse(assistant.gpt_image_ready({'image_enabled': False, 'image_model': 'm', 'image_api_key': 'k'}))
        self.assertTrue(assistant.gpt_image_ready({'image_enabled': True, 'image_model': 'm', 'image_api_key': 'k'}))

    def test_offered_without_comfyui(self):
        with patch.object(server, 'gpt_image_ready', return_value=True), patch.object(server, 'comfy_info', side_effect=OSError):
            self.assertEqual([k for k, _ in server.frame_editors()], ['gpt_image'])
        with patch.object(server, 'gpt_image_ready', return_value=False):
            self.assertNotIn('gpt_image', dict(server.frame_editors({})))


class GptImageEditTests(unittest.TestCase):
    def test_sends_images_mask_and_model(self):
        reply = MagicMock(ok=True); reply.json.return_value = {'data': [{'b64_json': 'aGk='}]}
        with patch.object(assistant.requests, 'post', return_value=reply) as post:
            out = assistant.gpt_image_edit({'image_api_key': 'k', 'image_model': 'gpt-image-x', 'image_quality': 'high'}, [b'a', b'b'], 'Edit it', b'm')
        self.assertEqual(out, b'hi')
        args = post.call_args
        self.assertTrue(args.args[0].endswith('/v1/images/edits'))
        self.assertEqual([f[0] for f in args.kwargs['files']], ['image[]', 'image[]', 'mask'])
        self.assertEqual((args.kwargs['data']['model'], args.kwargs['data']['quality']), ('gpt-image-x', 'high'))

    def test_swap_instruction_names_the_masked_person(self):
        text = server.editor_instruction('gpt_image', 'swap', '', '', 1, marked=True)
        self.assertIn('the person inside the masked area of image 1', text)
        self.assertIn('image 2', text)


if __name__ == '__main__':
    unittest.main()
