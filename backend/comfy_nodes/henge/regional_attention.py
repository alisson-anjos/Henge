"""Experimental H3 reference routing inspired by MAST's LAMA (arXiv:2604.12281).

This is NOT full MAST: no inversion, AdaIN, STS or DDI. Text, guide, audio and
target tokens form the retained context partition. No latent/noise mask is set.
The standalone math functions also run on CPU without importing ComfyUI.
"""
import math
import torch
import torch.nn.functional as F


def region_tokens(mask, frames, height, width):
    """Pixel masks -> H3 1+4 temporal / 32px spatial attention grid, soft coverage."""
    spatial=F.adaptive_avg_pool2d(mask.float()[:,None],(height,width))[:,0]
    result=[];start=0
    for i in range(frames):
        stop=min(start+(1 if i==0 else 4),len(spatial))
        result.append(spatial[start:stop].mean(0) if start<len(spatial) else spatial[-1])
        start=stop
    return torch.stack(result).flatten().clamp(0,1)


def allocate_logits(logits, spans, coverage, budget, strength):
    """LAMA-style per-query partition allocation, interpolated with original logits.

    logits [heads,queries,keys]; coverage [queries,references]. All non-reference
    keys remain an untouched context partition. Tiny finite masses allow soft
    routing without -inf hard attention boundaries. Strength zero is exact off.
    """
    if strength==0:return logits
    keep=torch.ones(logits.shape[-1],dtype=torch.bool,device=logits.device)
    for a,b in spans:keep[a:b]=False
    if not keep.any():raise ValueError('Regional attention requires context tokens')
    masses=coverage.float().clamp(0,1)
    masses=masses/masses.sum(-1,keepdim=True).clamp_min(1)
    masses=(masses*budget).clamp_min(1e-6)
    context_mass=(1-masses.sum(-1)).clamp_min(1e-6)
    context_z=torch.logsumexp(logits[...,keep],dim=-1)
    adjusted=logits.clone()
    for i,(a,b) in enumerate(spans):
        z=torch.logsumexp(logits[...,a:b],dim=-1)
        bias=(masses[:,i]/context_mass).log()[None]+context_z-z
        adjusted[...,a:b]+=strength*bias[...,None]
    return adjusted


def routed_attention(q,k,v,spans,coverage,budget=.35,strength=.5,chunk=32):
    """Head-wise query chunks bound FP32 score memory; never build full NxN scores."""
    output=torch.empty_like(q)
    for head in range(0,q.shape[0],4):
        keys=k[head:head+4].float().transpose(-1,-2);values=v[head:head+4].float()
        for start in range(0,q.shape[1],chunk):
            end=start+chunk
            logits=(q[head:head+4,start:end].float()@keys)/math.sqrt(q.shape[-1])
            logits=allocate_logits(logits,spans,coverage[start:end],budget,strength)
            output[head:head+4,start:end]=(logits.softmax(-1)@values).to(q.dtype)
    return output


class HengeRegionalAttention:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'model':('MODEL',),'regions':('HENGE_REGIONS',),
            'strength':('FLOAT',{'default':.5,'min':0.,'max':1.}),
            'reference_budget':('FLOAT',{'default':.35,'min':.01,'max':.95}),
            'layers':('STRING',{'default':'10,25,40'})}}
    RETURN_TYPES=('MODEL',);FUNCTION='patch';CATEGORY='Henge/experimental'

    def patch(self,model,regions,strength,reference_budget,layers):
        if strength==0:return (model,)
        dm=model.get_model_object('diffusion_model')
        if not hasattr(dm,'blocks') or not hasattr(dm,'video_patch_proj'):
            raise ValueError('Regional attention requires the packed MiniMax H3 model')
        indices=sorted({int(i.strip()) for i in layers.split(',') if i.strip()})
        if not indices or any(i<0 or i>=len(dm.blocks) for i in indices):
            raise ValueError('Regional attention layer is outside this H3 model')
        patched=model.clone()
        existing=patched.model_options.get('transformer_options',{}).get('patches_replace',{}).get('dit',{})
        for index in indices:
            if ('double_block',index) in existing:
                raise ValueError('Regional attention cannot overwrite another H3 block patch')
            attn=dm.blocks[index].attn
            def block(args,extra,attn=attn):
                layout=args['layout'];spans=[(a,b) for a,b,kind in layout.segments if kind=='ref_img']
                if not spans or any(int(slot)<1 or int(slot)>len(spans) for slot in regions):
                    raise ValueError('Regional attention reference slots do not match H3 layout')
                _,frames,lh,lw,_=layout.signature
                va,vb,_=next(s for s in layout.segments if s[2]=='video')
                if regions:
                    coverage=torch.stack([region_tokens(regions[i+1],frames,lh//2,lw//2) if i+1 in regions
                        else torch.zeros(vb-va) for i in range(len(spans))],-1)
                else:coverage=torch.zeros(vb-va,len(spans))
                if len(coverage)!=vb-va:raise ValueError('Regional attention token grid differs from H3 layout')
                def attention(x,rope_freqs=None,transformer_options=None):
                    import comfy.model_management as mm
                    import comfy.quant_ops
                    # Preserve the native attention for all non-target queries.
                    baseline=attn(x,rope_freqs=rope_freqs,transformer_options=transformer_options or {})
                    n,heads,dim=x.shape[0],attn.heads,attn.head_dim
                    q,k,v=attn.qkv_proj(x).split(heads*dim,dim=-1)
                    q=q.view(1,n,heads,dim);k=k.view(1,n,heads,dim)
                    if rope_freqs is not None:
                        comfy.quant_ops.ck.rms_rope_split_half_(q,k,rope_freqs,
                            mm.cast_to(attn.q_norm.weight,device=x.device),mm.cast_to(attn.k_norm.weight,device=x.device),
                            epsilon=attn.q_norm.eps,rot_dim=rope_freqs.shape[-3]*2)
                    else:
                        q=attn.q_norm(q);k=attn.k_norm(k)
                    out=routed_attention(q[0,va:vb].transpose(0,1),k[0].transpose(0,1),
                        v.view(n,heads,dim).transpose(0,1),spans,coverage.to(x.device),reference_budget,strength)
                    baseline[va:vb]=attn.out_proj(out.transpose(0,1).reshape(vb-va,heads*dim))
                    return baseline
                return extra['original_block']({**args,'attention':attention})
            patched.set_model_patch_replace(block,'dit','double_block',index)
        print(f'[Henge regional attention] LAMA-inspired; layers={indices}; strength={strength}; budget={reference_budget}',flush=True)
        return (patched,)
