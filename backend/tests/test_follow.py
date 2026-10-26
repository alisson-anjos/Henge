import importlib.util,unittest
from pathlib import Path
import torch
spec=importlib.util.spec_from_file_location('follow',Path(__file__).resolve().parents[1]/'comfy_nodes'/'henge'/'follow.py')
follow=importlib.util.module_from_spec(spec);spec.loader.exec_module(follow)

def scene(swap=False,n=6,h=64,w=96):
    """Two people: red shirt / blue pants on one side, yellow shirt / green pants on the other (swapped after a cut)."""
    images=torch.full((n,h,w,3),.5);masks=torch.zeros(n,2,h,w,dtype=torch.bool)
    people=[((1,0,0),(0,0,1)),((1,1,0),(0,.6,0))]
    for t,(top,bottom) in enumerate(people):
        x0=(56 if (t==0)==(not swap) else 8) if swap else (8 if t==0 else 56)
        masks[:,t,8:56,x0:x0+30]=True
        images[:,8:32,x0:x0+30]=torch.tensor(top);images[:,32:56,x0:x0+30]=torch.tensor(bottom)
    return images,masks

def subject(sid,**extra):return {'id':sid,'label':sid,'anchors':[],**extra}

class FollowTest(unittest.TestCase):
    def test_marks_then_recognition_after_people_swap_places(self):
        images,masks=scene()
        a={'x':.25,'y':.5,'time_seconds':0,'frame_width':96,'frame_height':64};b={**a,'x':.75}
        picked,warn=follow.choose([subject('A',anchors=[a]),subject('B',anchors=[b])],masks,images,0)
        self.assertEqual({s['id']:t for t,s,_ in picked},{'A':0,'B':1});self.assertEqual(warn,[])
        rep=follow.report(picked,masks,images,warn);looks={s['id']:s['signature'] for s in rep['subjects']}
        # After a cut the two swap sides (and track order): recognised by look, not by position.
        images2,masks2=scene(swap=True)
        masks2=masks2[:,[1,0]]
        picked,warn=follow.choose([subject('A',signature=looks['A']),subject('B',signature=looks['B'])],masks2,images2,10)
        got={s['id']:t for t,s,how in picked};self.assertEqual(got,{'A':1,'B':0});self.assertTrue(all(how=='look' for *_,how in picked))
    def test_carry_follows_position_without_a_cut(self):
        images,masks=scene()
        picked,_=follow.choose([subject('A',carry={'x':.7,'y':.5})],masks,images,5)
        self.assertEqual([(t,how) for t,_,how in picked],[(1,'carry')])
    def test_unknown_person_is_reported_not_fatal(self):
        images,masks=scene()
        picked,warn=follow.choose([subject('A')],masks,images,5)
        self.assertEqual(picked,[]);self.assertIn('never seen',warn[0])
    def test_points_track_the_person(self):
        images,masks=scene();pts=follow.points(masks[:,1])
        self.assertTrue(all(p and .55<p[0]<.95 for p in pts))

if __name__=='__main__':unittest.main()
