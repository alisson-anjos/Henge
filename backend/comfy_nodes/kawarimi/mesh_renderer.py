"""CUDA z-buffer rendering with fixed identity colors and semantic face colors."""
import numpy as np
import torch
from comfy_extras.sam3d_body.rasterizer import _faces_to_device,_vertex_normals,_make_shade_fn,_rasterize_person
_CACHE={}
@torch.inference_mode()
def render(rgb,persons,faces,underlays,face_regions):
 device=torch.device('cuda');h,w=rgb.shape[:2]
 bg=rgb.copy()
 for mask,color in underlays or []:bg[mask]=color
 bg=torch.as_tensor(bg,device=device,dtype=torch.float32)/255
 if not persons:return (bg*255).byte().cpu().numpy()[...,::-1].copy()
 f=_faces_to_device(faces,device,_CACHE)
 z=torch.full((h*w,),float('inf'),device=device);colors=torch.zeros((h*w,3),device=device);mask=torch.zeros(h*w,dtype=torch.bool,device=device)
 for p in persons:
  verts=torch.as_tensor(np.asarray(p['pred_vertices'])+np.asarray(p['pred_cam_t']).reshape(1,3),device=device,dtype=torch.float32)
  normals=_vertex_normals(verts,f);view=verts*torch.tensor([1,-1,-1],device=device);normals=normals*torch.tensor([1,-1,-1],device=device)
  vc=np.tile(np.asarray(p['_rgb'],dtype=np.float32)/255,(len(verts),1))
  if face_regions is not None:
   selected=face_regions.sum(axis=1)>0;vc[selected]=face_regions[selected]
  vc=torch.as_tensor(vc,device=device)
  shade=_make_shade_fn('rainbow_face_semantic','over',normals,view,vc,f,(1,1,1),(.4,-.7,-.6),0)
  _rasterize_person(verts,f,float(np.asarray(p['focal_length']).reshape(-1)[0]),w,h,z,colors,mask,shade)
 out=torch.where(mask.reshape(h,w,1),colors.reshape(h,w,3).clamp(0,1),bg)
 return (out*255).byte().cpu().numpy()[...,::-1].copy()
