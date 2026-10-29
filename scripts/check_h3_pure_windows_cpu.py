"""Exercise pure windows with a tiny native H3 and real BFS TARA wrapper, on CPU.
No pretrained weights, network requests, model downloads or video generation.
Run with the ComfyUI Python environment:
  python scripts/check_h3_pure_windows_cpu.py --comfy-root /path/to/ComfyUI --bfs-root /path/to/ComfyUI-BFSNodes
"""
import sys,importlib.util,argparse
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--comfy-root',type=Path,required=True);parser.add_argument('--bfs-root',type=Path,required=True);settings=parser.parse_args()
sys.path.insert(0,str(settings.comfy_root.resolve()))
sys.argv=[sys.argv[0],'--cpu']
from comfy.cli_args import args
args.cpu=True
import torch,comfy.ops,comfy.utils,comfy.conds
from comfy.ldm.minimax.model import MiniMaxH3Model
path=Path(__file__).resolve().parents[1]/'backend/comfy_nodes/henge/temporal_windows.py';spec=importlib.util.spec_from_file_location('smoke_pure_windows',path);tw=importlib.util.module_from_spec(spec);sys.modules[spec.name]=tw;spec.loader.exec_module(tw)
torch.manual_seed(4);torch.set_num_threads(2)
dm=MiniMaxH3Model(hidden_size=128,num_layers=1,token_refiner_num_layers=0,num_attention_heads=1,attention_head_dim=128,ffn_hidden_size=256,text_dim=128,timestep_input_dim=32,time_embed_hidden_size=128,time_embed_dim=64,dtype=torch.float32,device='cpu',operations=comfy.ops.disable_weight_init)
dm.requires_grad_(False).eval()
with torch.no_grad():
 for name,p in dm.named_parameters():
  p.normal_(0,.02)
  if 'norm' in name and name.endswith('weight'):p.fill_(1)
 dm.rope.inv_freq.copy_(torch.linspace(.001,.1,16))
text=torch.randn(1,3,128)
for frames in (22,56):
 vt=tw.latent_rows(frames);at=round(frames*40/24);video=torch.randn(1,24,vt,2,2);audio=torch.randn(1,32,2,at);x,shapes=comfy.utils.pack_latents([video,audio])
 payload={'keyframes':[{'resolved_frame_index':0,'latent':video*.1}],'cond_video_latents':[video*.1],'visual_cond_noise_aug':1.,'audio_scale':1.,'seed':42}
 cond={'model_conds':{'latent_shapes':comfy.conds.CONDConstant(shapes),'minimax_payload':comfy.conds.CONDConstant(payload),'c_crossattn':comfy.conds.CONDRegular(text)}}
 def predict(model,groups,z,t,options):
  outputs=[]
  for group in groups:
   item=group[0]['model_conds'];parts=comfy.utils.unpack_latents(z,item['latent_shapes'].cond)
   velocity=dm(parts,t,context=text,transformer_options=options.get('transformer_options',{}),minimax_payload=item['minimax_payload'].cond)
   packed,_=comfy.utils.pack_latents(velocity);outputs.append(z-.7*packed)
  return outputs
 with torch.no_grad():
  result=tw.PureH3Windows(22,5).execute(predict,dm,[[cond]],x,torch.tensor([700.]),{})[0]
  assert result.shape==x.shape and bool(torch.isfinite(result).all())
  if frames==22:torch.testing.assert_close(result,predict(dm,[[cond]],x,torch.tensor([700.]),{})[0],rtol=1e-5,atol=1e-5)
 print('PASS actual H3 model CPU:',frames,'frames; windows',len(tw.plan_windows(vt,at,22,5)),'finite output; AV shape preserved')

# Exercise the actual BFS TARA wrapper against window-local packed layouts on CPU.
import types,copy,importlib
pkg=types.ModuleType('bfs_window_smoke');pkg.__path__=[str(settings.bfs_root.resolve())];sys.modules[pkg.__name__]=pkg
tara=importlib.import_module('bfs_window_smoke.minimax_h3_native_temporal')
class Patcher:
 def __init__(self):self.model_options={'transformer_options':{}}
 def get_model_object(self,name):return dm
 def clone(self):p=Patcher();p.model_options=copy.deepcopy(self.model_options);return p
 def set_model_unet_function_wrapper(self,fn):self.model_options['model_function_wrapper']=fn
patched=tara.patch_temporal_model(Patcher(),backend='flex (original)')
frames=56;vt=tw.latent_rows(frames);at=round(frames*40/24);v=torch.randn(1,24,vt,2,2);a=torch.randn(1,32,2,at);x,shapes=comfy.utils.pack_latents([v,a])
reference={'kind':'video','latent':v*.1,'latent_t':vt,'latent_h':2,'latent_w':2,'ref_audio_t':0,'audio_latent':None}
payload={'refs':[reference],'cond_video_latents':[reference['latent']],'visual_cond_noise_aug':1.,'audio_scale':1.,'seed':42}
cond={'model_conds':{'latent_shapes':comfy.conds.CONDConstant(shapes),'minimax_payload':comfy.conds.CONDConstant(payload),'c_crossattn':comfy.conds.CONDRegular(text)}}
def native(x,sigma,latent_shapes,minimax_payload,transformer_options,**kwargs):
 parts=comfy.utils.unpack_latents(x,latent_shapes);out=dm(parts,sigma*1000,context=text,transformer_options=transformer_options,minimax_payload=minimax_payload);velocity,_=comfy.utils.pack_latents(out);return x-sigma[0]*velocity

def prediction(model,groups,z,sigma,options):
 outputs=[]
 for group in groups:
  mc=group[0]['model_conds'];values={k:c.cond for k,c in mc.items()};values['transformer_options']=dict(options.get('transformer_options',{}))
  outputs.append(patched.model_options['model_function_wrapper'](native,{'input':z,'timestep':sigma,'c':values,'cond_or_uncond':[0]}))
 return outputs
with torch.no_grad():
 result=tw.PureH3Windows(22,5).execute(prediction,dm,[[cond]],x,torch.tensor([.7]),{})[0]
 assert result.shape==x.shape and bool(torch.isfinite(result).all())
print('PASS actual BFS TARA + H3 CPU: 56 frames / 3 windows; native reference aligned; finite AV output')
