"""Sampling contracts for the Pika Comfy adapter; no weights or GPU are loaded."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from workflows import h3_graph, TURBOS, REGENERATE_SIGMAS

ROOT=Path(__file__).resolve().parents[2]

class PikaSamplingTests(unittest.TestCase):
    def graph(self, profile='motion', steps=6, **options):
        return h3_graph('guide.mp4',['reference.png'],'motion_transfer: reference',512,288,22,22,
                        profile,42,steps,'original',[],'human',0,turbo=options.pop('turbo','pika6'),**options)

    def test_six_step_workflow_schedule_without_training_adapter(self):
        graph=self.graph()
        self.assertEqual(graph['12']['inputs']['sampler_name'],'lcm')
        self.assertEqual(graph['13']['class_type'],'ManualSigmas')
        self.assertEqual([float(s) for s in graph['13']['inputs']['sigmas'].split(',')],
                         [1.,.972973,.923077,.8,.571429,.333333,0.])
        self.assertEqual(graph['2']['inputs']['lora_name'],TURBOS['pika6']['lora'])
        self.assertNotIn('25',graph);self.assertEqual(graph['3']['inputs']['model'],['2',0])
        self.assertEqual(graph['4']['inputs']['shift_video'],12.)
        self.assertEqual(graph['4']['inputs']['shift_audio'],3.)

    def test_kijai_selection_keeps_pika_sampling_and_its_own_file(self):
        graph=self.graph(turbo='pika6_kijai')
        self.assertEqual(graph['12']['inputs']['sampler_name'],'lcm')
        self.assertEqual(graph['13']['class_type'],'ManualSigmas')
        self.assertEqual(graph['2']['inputs']['lora_name'],TURBOS['pika6_kijai']['lora'])
        self.assertNotEqual(TURBOS['pika6']['lora'],TURBOS['pika6_kijai']['lora'])
        self.assertIn('Kijai',TURBOS['pika6_kijai']['label'])

    def test_six_step_sigmas_take_no_model_when_tara_or_windows_patch_it(self):
        # A Pika 6-step job with TARA or pure windows failed: "ManualSigmas.execute() got an unexpected keyword
        # argument 'model'". The patched MODEL goes to the guider only; ManualSigmas keeps its fixed sigmas.
        windows={'enabled':True,'scope':'all','window_frames':22,'overlap_frames':5}
        for options in ({'conditioning_mode':'tara'},{'temporal_windows':windows},{'conditioning_mode':'tara','temporal_windows':windows}):
            with self.subTest(options=options):
                graph=self.graph(**options)
                self.assertEqual(graph['13']['class_type'],'ManualSigmas');self.assertNotIn('model',graph['13']['inputs'])
                patched='80' if 'temporal_windows' in options else '21'
                self.assertEqual(graph['10']['inputs']['model'],[patched,0])
        # Other step counts keep a BasicScheduler, which must follow the patched model.
        graph=self.graph(steps=8,conditioning_mode='tara')
        self.assertEqual(graph['13']['class_type'],'BasicScheduler');self.assertEqual(graph['13']['inputs']['model'],['21',0])

    def test_override_sampler_keeps_published_six_step_sigmas(self):
        graph=self.graph(profile='motion_tara',conditioning_mode='tara',sampler_name='euler')
        self.assertEqual(graph['12']['inputs']['sampler_name'],'euler')
        self.assertEqual(graph['13']['class_type'],'ManualSigmas')
        self.assertEqual(graph['9']['inputs']['conditioning_mode'],'tara')

    def test_custom_step_count_uses_requested_number_not_six(self):
        for steps in (1,4,8,12):
            graph=self.graph(steps=steps)
            self.assertEqual(graph['13']['class_type'],'BasicScheduler')
            self.assertEqual(graph['13']['inputs']['steps'],steps)
            self.assertEqual(graph['12']['inputs']['sampler_name'],'lcm')

    def test_existing_default_still_euler_with_original_schedule(self):
        graph=h3_graph('g.mp4',['r.png'],'prompt',512,288,22,22,'headswap',42,8,'original',[],'human',0)
        self.assertEqual(graph['12']['inputs']['sampler_name'],'euler')
        self.assertEqual(graph['13']['class_type'],'BasicScheduler')
        self.assertEqual(graph['13']['inputs']['scheduler'],'beta')

    def test_h3_upscale_works_when_first_schedule_is_manual(self):
        graph=self.graph(profile='sharpness',upscale={'method':'h3','model':'upscaler.safetensors','steps':2,'denoise':.15})
        self.assertEqual(graph['13']['class_type'],'ManualSigmas')
        self.assertEqual(graph['34']['class_type'],'BasicScheduler')
        self.assertEqual(graph['34']['inputs']['steps'],2)

    def test_open_h3_stage_two_keeps_its_own_turbo_and_sampler(self):
        graph=self.graph(profile='sharpness',sampler_name='heun',upscale={'method':'regenerate','steps':2})
        self.assertEqual(graph['12']['inputs']['sampler_name'],'heun')
        self.assertEqual(graph['35']['inputs']['sampler_name'],'er_sde')
        self.assertEqual(graph['33']['inputs']['sigmas'],REGENERATE_SIGMAS[2])
        self.assertNotEqual(graph['72']['inputs']['lora_name'],TURBOS['pika6']['lora'])

    def test_request_defaults_and_incompatible_base(self):
        request={'mode':'motion','prompt':'motion_transfer: guide','quality':'480p',
                 'video':{'start_seconds':0,'end_seconds':4.5},'processing':{},
                 'subject_guidance':{'representation':'original','bindings':[]}}
        options={'turbo':'pika6'}
        server.validate_request(request,options,[1])
        self.assertEqual(options['steps'],6)
        with self.assertRaisesRegex(ValueError,'sampler'):
            server.validate_request(request,{'sampler_name':'invented'},[1])
        with self.assertRaisesRegex(ValueError,'Ref2VA'):
            server.validate_request(request,{'turbo':'pika6','base':'omniref'},[1])

    def test_default_download_includes_adapter_and_notices(self):
        spec=importlib.util.spec_from_file_location('download_models',ROOT/'scripts/download_models.py')
        downloader=importlib.util.module_from_spec(spec);spec.loader.exec_module(downloader)
        manifest=json.loads((ROOT/'config/model-repos.example.json').read_text())
        for profile in ('character','motion','headswap','sharpness'):
            selected={m['id']:m for m in downloader.selected_models(manifest,[profile])}
            self.assertTrue({'turbo_pika6','pika_license','pika_notice','pika_upstream_license'} <= set(selected))
            self.assertEqual(selected['turbo_pika6']['destination'],'loras/'+TURBOS['pika6']['lora'])
            self.assertRegex(selected['turbo_pika6']['revision'],r'^[0-9a-f]{40}$')
            self.assertEqual(selected['turbo_pika6']['repo_id'],'Pika-Labs/Pika-H3-Flex')
            self.assertEqual(selected['turbo_pika6']['filename'],
                             'comfy/loras/pika_h3_flex_ref2va_comfy_bf16.safetensors')
            self.assertEqual(selected['turbo_pika6']['sha256'],
                             'e4d058fbd027377b925a0ee607b514ddd9037873fee3afa05d73b302e6f7f8e1')
        aliases=json.loads((ROOT/'backend/legacy_loras.json').read_text())
        self.assertNotIn(TURBOS['pika6']['lora'],aliases)
        self.assertNotIn(TURBOS['pika6']['lora'],aliases.values())
