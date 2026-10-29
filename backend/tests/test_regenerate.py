"""Contracts for the optional native Open-H3 refinement stage (no GPU required)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from workflows import h3_graph, REGENERATE, REGENERATE_SIGMAS, BASES

class RegenerateTests(unittest.TestCase):
    def graph(self,steps=2):
        return h3_graph('clip.mp4',[],'LMS instruction',1344,768,22,22,'sharpness',42,8,'original',[],'human',0,
                        upscale={'method':'regenerate','width':2560,'height':1440,'steps':steps,'prompt':'A person walks.'},gen_audio=True)

    def test_refiner_has_independent_base_and_text_conditioning(self):
        g=self.graph()
        self.assertEqual(g['70']['inputs']['unet_name'],BASES['h3']['unet'])
        self.assertEqual(g['70']['inputs']['unet_name'],g['1']['inputs']['unet_name'])
        self.assertEqual(g['72']['inputs']['model'],['71',0])
        self.assertEqual(g['73']['inputs']['model'],['72',0])
        self.assertEqual(g['72']['inputs']['lora_name'],REGENERATE['turbo'])
        self.assertEqual(g['73']['inputs']['lora_name'],REGENERATE['refiner'])
        self.assertEqual(g['74']['inputs']['model'],['73',0])
        self.assertEqual(g['74']['inputs']['lora_name'],REGENERATE['lms'])
        self.assertEqual(g['74']['inputs']['strength_model'],1.)
        self.assertEqual(g['34']['inputs']['model'],['74',0])
        self.assertEqual(g['34']['inputs']['conditioning'],['76',0])
        self.assertEqual(g['76']['class_type'],'MiniMaxH3AddGuide')
        self.assertEqual(g['76']['inputs']['positive'],['32',0])
        self.assertEqual(g['76']['inputs']['latent'],['31',0])
        self.assertEqual(g['76']['inputs']['image'],['75',0])
        self.assertEqual(g['75']['inputs']['video'],'clip.mp4')
        self.assertEqual(g['75']['inputs']['pictures'],'[]')
        self.assertEqual((g['75']['inputs']['width'],g['75']['inputs']['height']),(2560,1440))
        self.assertEqual(g['32']['class_type'],'CLIPTextEncode')
        self.assertEqual(g['32']['inputs']['text'],'A person walks.')
        self.assertNotEqual(g['3']['inputs']['lora_name'],REGENERATE['refiner'])

    def test_joint_latent_and_audio_survive_native_upscale(self):
        g=self.graph()
        self.assertEqual(g['31']['class_type'],'MiniMaxH3LatentUpscaleWithModel')
        self.assertEqual(g['31']['inputs']['samples'],['14',0])
        self.assertEqual((g['31']['inputs']['width'],g['31']['inputs']['height']),(2560,1440))
        self.assertEqual(g['37']['inputs']['latent_image'],['31',0])
        self.assertEqual(g['16']['inputs']['samples'],['38',0])
        self.assertEqual(g['50']['inputs']['samples'],['37',0])

    def test_schedules_and_sampler_follow_supplied_workflow(self):
        for count in (2,3):
            g=self.graph(count)
            self.assertEqual(g['33']['inputs']['sigmas'],REGENERATE_SIGMAS[count])
            self.assertEqual(g['35']['inputs']['sampler_name'],'er_sde')
            self.assertEqual(g['36']['inputs']['noise_seed'],42)
        with self.assertRaises(ValueError):self.graph(4)

    def test_missing_native_nodes_and_weights_disable_mode(self):
        status=server.regenerate_requirements({})
        self.assertFalse(status['available'])
        self.assertIn('MiniMaxH3LatentUpscaleWithModel',status['missing_nodes'])
        self.assertEqual(len(status['missing_models']),5)

    def test_complete_inventory_accepts_subfolder_model_names(self):
        info={k:{} for k in ('MiniMaxH3LatentUpscaleWithModel','ManualSigmas','BasicGuider','MiniMaxH3AddGuide')}
        for loader,key,names in [('UNETLoader','unet_name',[REGENERATE['base']]),('LoraLoaderModelOnly','lora_name',[REGENERATE['turbo'],REGENERATE['refiner'],REGENERATE['lms']]),('LatentUpscaleModelLoader','model_name',[REGENERATE['upscaler']])]:
            info[loader]={'input':{'required':{key:[['custom/'+n.split('/')[-1] for n in names]]}}}
        self.assertTrue(server.regenerate_requirements(info)['available'])

    def test_manual_description_does_not_require_vlm_or_molmo(self):
        with patch.object(server,'prepare_evidence') as evidence,patch.object(server,'execute_graph') as inference:
            self.assertEqual(server.regenerate_scene_prompt({'options':{'regenerate_prompt':' A person walks. '}}),'A person walks.')
        evidence.assert_not_called();inference.assert_not_called()

    def test_unsupported_mode_resolution_steps_and_prompt_rejected(self):
        base={'mode':'sharpness','prompt':'','quality':'1440p','video':{'start_seconds':0,'end_seconds':1}}
        for changes,options in [({'mode':'motion'},{'regenerate_steps':2}),({'quality':'2160p'},{}),({}, {'regenerate_steps':4}),({}, {'regenerate_prompt':None})]:
            with self.subTest(changes=changes,options=options),self.assertRaises(ValueError):
                server.validate_request({**base,**changes},{'upscale_method':'regenerate',**options},[])

    def test_regenerate_download_profile_has_no_fl2va_dependency(self):
        import json
        manifest=json.loads((Path(__file__).resolve().parents[2]/'config/model-repos.example.json').read_text())
        selected=[m for m in manifest['models'] if set(m['profiles']) & {'common','regenerate'}]
        self.assertFalse(any('fl2va' in m['destination'].lower() for m in selected))
        self.assertIn('diffusion_models/'+BASES['h3']['unet'],[m['destination'] for m in selected])

    def test_long_single_refinement_is_bounded_without_losing_duration(self):
        job={'request':{'mode':'sharpness','video':{'start_seconds':0,'end_seconds':13.458333},'processing':{'mode':'single','requested_seconds_per_shot':15,'context_frames':22,'cut_mode':'off'}},'options':{'upscale_method':'regenerate'}}
        shots,context=server.plan_shots(job)
        self.assertGreater(len(shots),1)
        self.assertTrue(all(s['length']<=107 for s in shots))
        self.assertEqual(sum(s['frames']-s['overlap'] for s in shots),323)
        self.assertEqual(context,22)
        self.assertTrue(all(s['length']%17==5 for s in shots))
        job['options']['upscale_method']='h3'
        old,_=server.plan_shots(job)
        self.assertEqual(len(old),1)
        self.assertEqual(old[0]['length'],328)
