import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requirements_check
from workflows import MODELS

def test_models_comfyui_lists_from_another_drive_count_as_installed(tmp_path):
    # COMFY_ROOT/models is empty: every file lives on another drive that extra_model_paths.yaml maps into ComfyUI.
    needed=[rel for _,_,rel in requirements_check.base_files()]
    needed+=['loras/'+MODELS['character']['lora'],'loras/'+MODELS['character']['adapter']]
    names={rel.split('/',1)[1] for rel in needed}
    info={'LoraLoaderModelOnly':{'input':{'required':{'lora_name':[sorted(n for n in names if n.startswith('henge/'))]}}},
          'AnyLoader':{'input':{'required':{'name':[sorted(names)],'steps':['INT',{}]}}}}
    listed=requirements_check.comfy_listed(info)
    _,ready_without,_=requirements_check.check(tmp_path,MODELS)
    rows,ready_with,_=requirements_check.check(tmp_path,MODELS,listed)
    assert not ready_without['character'] and ready_with['character']
    assert all(r['state']=='installed' for r in rows if 'character' in r['groups'] or 'common' in r['groups'])

def test_comfy_listed_keeps_only_model_files():
    info={'X':{'input':{'required':{'a':[['m\\sub\\x.safetensors','euler','y.gguf']],'b':['INT',{}]},'optional':{'c':[['z.ckpt']]}}}}
    assert requirements_check.comfy_listed(info)=={'m/sub/x.safetensors','y.gguf','z.ckpt'}
