import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import workflows


@pytest.mark.parametrize('separator', ['/', '\\'])
def test_input_normalization_preserves_resolved_loader_names(monkeypatch,separator):
    installed={}
    graph={}
    for loader,key in workflows.LOADERS.items():
        name=f'henge/{loader}.safetensors'
        installed[loader]={name.replace('/',separator)}
        graph[loader]={'class_type':loader,'inputs':{key:name}}
    monkeypatch.setattr(workflows,'INSTALLED',installed)
    graph['video']={'class_type':'HengeLoadShot','inputs':{
        'video':r'henge\job\shot.mp4','pictures':'[]','width':864}}
    graph['image']={'class_type':'LoadImage','inputs':{'image':r'henge\job\ref.png'}}

    result=server.posix_inputs(workflows.localize_loras(graph))

    for loader,key in workflows.LOADERS.items():
        assert result[loader]['inputs'][key] in installed[loader]
    assert result['video']['inputs']=={'video':'henge/job/shot.mp4','pictures':'[]','width':864}
    assert result['image']['inputs']['image']=='henge/job/ref.png'
