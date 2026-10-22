from huggingface_hub import hf_hub_download
from pathlib import Path
import shutil
root=Path('/data/kagemane-comfy-backend/models')
for repo,name in [('Comfy-Org/Fibo-2.0','diffusion_models/fibo2_edit_turbo_int8_convrot.safetensors'),('Comfy-Org/Fibo-2.0','text_encoders/qwen3vl_4b_int8_convrot.safetensors'),('drbaph/MiniMax-H3-Turbo-Lora-ComfyUI','experimental/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors')]:
 dest=root/('loras/kagemane/dmd_ref2va_8step.safetensors' if name.startswith('experimental') else name);dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.is_file():continue
 print('Downloading',repo,name,flush=True)
 # Dedicated download cache is on local disk. No credentials are printed.
 p=hf_hub_download(repo,name,cache_dir='/tmp/kagemane-model-downloads');shutil.copyfile(p,dest);print('Ready',dest,flush=True)
