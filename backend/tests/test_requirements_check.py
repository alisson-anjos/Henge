import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from requirements_check import check


class ModelChecklistTests(unittest.TestCase):
    def test_legacy_weights_are_ready_like_the_graph_loader(self):
        model={'character':{'label':'Character Swap','lora':'henge/minimax_h3_character_swap_v1.1_ref2va_fro.safetensors',
                            'adapter':'henge/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors'}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['base.safetensors','loras/henge/character_v1_1.safetensors','loras/henge/dmd_ref2va_8step.safetensors']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'weight')
            with patch('requirements_check.base_files',return_value=[('base','Base','base.safetensors')]):
                rows,ready,setup=check(root,model)
            self.assertTrue(ready['character'])
            self.assertTrue(setup['all_ready'])
            self.assertTrue(all(r['state']=='installed' for r in rows))

    def test_missing_legacy_adapter_is_not_reported_ready(self):
        model={'character':{'label':'Character Swap','lora':'henge/minimax_h3_character_swap_v1.1_ref2va_fro.safetensors',
                            'adapter':'henge/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors'}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['base.safetensors','loras/henge/character_v1_1.safetensors']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'weight')
            with patch('requirements_check.base_files',return_value=[('base','Base','base.safetensors')]):
                rows,ready,setup=check(root,model)
            self.assertFalse(ready['character'])
            self.assertFalse(setup['all_ready'])
            self.assertEqual([r['state'] for r in rows if r['id']=='character_adapter'],['missing'])
