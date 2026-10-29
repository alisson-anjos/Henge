"""Validate public Motion Transfer links, conditioning contracts and optional browser API exports.
python scripts/workflows/check_motion_transfer.py [--api-dir /tmp]
No inference is queued.
"""
import argparse,json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--api-dir',type=Path);args=p.parse_args()
files=sorted((root/'workflows').glob('minimax_h3_motion_transfer*workflow_*_v1.0.json'))
assert len(files)==4
for path in files:
 d=json.loads(path.read_text());nodes={n['id']:n for n in d['nodes']};links={l[0]:l for l in d['links']};meta=d['extra']['henge_motion_workflow'];tara=meta['method']=='tara';planner=meta['planner']
 assert len(nodes)==len(d['nodes']) and len(links)==len(d['links'])
 for lid,a,sa,b,sb,typ in d['links']:
  assert a in nodes and b in nodes
  assert nodes[a]['outputs'][sa]['type']==typ
  assert nodes[b]['inputs'][sb]['link']==lid
  assert lid in nodes[a]['outputs'][sa]['links']
 for n in nodes.values():
  for i,port in enumerate(n.get('inputs',[])):
   if port.get('link') is not None:assert links[port['link']][3:5]==[n['id'],i]
  for i,port in enumerate(n.get('outputs',[])):
   for lid in port.get('links') or []:assert links[lid][1:3]==[n['id'],i]
  assert not n['type'].startswith('Henge'),n['type']
 def one(kind):return next(n for n in nodes.values() if n['type']==kind)
 def src(n,name):return tuple(links[next(p['link'] for p in n['inputs'] if p['name']==name)][1:3])
 loaders=[n for n in nodes.values() if n['type']=='LoraLoaderModelOnly']
 assert [n['widgets_values_named']['lora_name'] for n in loaders]==['minimax_h3_ref2va_training_adapter_v2.safetensors','minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors',f'minimax_h3_motion_transfer_{"tara_" if tara else ""}v1.0_ref2va.safetensors']
 assert one('BasicScheduler')['widgets_values_named']['steps']==8
 assert one('CFGGuider')['widgets_values_named']['cfg']==1
 assert src(one('CFGGuider'),'model')==src(one('BasicScheduler'),'model')
 if planner:
  cond=one('BFSShotH3ConditioningSimple');assert src(one('CFGGuider'),'model')==(cond['id'],3)
  assert cond['widgets_values_named']['guide_mode']==('TARA - Native Temporal Alignment (experimental)' if tara else 'aligned guide + CLIP video context')
  plan=json.loads(one('BFSShotPlanner')['widgets_values'][0]);assert plan['auto_prompt']['enabled'] and plan['auto_prompt']['trigger']=='motion_transfer'
  assert not plan['auto_prompts'] and not plan['picture_details'] and not plan['segs']
  assert one('BFSShotJoin')['widgets_values_named']['crossfade']==0
  assert one('BFSShotJoin')['widgets_values_named']['save_to']=='mp4 file (long videos, low memory)'
  assert not any(n['type']=='SaveVideo' for n in nodes.values())
 else:
  native=one('MiniMaxH3ReferenceToVideo');assert native['widgets_values_named']['prompt'].startswith('motion_transfer:')
  attached=[x for x in native['inputs'] if x['name'].startswith('ref_images.') and x.get('link')]
  assert len(attached)==1 and attached[0]['name']=='ref_images.ref_image_1'
  assert any(x['name']=='ref_images.ref_image_2' and x['link'] is None for x in native['inputs'])
  assert src(one('ImageFromBatch'),'length')==(one('BFSH3PrepareNativeVideo')['id'],8)
  has_video=any(x['name']=='ref_videos.ref_video_1' and x.get('link') for x in native['inputs'])
  assert has_video==tara
  assert sum(n['type']=='MiniMaxH3AddGuide' for n in nodes.values())==(0 if tara else 1)
  if tara:assert src(one('CFGGuider'),'model')==(one('BFSMiniMaxH3NativeTemporal')['id'],0)
  else:assert src(one('CFGGuider'),'positive')==(one('MiniMaxH3AddGuide')['id'],0)
 if args.api_dir:
  api=json.loads((args.api_dir/path.name.replace('.json','.api.json')).read_text())
  for n in nodes.values():
   if n['type']=='MarkdownNote':continue
   real=api[str(n['id'])];assert real['class_type']==n['type']
   saved_widgets=n.get('widgets_values_named',{})
   if n['type']=='VHS_LoadVideoFFmpeg':saved_widgets=n['widgets_values']
   for name,value in saved_widgets.items():
    port=next((p for p in n['inputs'] if p['name']==name),{})
    if port.get('link') is None:assert real['inputs'].get(name)==value,(path.name,n['type'],name,real['inputs'].get(name),value)
   for port in n['inputs']:
    if port.get('link'):
     l=links[port['link']];assert real['inputs'][port['name']]==[str(l[1]),l[2]]
 print('PASS',path.name,'— links, matching LoRA, reference roles, conditioning and model routing'+('; browser-exported API matches saved widgets/sockets' if args.api_dir else ''))
