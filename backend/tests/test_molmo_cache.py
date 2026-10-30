import sys
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

def job(path,**options):
    return {'id':path.stem,'assets':{'video':path.name},'options':options}

def test_same_clip_reuses_the_answer_and_refresh_asks_again(tmp_path):
    a=tmp_path/'a.mp4';b=tmp_path/'b.mp4';a.write_bytes(b'same clip');b.write_bytes(b'same clip')
    calls=[]
    def ask(video,question,start,end,folder):calls.append((video.name,question,start,end));return {'answer':f'answer {len(calls)}'}
    with mock.patch.object(server,'INPUT',tmp_path),mock.patch.object(server,'MOLMO_CACHE',tmp_path),\
         mock.patch.object(server.molmo_pointing,'ask_video',side_effect=ask),mock.patch.object(server.molmo_pointing,'location',return_value='backend'),\
         mock.patch.object(server,'molmo_settings',return_value={}):
        first=server.molmo_answer(job(a),'Describe the video',0,4,tmp_path)
        # Another job, another file name, the same bytes and interval: no second Molmo2 run.
        assert server.molmo_answer(job(b),'Describe the video',0,4,tmp_path)==first and len(calls)==1
        assert server.molmo_answer(job(b,molmo_refresh=True),'Describe the video',0,4,tmp_path)=={'answer':'answer 2'}
        # The refreshed answer replaced the saved one.
        assert server.molmo_answer(job(a),'Describe the video',0,4,tmp_path)=={'answer':'answer 2'} and len(calls)==2
        server.molmo_answer(job(a),'Describe the video',2,4,tmp_path);server.molmo_answer(job(a),'Who is on the left?',0,4,tmp_path)
        assert len(calls)==4
