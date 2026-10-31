import importlib.util
import json
from pathlib import Path

import torch

spec=importlib.util.spec_from_file_location('point_tracking',Path(__file__).resolve().parents[1]/'comfy_nodes/henge/point_tracking.py')
point_tracking=importlib.util.module_from_spec(spec);spec.loader.exec_module(point_tracking)


def subject(time=3/24):
    return {'id':'subject','label':'Subject 1','anchors':[{'x':.25,'y':.5,'time_seconds':time,'frame_width':16,'frame_height':8}]}


def test_point_seeds_bidirectional_tracking_without_crossing_cuts():
    images=torch.zeros(8,16,16,3)
    images[:,0,0,0]=torch.arange(8)
    calls=[]
    def detect(**kw):
        assert kw['refine_iterations']==1, 'Mask-only refinement can erase the point segmentation'
        # Letterboxing an original 16x8 frame into 16x16 adds four pixels above it.
        assert json.loads(kw['positive_coords'])==[{'x':4,'y':8}]
        assert int(kw['image'][0,0,0,0])==3
        mask=torch.zeros(1,16,16);mask[:,6:10,2:7]=1
        return mask,None
    def track(**kw):
        calls.append(kw['images'][:,0,0,0].tolist())
        assert 'conditioning' not in kw
        assert kw['max_objects']==1
        return ({'packed_masks':kw['initial_mask'][:,None].repeat(len(kw['images']),1,1,1)},)
    masks,picked,warnings,anchored=point_tracking.track_marks(images,object(),[subject()],0,[0,2,6,8],detect,track,lambda x:x)
    assert calls==[[3,4,5],[3,2]]
    assert masks.shape==(8,1,16,16)
    assert masks[2:6].any() and not masks[:2].any() and not masks[6:].any()
    assert picked[0][2]=='mark' and warnings==[] and anchored=={'subject'}


def test_failed_point_is_reported_without_selecting_an_unrelated_mask():
    def detect(**kw):
        mask=torch.zeros(1,16,16);mask[:,0:2,0:2]=1
        return mask,None
    def track(**kw):raise AssertionError('No tracking without a mask under the point')
    masks,picked,warnings,anchored=point_tracking.track_marks(torch.zeros(8,16,16,3),object(),[subject()],0,[0,8],detect,track,lambda x:x)
    assert masks.shape[1]==0 and picked==[] and len(warnings)==1 and anchored=={'subject'}


def test_marks_outside_segment_are_left_for_continuity_tracking():
    def unexpected(**kw):raise AssertionError('Out-of-segment marks must not seed tracking')
    result=point_tracking.track_marks(torch.zeros(8,16,16,3),object(),[subject(10)],0,[0,8],unexpected,unexpected,lambda x:x)
    assert result[1:]==([],[],set())


def test_guide_uses_point_mask_when_automatic_detection_finds_nobody(monkeypatch):
    import ast
    import sys
    from types import SimpleNamespace
    source=Path(__file__).resolve().parents[1]/'comfy_nodes/henge/__init__.py'
    cls=next(node for node in ast.parse(source.read_text()).body if isinstance(node,ast.ClassDef) and node.name=='HengeGuide')
    images=torch.zeros(8,16,16,3)
    mask=torch.ones(8,1,16,16,dtype=torch.bool)
    marked={**subject(),'hex':'#32B45A','picture_slots':[1]}
    def unexpected(*args,**kwargs):raise AssertionError('Automatic detection must not replace an explicit mark')
    clip=SimpleNamespace(tokenize=lambda x:x,encode_from_tokens_scheduled=lambda x:x)
    scope={'torch':torch,'json':json,'DEFAULT_MASK':{},'track_marks':lambda *a:(mask,[(0,marked,'mark')],[],{'subject'}),
        'scene_cuts':lambda x:[],'track_scenes':unexpected,'blur_guide':lambda x,*a:x,
        'shape_mask':lambda x,*a:x.float(),'mask_region':lambda x,*a:x,'ui_report':lambda x:x,
        'follow':SimpleNamespace(report=lambda *a:{'subjects':[],'warnings':[]}),
        'folder_paths':SimpleNamespace(get_full_path_or_raise=lambda *a:'checkpoint'),
        'comfy':SimpleNamespace(sd=SimpleNamespace(load_checkpoint_guess_config=lambda *a,**kw:(object(),clip))),
        'mm':SimpleNamespace(unload_all_models=lambda:None,soft_empty_cache=lambda:None)}
    monkeypatch.setitem(sys.modules,'comfy_extras.nodes_sam3',SimpleNamespace(SAM3_Detect=SimpleNamespace(execute=unexpected),SAM3_VideoTrack=SimpleNamespace(execute=unexpected)))
    monkeypatch.setitem(sys.modules,'comfy.ldm.sam3.tracker',SimpleNamespace(unpack_masks=lambda x:x,pack_masks=lambda x:x))
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(source),'exec'),scope)
    result=scope['HengeGuide']().prepare(images,'mask',json.dumps([marked]),'human',0,'sam','body')['result']
    assert result[1].all()
    assert result[2][1].all()
    scope['track_marks']=lambda *a:(mask[:,:0],[],['Point segmentation failed'],{'subject'})
    import pytest
    with pytest.raises(ValueError,match='SAM could not segment'):
        scope['HengeGuide']().prepare(images,'mask',json.dumps([marked]),'human',0,'sam','body')
