import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import molmo_pointing


class PointNormalizationTests(unittest.TestCase):
    def test_object_id_time_order_and_trim_offset(self):
        points,warnings=molmo_pointing.normalize_points([[7,.5,100,50],[7,0,80,40]],200,100,10,12)
        self.assertEqual([p['time_seconds'] for p in points],[10,10.5])
        self.assertEqual(points[1]['object_id'],7)
        self.assertEqual(points[1]['x'],.5)
        self.assertEqual(points[1]['y'],.5)
        self.assertEqual(points[1]['frame_index_24fps'],252)
        self.assertEqual(warnings,[])

    def test_invalid_points_are_reported_not_turned_into_marks(self):
        points,warnings=molmo_pointing.normalize_points([[1,2,20,20],[1,0,100,2],[1,0,float('nan'),2],[-1,0,2,2],[1.5,0,2,2]],100,100,0,2)
        self.assertEqual(points,[])
        self.assertIn('5 invalid',warnings[0])
        for query,start,end in [('',0,1),('x',-1,1),('x',2,1),('x',0,31),('x',0,float('nan'))]:
            with self.assertRaises(ValueError):molmo_pointing.validate_request(query,start,end)

    def test_missing_local_configuration_does_not_download(self):
        with patch.dict(os.environ,{},clear=True),patch.object(molmo_pointing.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'not configured'):
                molmo_pointing.point_video('video','person',0,1,'.')
            run.assert_not_called()

    def test_bridge_uses_isolated_worker_and_preserves_proposals(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);python=root/'python';python.touch();model=root/'model';model.mkdir();(model/'config.json').write_text('{}')
            payload={'points':[{'object_id':2,'time_seconds':.5,'x':.2,'y':.3}]}
            def execute(args,**kwargs):
                Path(args[args.index('--output')+1]).write_text(json.dumps(payload))
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            with patch.dict(os.environ,{'HENGE_MOLMO_PYTHON':str(python),'HENGE_MOLMO_MODEL':str(model)}),patch.object(molmo_pointing.subprocess,'run',side_effect=execute) as run,patch.object(molmo_pointing,'point_previews',return_value=['preview']):
                result=molmo_pointing.point_video('video','person',0,1,root)
            self.assertEqual(result['points'],payload['points'])
            self.assertEqual(result['previews'],['preview'])
            self.assertEqual(run.call_args.kwargs['timeout'],900)


class MatchPeopleTests(unittest.TestCase):
    def test_three_keyframes_per_shot_and_short_shots_skipped(self):
        shots=molmo_pointing.shot_keyframes(0,10,[4,4.1,7])
        self.assertEqual([(s['start'],s['end']) for s in shots],[(0,4),(4.1,7),(7,10)])
        self.assertEqual(shots[0]['times'],[.8,2.,3.2])

    def test_person_needs_two_consistent_keyframes_per_shot(self):
        shots=molmo_pointing.shot_keyframes(0,4,[2])
        m=lambda ref,shot,t,ok:dict(ref=ref,shot=shot,time=t,x=.5,y=.5,ok=ok)
        matches=[m(0,0,.4,True),m(0,0,1.,True),m(0,0,1.6,False),m(0,1,2.4,True),m(0,1,3.,False),m(0,1,3.6,False),m(1,1,2.4,True),m(1,1,3.,True)]
        people=molmo_pointing.summarize_matches(matches,shots,2)['people']
        self.assertEqual([a['time_seconds'] for a in people[0]['anchors']],[.4])
        self.assertEqual(people[0]['missing_shots'],[1])
        self.assertEqual([a['shot'] for a in people[1]['anchors']],[1])
        self.assertEqual(people[1]['missing_shots'],[0])

    def test_match_limits(self):
        for people,start,end in [(0,0,1),(7,0,1),(1,0,121),(1,2,1)]:
            with self.assertRaises(ValueError):molmo_pointing.validate_match(people,start,end)


class SplitPointTests(unittest.TestCase):
    def test_points_end_shots_inside_a_take_and_cuts_stay_clean(self):
        from workflows import split_at_points
        shots=split_at_points(254,107,22,[98,175,236],[60,140],every_cut=True)
        self.assertEqual([(s['start'],s['start']+s['frames']) for s in shots],[(0,98),(98,175),(175,254)])  # 236 would leave an 18-frame shot (< min_gap)
        self.assertTrue(all(s['overlap']==0 for s in shots))
        # One take, no cuts: the shot ends at the last suggested point in reach and the next carries context.
        shots=split_at_points(300,107,22,[],[80,150,250])
        self.assertEqual([(s['start'],s['frames'],s['overlap']) for s in shots],[(0,80,0),(58,92,22),(128,107,22),(213,87,22)])


class PointingApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        cls.env=patch.dict(os.environ,{'HENGE_DATA_DIR':cls.folder.name,'HENGE_BACKEND':'comfyui'})
        cls.env.start()
        import server
        from fastapi.testclient import TestClient
        cls.server=server;cls.client=TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop();cls.folder.cleanup()

    def test_unconfigured_and_bad_interval_fail_before_inference(self):
        with patch.object(self.server,'pointing_status',return_value={'configured':False}):
            r=self.client.post('/assistant/point-video',files={'video':('x.mp4',b'video','video/mp4')},data={'query':'man','start':0,'end':1})
        self.assertEqual(r.status_code,409)
        r=self.client.post('/assistant/point-video',files={'video':('x.mp4',b'video','video/mp4')},data={'query':'man','start':0,'end':31})
        self.assertEqual(r.status_code,400)

    def test_api_returns_points_without_starting_generation(self):
        expected={'points':[dict(object_id=1,time_seconds=.5,x=.2,y=.3)],'previews':[]}
        with patch.object(self.server,'pointing_status',return_value={'configured':True}),patch.object(self.server,'probe',return_value={'duration':2}),patch.object(self.server.molmo_pointing,'point_video',return_value=expected) as point,patch.object(self.server,'execute_graph') as generate:
            r=self.client.post('/assistant/point-video',files={'video':('x.mp4',b'video','video/mp4')},data={'query':'man','start':0,'end':1})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['points'],expected['points'])
        self.assertEqual(point.call_args.args[1:4],('man',0.,1.))
        generate.assert_not_called()

    def test_match_people_api_saves_photos_and_does_not_generate(self):
        import io
        from PIL import Image
        buf=io.BytesIO();Image.new('RGB',(8,8)).save(buf,'PNG')
        expected={'people':[{'person':1,'anchors':[],'missing_shots':[0]}],'shots':[],'previews':[]}
        with patch.object(self.server,'pointing_status',return_value={'configured':True}),patch.object(self.server,'probe',return_value={'duration':5,'width':640,'height':360}),patch.object(self.server.molmo_pointing,'match_people',return_value=expected) as match,patch.object(self.server,'execute_graph') as generate:
            r=self.client.post('/assistant/match-people',files=[('video',('x.mp4',b'video','video/mp4')),('people',('a.png',buf.getvalue(),'image/png'))],data={'start':0,'end':5})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['frame_width'],640)
        self.assertEqual(len(match.call_args.args[1]),1)
        generate.assert_not_called()
        r=self.client.post('/assistant/match-people',files=[('video',('x.mp4',b'video','video/mp4'))],data={'start':0,'end':5})
        self.assertEqual(r.status_code,400)

    def test_ask_video_api_answers_without_generating(self):
        with patch.object(self.server,'pointing_status',return_value={'configured':True}),patch.object(self.server,'probe',return_value={'duration':5,'width':640,'height':360}),patch.object(self.server.molmo_pointing,'ask_video',return_value={'answer':'two people talk'}) as ask,patch.object(self.server,'execute_graph') as generate:
            r=self.client.post('/assistant/ask-video',files={'video':('x.mp4',b'video','video/mp4')},data={'question':'who talks?','start':0,'end':5})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['answer'],'two people talk')
        self.assertEqual(ask.call_args.args[1],'who talks?');generate.assert_not_called()
        r=self.client.post('/assistant/ask-video',files={'video':('x.mp4',b'video','video/mp4')},data={'question':'','start':0,'end':5})
        self.assertEqual(r.status_code,400)

    def test_local_comfy_is_freed_before_molmo_only_when_local(self):
        with patch.object(self.server,'REMOTE',None),patch.object(self.server,'URL','http://127.0.0.1:8189'),patch.object(self.server.requests,'post') as post:
            self.server.free_local_comfy()
        post.assert_called_once();self.assertEqual(post.call_args.args[0],'http://127.0.0.1:8189/free')
        self.assertEqual(post.call_args.kwargs['json'],{'unload_models':True,'free_memory':True})
        for remote,url in [(object(),'http://127.0.0.1:8189'),(None,'http://10.0.0.5:8188')]:
            with patch.object(self.server,'REMOTE',remote),patch.object(self.server,'URL',url),patch.object(self.server.requests,'post') as post:
                self.server.free_local_comfy()
            post.assert_not_called()
        self.assertIs(self.server.molmo_pointing.BEFORE_RUN,self.server.free_local_comfy)

    def test_guide_caption_is_skipped_without_molmo(self):
        job={'id':'0'*32,'request':{'mode':'swap','video':{'start_seconds':0,'end_seconds':2}},'assets':{'video':'x.mp4'}}
        with patch.object(self.server.molmo_pointing,'available',return_value=False),patch.object(self.server.molmo_pointing,'ask_video') as ask:
            self.assertEqual(self.server.guide_caption(job),'')
        ask.assert_not_called()


if __name__=='__main__':unittest.main()
