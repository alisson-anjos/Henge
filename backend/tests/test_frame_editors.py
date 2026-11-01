import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import workflows

class FrameEditorSelectionTests(unittest.TestCase):
    def test_fibo_is_the_default_editor(self):
        # FIBO 2.0 samples the latent of the frame it is given and conditions both positive and negative on it, so the
        # composition survives the edit. FLUX.3 resizes the frame to about a megapixel and samples an empty latent,
        # which re-draws the shot: it comes last.
        info={'TextEncodeFibo2':{},
              'UNETLoader':{'input':{'required':{'unet_name':[[workflows.FIBO['unet']]]}}},
              'CLIPLoader':{'input':{'required':{'clip_name':[[workflows.FIBO['clip']]]}}}}
        self.assertEqual(server.frame_editor(info),'fibo')

    def test_qwen21_needs_its_node_encoder_and_vae(self):
        with patch.object(server,'fibo_available',return_value=False):
            info={'TextEncodeQwenImage21':{},
                  'UNETLoader':{'input':{'required':{'unet_name':[[workflows.QWEN21['unet']]]}}},
                  'CLIPLoader':{'input':{'required':{'clip_name':[[workflows.QWEN21['clip']]]}}},
                  'VAELoader':{'input':{'required':{'vae_name':[[workflows.QWEN21['vae']]]}}}}
            self.assertEqual(server.frame_editor(info),'qwen21')
            # The plain checkpoint works too, and a missing encoder takes the editor out of the offering.
            info['UNETLoader']={'input':{'required':{'unet_name':[[workflows.QWEN21['base']]]}}}
            self.assertEqual(server.frame_editor(info),'qwen21')
            info['CLIPLoader']={'input':{'required':{'clip_name':[['qwen_3_4b.safetensors']]}}}
            self.assertIsNone(server.frame_editor(info))

    def test_editors_are_offered_in_preference_order(self):
        with patch.object(server,'fibo_available',return_value=True),patch.object(server,'qwen21_available',return_value=True), \
             patch.object(server,'klein_available',return_value=True),patch.object(server,'klein3_available',return_value=True):
            self.assertEqual(server.frame_editor({}),'fibo')
            self.assertEqual([key for key,_ in server.frame_editors({})],['fibo','qwen21','klein','klein3'])
            self.assertEqual([c['id'] for c in server.frame_editor_choices({})],['fibo','qwen21','klein','klein3','bfs'])
            with patch.dict(os.environ,{'HENGE_FRAME_EDITOR':'qwen21'}):
                self.assertEqual(server.frame_editor({}),'qwen21')

    def test_a_serverless_worker_without_a_model_list_still_offers_the_editors(self):
        # A Comfy SDK worker names its files only after its first job: until then the studio assumes the editors the
        # image was built with, so the First Frame modal does not hide the frame edit for no reason.
        self.assertFalse(any(c['installed'] for c in server.frame_editor_choices({})))
        assumed=server.frame_editor_choices({},assume=True)
        self.assertEqual([c['id'] for c in assumed],['fibo','qwen21','klein','klein3','bfs'])
        self.assertTrue(all(c['installed'] for c in assumed))

    def test_qwen21_graph_edits_the_frame_at_its_own_size(self):
        graph=workflows.qwen21_graph('henge/job/frame.png',['henge/job/picture_1.png'],'Add fire effects.',7)
        encoder=graph['5']['inputs']
        self.assertEqual(encoder['resolution'],0)                    # keep the frame's size, no ~1 MP crop
        self.assertEqual(encoder['images.image_1'],['10',0])         # the frame itself is reference 1
        self.assertEqual(encoder['images.image_2'],['22',0])
        sampler=graph['6']['inputs']
        self.assertEqual(sampler['latent_image'],['5',2])            # the encoder's latent, not an empty one
        self.assertEqual((sampler['steps'],sampler['cfg'],sampler['sampler_name'],sampler['scheduler']),(8,1.,'deis_2m','simple'))
        plain=workflows.qwen21_graph('henge/job/frame.png',[],'Add fire effects.',7,unet=workflows.QWEN21['base'])
        self.assertEqual(plain['1']['inputs']['unet_name'],workflows.QWEN21['base'])
        self.assertEqual((plain['6']['inputs']['steps'],plain['6']['inputs']['cfg'],plain['6']['inputs']['sampler_name']),(24,2.5,'euler'))

    def test_qwen_image_21_goes_fast_with_the_turbo_lora(self):
        # The 7.3 GB Turbo checkpoint is optional: the full checkpoint plus the 5-step LoRA gets the same short schedule,
        # and the LoRA is skipped when the distilled build is the one being loaded.
        base_only={'UNETLoader':{'input':{'required':{'unet_name':[[workflows.QWEN21['base']]]}}}}
        turbo_only={'UNETLoader':{'input':{'required':{'unet_name':[[workflows.QWEN21['unet']]]}}}}
        with patch.object(workflows,'INSTALLED',{'LoraLoaderModelOnly':{workflows.QWEN21['turbo']}}):
            self.assertEqual(server.qwen21_lora(base_only),workflows.QWEN21['turbo'])
            graph=server.editor_graph('qwen21','henge/job/frame.png',[],'Add fire effects.',7,info=base_only)
            self.assertEqual(graph['1']['inputs']['unet_name'],workflows.QWEN21['base'])
            self.assertEqual(graph['9']['inputs']['lora_name'],workflows.QWEN21['turbo'])
            self.assertEqual(graph['6']['inputs']['model'],['9',0])
            self.assertEqual((graph['6']['inputs']['steps'],graph['6']['inputs']['cfg'],graph['6']['inputs']['sampler_name']),(5,1.,'deis_2m'))
            self.assertEqual(server.qwen21_lora(turbo_only),'')
            self.assertNotIn('9',server.editor_graph('qwen21','henge/job/frame.png',[],'Add fire effects.',7,info=turbo_only))
        with patch.object(workflows,'INSTALLED',{'LoraLoaderModelOnly':set()}):
            self.assertEqual(server.qwen21_lora(base_only),'')

    def test_editor_graph_follows_the_chosen_editor(self):
        with patch.object(server,'qwen21_model',return_value=workflows.QWEN21['base']):
            graph=server.editor_graph('qwen21','henge/job/frame.png',[],'Add fire effects.',7)
        self.assertEqual(graph['1']['inputs']['unet_name'],workflows.QWEN21['base'])
        self.assertEqual(server.editor_graph('fibo','henge/job/frame.png',[],'Add fire effects.',7)['1']['inputs']['unet_name'],
                         workflows.FIBO['unet'])
        with self.assertRaisesRegex(ValueError,'image editor'):
            server.editor_graph('paintbrush','henge/job/frame.png',[],'Add fire effects.',7)

    def test_adaptation_without_editor_fails_before_media_or_inference(self):
        with patch.object(server,'frame_editor',return_value=None),patch.object(server,'run') as media,patch.object(server,'execute_graph') as infer:
            with self.assertRaisesRegex(ValueError,'image editor'):
                server.adapt_prepare({}, {})
        media.assert_not_called();infer.assert_not_called()

    def test_the_modal_can_ask_for_any_installed_editor(self):
        # The First Frame modal sends `editor`; anything this ComfyUI can run is accepted, anything else is refused
        # before media work, and the graph that runs is the one that was asked for.
        from fastapi.testclient import TestClient
        from PIL import Image
        import io as memory
        def png():
            buffer=memory.BytesIO();Image.new('RGB',(16,16),'white').save(buffer,'PNG');return buffer.getvalue()
        def fake_image(outputs,dest):
            Image.new('RGB',(16,16),'black').save(dest);return dest
        with patch.object(server,'frame_editors',return_value=[('fibo','FIBO 2.0 edit turbo'),('qwen21','Qwen-Image 2.1 Turbo')]), \
             patch.object(server,'execute_graph',return_value={}) as infer,patch.object(server,'image_from_output',side_effect=fake_image):
            client=TestClient(server.app)
            for editor,sampler in (('fibo','euler'),('qwen21','deis_2m')):
                response=client.post('/frame-edit',data={'op':'add','instruction':'Add fire effects.','editor':editor},
                                     files={'frame':('frame.png',png(),'image/png')})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(infer.call_args_list[-1].args[1]['6']['inputs']['sampler_name'],sampler)
            refused=client.post('/frame-edit',data={'op':'add','instruction':'Add fire effects.','editor':'klein'},
                                files={'frame':('frame.png',png(),'image/png')})
            self.assertEqual(refused.status_code,400)

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
        # Other test files leave jobs behind in this data dir, so assert on what must be in the deleted set.
        deleted=set(server.clear_frame_edits()['deleted'])
        self.assertTrue({'a'*32,'b'*32} <= deleted)
        self.assertNotIn('c'*32,deleted)
        self.assertFalse((server.job_path('a'*32).exists() or (server.INPUT/'henge'/('a'*32)).exists()))
        self.assertTrue((server.INPUT/'henge'/('c'*32)/'guide.mp4').is_file())
