"""Merge LoRAs exactly by rank concatenation (no SVD, no approximation).

For each module, A=[A1;A2] and B=[B1*s1, B2*s2] with alpha=rank, so B@A equals
s1*B1@A1 + s2*B2@A2. Sources without an alpha already use scale 1 (alpha=rank).

  python scripts/merge_lora_concat.py out.safetensors motion.safetensors adapter.safetensors \
      --name tara4500_plus_training_adapter_v2_exact
"""
import argparse,json
import torch
from safetensors.torch import load_file,save_file

def module_scale(tensors,module,rank):
    alpha=tensors.get(module+'.alpha')
    return 1. if alpha is None else float(alpha)/rank

def merge(sources,strengths):
    loaded=[load_file(path) for path in sources]
    modules=sorted({key[:-len('.lora_A.weight')] for tensors in loaded for key in tensors if key.endswith('.lora_A.weight')})
    out={}
    for module in modules:
        downs,ups=[],[]
        for tensors,strength in zip(loaded,strengths):
            if module+'.lora_A.weight' not in tensors:continue
            down=tensors[module+'.lora_A.weight'];up=tensors[module+'.lora_B.weight']
            scale=strength*module_scale(tensors,module,down.shape[0])
            downs.append(down);ups.append(up if scale==1. else (up.float()*scale).to(up.dtype))
        down=torch.cat(downs,0);up=torch.cat(ups,1)
        out[module+'.lora_A.weight']=down.contiguous();out[module+'.lora_B.weight']=up.contiguous()
        out[module+'.alpha']=torch.tensor(float(down.shape[0]),dtype=torch.float32)
    return out

def main():
    parser=argparse.ArgumentParser();parser.add_argument('output');parser.add_argument('sources',nargs='+')
    parser.add_argument('--strengths',type=float,nargs='*');parser.add_argument('--name',required=True);parser.add_argument('--warning',default='')
    args=parser.parse_args();strengths=args.strengths or [1.]*len(args.sources)
    if len(strengths)!=len(args.sources):raise SystemExit('One strength per source')
    tensors=merge(args.sources,strengths)
    names=[path.rsplit('/',1)[-1].rsplit('.',1)[0] for path in args.sources]
    metadata={'name':args.name,'inference_strength':'1.0','merge_formula':' + '.join(f'{s:g} {n}' for s,n in zip(strengths,names)),
              'rank_scaling':'exact concatenation; alpha=rank; source alpha absent defaults to rank','sources':json.dumps(names)}
    if args.warning:metadata['warning']=args.warning
    save_file(tensors,args.output,metadata=metadata);print('Saved',args.output,len(tensors),'tensors')
if __name__=='__main__':main()
