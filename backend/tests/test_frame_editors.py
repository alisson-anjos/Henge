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

    def test_clearing_recent_edits_removes_their_records_and_pictures(self):
        # Recent frame edits stay out of "clear history", so the modal's own Clear button has to remove them:
        # record, edited picture and staged input, without touching generations.
        for jid in ('a'*32,'b'*32):
            server.job_path(jid).mkdir(parents=True,exist_ok=True);(server.INPUT/'henge'/jid).mkdir(parents=True,exist_ok=True)
            server.save({'id':jid,'created':0,'status':'completed','request':{'mode':'frame_edit','instruction':'x'}})
            (server.INPUT/'henge'/jid/'edited.png').write_bytes(b'png')
        server.job_path('c'*32).mkdir(parents=True,exist_ok=True);(server.INPUT/'henge'/('c'*32)).mkdir(parents=True,exist_ok=True)
        server.save({'id':'c'*32,'created':0,'status':'completed','request':{'mode':'motion'}})
        (server.INPUT/'henge'/('c'*32)/'guide.mp4').write_bytes(b'v')
        self.assertEqual(sorted(server.clear_frame_edits()['deleted']),['a'*32,'b'*32])
        self.assertFalse((server.job_path('a'*32).exists() or (server.INPUT/'henge'/('a'*32)).exists()))
        self.assertTrue((server.INPUT/'henge'/('c'*32)/'guide.mp4').is_file())
