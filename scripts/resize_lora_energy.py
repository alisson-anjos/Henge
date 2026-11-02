"""Shrink a LoRA by per-module SVD, keeping a share of each module's Frobenius energy (dynamic rank).

For each module the update is W = scale * B @ A. With B = Qb Rb and A^T = Qa Ra (thin QR), W = Qb (Rb Ra^T) Qa^T, so the
SVD of the small r x r core gives W's singular values without forming W. Each module keeps the fewest singular values
whose squares reach `--energy` of the total, at most `--max-rank`. The scale is folded into B and no alpha is written,
so the result loads at strength 1 like the source.

  python scripts/resize_lora_energy.py in.safetensors out.safetensors --energy 0.99
"""
import argparse,json
import torch
from safetensors import safe_open
from safetensors.torch import save_file

def pairs(keys):
    for key in sorted(keys):
        for down,up in (('.lora_A.weight','.lora_B.weight'),('.lora_down.weight','.lora_up.weight')):
            if key.endswith(down):yield key[:-len(down)],down,up

def resize(down,up,scale,energy,max_rank):
    a,b=down.float(),up.float()*scale                 # A: r x in, B: out x r
    qb,rb=torch.linalg.qr(b);qa,ra=torch.linalg.qr(a.T)
    u,s,vh=torch.linalg.svd(rb@ra.T)
    share=torch.cumsum(s**2,0)/(s**2).sum().clamp_min(1e-20)
    k=int(min(max_rank,int((share<energy).sum())+1,s.numel()))
    root=s[:k].sqrt()
    return (vh[:k]@qa.T)*root[:,None],(qb@u[:,:k])*root[None,:],k

def main():
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output')
    p.add_argument('--energy',type=float,default=.99);p.add_argument('--max-rank',type=int,default=1<<30)
    p.add_argument('--dtype',default='bfloat16');p.add_argument('--name',default='')
    args=p.parse_args();dtype=getattr(torch,args.dtype);out={};ranks=[]
    with safe_open(args.source,'pt') as f:
        keys=list(f.keys());meta=f.metadata() or {}
        for module,dn,un in pairs(keys):
            down=f.get_tensor(module+dn);up=f.get_tensor(module+un)
            alpha=f.get_tensor(module+'.alpha').item() if module+'.alpha' in keys else None
            scale=1. if alpha is None else alpha/down.shape[0]
            if down.dim()!=2:raise SystemExit(f'{module}: only linear LoRA modules are supported')
            new_down,new_up,k=resize(down,up,scale,args.energy,args.max_rank);ranks.append(k)
            out[module+dn]=new_down.to(dtype).contiguous();out[module+un]=new_up.to(dtype).contiguous()
        known={m+s for m,dn,un in pairs(keys) for s in (dn,un,'.alpha')}
        for key in keys:
            if key not in known:out[key]=f.get_tensor(key)
    metadata={**{k:v for k,v in meta.items() if k in ('base_model','role','converted_from','solar_strength')},
              'method':f'per-module SVD, Frobenius energy {args.energy:g}','source':args.source.rsplit('/',1)[-1],
              'rank_min':str(min(ranks)),'rank_max':str(max(ranks)),'rank_mean':f'{sum(ranks)/len(ranks):.1f}'}
    if args.name:metadata['name']=args.name
    save_file(out,args.output,metadata=metadata)
    print(json.dumps({'modules':len(ranks),**{k:metadata[k] for k in ('rank_min','rank_max','rank_mean')}}))

if __name__=='__main__':main()
