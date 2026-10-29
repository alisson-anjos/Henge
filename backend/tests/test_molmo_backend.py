import json,sys
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import molmo_pointing
from comfy_client import referenced_files

def test_files_named_inside_a_molmo_task_are_sent_to_the_worker(tmp_path):
    for rel in ('henge/a/video.mp4','henge/a/ref.png','henge/a/key0.jpg'):
        (tmp_path/rel).parent.mkdir(parents=True,exist_ok=True);(tmp_path/rel).write_bytes(b'x')
    task={'mode':'match','video':'henge/a/video.mp4','refs':['henge/a/ref.png'],'keys':[{'shot':0,'path':'henge/a/key0.jpg'}]}
    graph={'1':{'class_type':'HengeMolmo','inputs':{'task':json.dumps(task)}}}
    assert referenced_files(graph,tmp_path)==['henge/a/video.mp4','henge/a/ref.png','henge/a/key0.jpg']

def test_without_local_molmo_tasks_run_on_the_backend(tmp_path):
    sent={}
    def runner(request):sent.update(request);return '{"answer":"two fighters"}'
    out=tmp_path/'answer.json'
    with mock.patch.object(molmo_pointing,'SETTINGS',lambda:{'enabled':True,'image_quality':'fast'}),\
         mock.patch.object(molmo_pointing,'local_configured',lambda:False),\
         mock.patch.object(molmo_pointing,'REMOTE_READY',lambda:True),mock.patch.object(molmo_pointing,'REMOTE_RUNNER',runner):
        assert molmo_pointing.location()=='backend' and molmo_pointing.available()
        molmo_pointing.run_worker(['--mode','ask','--video','/x/v.mp4','--query','who?','--start','0','--end','4','--output',str(out)])
    assert json.loads(out.read_text())=={'answer':'two fighters'}
    assert sent=={'mode':'ask','video':'/x/v.mp4','query':'who?','start':0.,'end':4.,'max_crops':4}

def test_turned_off_or_no_backend_means_unavailable():
    with mock.patch.object(molmo_pointing,'SETTINGS',lambda:{'enabled':False}),mock.patch.object(molmo_pointing,'REMOTE_READY',lambda:True),\
         mock.patch.object(molmo_pointing,'REMOTE_RUNNER',lambda r:'{}'):
        assert molmo_pointing.location() is None
    with mock.patch.object(molmo_pointing,'SETTINGS',lambda:{'enabled':True}),mock.patch.object(molmo_pointing,'local_configured',lambda:False),\
         mock.patch.object(molmo_pointing,'REMOTE_READY',lambda:False):
        assert not molmo_pointing.available()
