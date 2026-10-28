import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class FrameEditorSelectionTests(unittest.TestCase):
    def test_retired_fibo_inventory_is_not_selected(self):
        info={'TextEncodeFibo2':{},'UNETLoader':{'input':{'required':{'unet_name':[['fibo2_edit_turbo_int8_convrot.safetensors']]}}}}
        self.assertIsNone(server.frame_editor(info))

    def test_klein3_is_preferred_when_both_are_available(self):
        with patch.object(server,'klein3_available',return_value=True),patch.object(server,'klein_available',return_value=True):
            self.assertEqual(server.frame_editor({}),'klein3')

    def test_klein2_remains_supported(self):
        with patch.object(server,'klein3_available',return_value=False),patch.object(server,'klein_available',return_value=True):
            self.assertEqual(server.frame_editor({}),'klein')

    def test_adaptation_without_editor_fails_before_media_or_inference(self):
        with patch.object(server,'frame_editor',return_value=None),patch.object(server,'run') as media,patch.object(server,'execute_graph') as infer:
            with self.assertRaisesRegex(ValueError,'FLUX.3 or FLUX.2 Klein'):
                server.adapt_prepare({}, {})
        media.assert_not_called();infer.assert_not_called()
