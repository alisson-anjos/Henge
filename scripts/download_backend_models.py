from huggingface_hub import hf_hub_download
from pathlib import Path
import shutil
root=Path('/data/henge-comfy-backend/models')
# Legacy convenience script: supported Klein editor plus the existing turbo adapter.
for repo,name,target in [
 ('black-forest-labs/FLUX.2-klein-4b-fp8','flux-2-klein-4b-fp8.safetensors','diffusion_models/flux-2-klein-4b-fp8.safetensors'),
 ('Comfy-Org/Flux-2-Klein-4B','split_files/text_encoders/qwen_3_4b.safetensors','text_encoders/qwen_3_4b.safetensors'),
 # Shared FLUX VAE; the hosting repository does not select an inference editor.
 ('Comfy-Org/Fibo-2.0','vae/flux2-vae.safetensors','vae/flux2-vae.safetensors'),
 ('drbaph/MiniMax-H3-Turbo-Lora-ComfyUI','experimental/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors','loras/henge/dmd_ref2va_8step.safetensors')]:
 dest=root/target;dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.is_file():continue
 print('Downloading',repo,name,flush=True)
 # Dedicated download cache is on local disk. No credentials are printed.
 p=hf_hub_download(repo,name,cache_dir='/tmp/henge-model-downloads');shutil.copyfile(p,dest);print('Ready',dest,flush=True)
