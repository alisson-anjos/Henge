import importlib.util, unittest
from pathlib import Path
import torch
spec=importlib.util.spec_from_file_location('regional_attention',Path(__file__).resolve().parents[1]/'comfy_nodes/henge/regional_attention.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class RegionalAttentionTests(unittest.TestCase):
    def test_partition_mass_matches_target_despite_different_reference_sizes(self):
        torch.manual_seed(7)
        logits=torch.randn(2,4,13)*3
        coverage=torch.tensor([[1.,0.],[0.,1.],[.3,.7],[0.,0.]])
        probs=m.allocate_logits(logits,[(2,4),(5,10)],coverage,.4,1).softmax(-1)
        self.assertTrue(torch.allclose(probs[...,2:4].sum(-1),(.4*coverage[:,0]).expand(2,-1),atol=2e-6))
        self.assertTrue(torch.allclose(probs[...,5:10].sum(-1),(.4*coverage[:,1]).expand(2,-1),atol=2e-6))
        self.assertTrue(torch.isfinite(probs).all())

    def test_off_is_exact_and_chunking_does_not_change_result(self):
        torch.manual_seed(2)
        q=torch.randn(2,7,8);k=torch.randn(2,11,8);v=torch.randn_like(k);mask=torch.rand(7,1)
        original=torch.nn.functional.scaled_dot_product_attention(q,k,v)
        got=m.routed_attention(q,k,v,[(3,6)],mask,strength=0,chunk=2)
        self.assertTrue(torch.allclose(got,original,atol=1e-6))
        a=m.routed_attention(q,k,v,[(3,6)],mask,chunk=1)
        b=m.routed_attention(q,k,v,[(3,6)],mask,chunk=5)
        self.assertTrue(torch.allclose(a,b,atol=1e-6))

    def test_temporal_grid_uses_first_frame_then_groups_of_four_and_padding(self):
        mask=torch.zeros(6,8,8);mask[1:5]=1
        tokens=m.region_tokens(mask,4,2,2).view(4,2,2)
        self.assertTrue(torch.equal(tokens[0],torch.zeros(2,2)))
        self.assertTrue(torch.equal(tokens[1],torch.ones(2,2)))
        self.assertTrue(torch.equal(tokens[2:],torch.zeros(2,2,2)))

    def test_graph_is_opt_in_and_does_not_use_noise_mask(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from workflows import h3_graph
        args=('v.mp4',['a.png','b.png'],'p',512,288,39,24,'character',1,8,'2d',[],'human',0)
        off=h3_graph(*args);on=h3_graph(*args,regional_attention={'enabled':True})
        self.assertNotIn('60',off)
        self.assertEqual(on['60']['inputs']['regions'],['8',2])
        self.assertEqual(on['10']['inputs']['model'],['60',0])
        self.assertFalse(any(n['class_type']=='HengeLatentMask' for n in on.values()))

if __name__=='__main__':unittest.main()

class H3PatchTests(unittest.TestCase):
    def test_patch_routes_reference_and_preserves_other_queries(self):
        from types import SimpleNamespace, ModuleType
        from unittest.mock import patch
        import copy,sys
        class Attention(torch.nn.Module):
            def __init__(self):
                super().__init__();self.heads=2;self.head_dim=4
                self.qkv_proj=torch.nn.Linear(8,24,bias=False);self.out_proj=torch.nn.Linear(8,8,bias=False)
                self.q_norm=torch.nn.Identity();self.k_norm=torch.nn.Identity()
            def forward(self,x,rope_freqs=None,transformer_options=None):
                q,k,v=[t.view(len(x),2,4).transpose(0,1) for t in self.qkv_proj(x).chunk(3,-1)]
                out=F.scaled_dot_product_attention(q,k,v)
                return self.out_proj(out.transpose(0,1).reshape(len(x),8))
        from torch.nn import functional as F
        attn=Attention()
        dm=SimpleNamespace(video_patch_proj=True,blocks=[SimpleNamespace(attn=attn)])
        class Model:
            model_options={}
            def get_model_object(self,name):return dm
            def clone(self):return copy.copy(self)
            def set_model_patch_replace(self,fn,*args):self.callback=fn
        model=m.HengeRegionalAttention().patch(Model(),{1:torch.ones(1,8,8)},1.,.4,'0')[0]
        layout=SimpleNamespace(signature=(1,1,2,2,1),segments=[(0,1,'text'),(1,3,'ref_img'),(3,5,'audio'),(5,6,'video')])
        torch.manual_seed(6);x=torch.randn(6,8)
        def original(args):return {'img':args['attention'](args['img'])}
        comfy=ModuleType('comfy');comfy.__path__=[]
        quant=ModuleType('comfy.quant_ops');mm=ModuleType('comfy.model_management')
        comfy.quant_ops=quant;comfy.model_management=mm
        with patch.dict(sys.modules,{'comfy':comfy,'comfy.quant_ops':quant,'comfy.model_management':mm}):
            got=model.callback({'img':x,'layout':layout},{'original_block':original})['img']
        self.assertTrue(torch.equal(got[:5],attn(x)[:5]))
        self.assertFalse(torch.allclose(got[5:],attn(x)[5:]))
