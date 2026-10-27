import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from edit_modes import shot_swap_plan

class ShotSwapTests(unittest.TestCase):
    def test_single_visible_subject_uses_only_its_reference(self):
        binding={'id':'pilot','color':'purple','picture_slots':[3]}
        local,refs,prompt=shot_swap_plan([binding],['a','b','c'],[{'slot':3,'description':'a pilot in a flight suit'}],'2d',True)
        self.assertEqual(refs,['c']);self.assertEqual(local[0]['picture_slots'],[1])
        self.assertEqual(binding['picture_slots'],[3])
        self.assertIn('purple-marked',prompt);self.assertNotIn('<Picture 3>',prompt)
        self.assertNotIn('<Subject 2>',prompt)

    def test_multiple_visible_subjects_renumber_labels_and_descriptions(self):
        bindings=[{'id':'a','color':'green','picture_slots':[2]}, {'id':'b','color':'purple','picture_slots':[4]}]
        local,refs,prompt=shot_swap_plan(bindings,['a','b','c','d'],[{'slot':2,'description':'red coat'},{'slot':4,'description':'blue suit'}],'2d',True)
        self.assertEqual(refs,['b','d'])
        self.assertIn('tagged <Picture 1>',prompt);self.assertIn('tagged <Picture 2>',prompt)
        self.assertNotIn('<Picture 4>',prompt)
        self.assertIn('red coat',prompt);self.assertIn('blue suit',prompt)

if __name__=='__main__':unittest.main()

class ShotGenerationTests(unittest.TestCase):
    def test_empty_tracking_skips_video_model_and_keeps_original(self):
        import tempfile
        from unittest.mock import patch
        import server
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inp=root/'input';work=root/'jobs'/'job';work.mkdir(parents=True)
            (inp/'henge'/'job').mkdir(parents=True)
            binding={'id':'a','label':'A','color':'green','picture_slots':[1],'anchors':[]}
            job={'id':'job','status':'running','options':{'prepare_references':False},
                 'request':{'mode':'swap','quality':'480p','processing':{},'video':{'start_seconds':0,'end_seconds':1},'subject_guidance':{'bindings':[binding]}},
                 'assets':{'video':'source.mp4','pictures':{'1':'ref.png'}},'video_info':{'width':640,'height':480,'audio':False},
                 'plan':{'adapt_reference':False,'representation':'2d','source_kind':'human','prompt':'original'}}
            def save(record,**changes):record.update(changes)
            def run(args):Path(args[-1]).write_bytes(b'video')
            shot={'start':0,'frames':24,'overlap':0,'length':39}
            with patch.object(server,'INPUT',inp),patch.object(server,'job_path',return_value=work),patch.object(server,'save',side_effect=save),patch.object(server,'load',return_value=job),patch.object(server,'run',side_effect=run),patch.object(server,'plan_shots',return_value=([shot],0)),patch.object(server,'subject_looks',return_value={'a':{}}),patch.object(server,'execute_graph',return_value={'8':{'henge_tracks':['{"subjects":[],"warnings":[]}']}}) as execute,patch.object(server,'finalize') as finalize:
                server.generate(job)
            self.assertEqual(execute.call_count,1)
            self.assertNotIn('14',execute.call_args.args[1])
            self.assertEqual(job['shot_plans'][0]['action'],'keep_original')
            self.assertTrue((work/'piece_000.mp4').exists())
            finalize.assert_called_once()
