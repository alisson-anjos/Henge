import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import workflow_export,workflows

JOB='henge/'+'a'*32+'/'

def shot(mode,context=False,refs=2,guide_context=True,scale=1.,audio=False):
    pictures=[JOB+f'reference_{i}_prepared.png' for i in range(1,refs+1)]
    g={'5':{'class_type':'CLIPLoader','inputs':{'clip_name':'clip.safetensors'}},'6':{'class_type':'VAELoader','inputs':{'vae_name':'vae.safetensors'}},
       '7':{'class_type':'HengeLoadShot','inputs':{'video':JOB+'shot_002.mp4','pictures':json.dumps(pictures),'width':864,'height':480,'length':107}},
       '9':{'class_type':'HengeH3Conditioning','inputs':{'clip':['5',0],'vae':['6',0],'guide':['7',0],'references':['7',1],'prompt':'scene','width':864,'height':480,'length':107,
            'clip_video_fps':2,'reference_size':'match','guide_context':guide_context,'audio_conditioning':audio,'audio_video':JOB+'shot_002.mp4','conditioning_mode':mode,'reference_scale':scale}},
       '11':{'class_type':'SamplerCustomAdvanced','inputs':{'guider':['9',0],'latent_image':['9',1]}},
       '17':{'class_type':'HengeSaveVideo','inputs':{'images':['7',0],'filename':JOB+'shot_002_result.mp4','trim_frames':107,'fps':24}}}
    if context:
        g['20']={'class_type':'HengeLoadShot','inputs':{'video':JOB+'context_002.mp4','pictures':'[]','width':864,'height':480,'length':22}}
        g['9']['inputs'].update(context_images=['20',0],context_count=22)
    return g

def nodes(g,t):return [k for k,n in g.items() if n['class_type']==t]

def test_loaders_become_load_video_and_load_image_with_flat_names():
    g,files,_=workflow_export.portable_graph(shot('guide'),'henge_aaaaaaaa_')
    assert g['7']=={'class_type':'HengeLoadVideo','inputs':{'video':'henge_aaaaaaaa_shot_002.mp4','width':864,'height':480,'length':107}}
    assert sorted(g[k]['inputs']['image'] for k in nodes(g,'LoadImage'))==['henge_aaaaaaaa_reference_1_prepared.png','henge_aaaaaaaa_reference_2_prepared.png']
    assert files[JOB+'shot_002.mp4']=='henge_aaaaaaaa_shot_002.mp4'
    assert g['17']['inputs']['filename']=='henge_aaaaaaaa_shot_002_result.mp4'
    assert not nodes(g,'HengeLoadShot') and not nodes(g,'HengeH3Conditioning')

def test_guide_mode_is_reference_to_video_then_add_guide_and_continuity():
    g,_,_=workflow_export.portable_graph(shot('guide',context=True),'p_')
    (r2v,)=nodes(g,'BFSMiniMaxH3ReferenceToVideoGuideContext');i=g[r2v]['inputs']
    assert i['guide_video_0']==['7',0] and i['clip_video_fps']==2 and i['ref_image_size']=='match'
    assert [g[i[f'ref_images.ref_image_{j}'][0]]['class_type'] for j in (1,2)]==['LoadImage','LoadImage']
    guide,cont=sorted(nodes(g,'MiniMaxH3AddGuide'),key=int)
    assert g[guide]['inputs']['image']==['7',0] and g[guide]['inputs']['positive']==[r2v,0]
    frames=g[g[cont]['inputs']['image'][0]]['inputs']
    assert frames=={'image':['20',0],'batch_index':-22,'length':22}   # 22 frames is on the 17n+5 grid
    # The sampler now reads the last guide's conditioning and the reference latent.
    assert g['11']['inputs']=={'guider':[cont,0],'latent_image':[r2v,1]}

def test_guide_mode_without_clip_context_is_fully_native():
    g,_,_=workflow_export.portable_graph(shot('guide',guide_context=False),'p_')
    assert nodes(g,'MiniMaxH3ReferenceToVideo') and not nodes(g,'BFSMiniMaxH3ReferenceToVideoGuideContext')

def test_tara_uses_the_shot_as_native_video_and_the_last_frame_as_a_picture():
    g,_,_=workflow_export.portable_graph(shot('tara',context=True,scale=.5,audio=True),'p_')
    (r2v,)=nodes(g,'MiniMaxH3ReferenceToVideo');i=g[r2v]['inputs']
    scale=g[i['ref_videos.ref_video_1'][0]]
    assert scale['class_type']=='ImageScale' and (scale['inputs']['width'],scale['inputs']['height'])==(416,224)
    last=g[i['ref_images.ref_image_3'][0]]['inputs'];assert last=={'image':['20',0],'batch_index':-1,'length':1}
    assert g[i['ref_video_audios.ref_video_audio_1'][0]]['class_type']=='LoadAudio'
    (cont,)=nodes(g,'MiniMaxH3AddGuide');assert g['11']['inputs']['guider']==[cont,0]

def test_more_pictures_than_the_native_node_takes_use_the_bfs_node():
    g,_,_=workflow_export.portable_graph(shot('guide',refs=11,guide_context=False),'p_')
    (r2v,)=nodes(g,'BFSMiniMaxH3ReferenceToVideoGuideContext');assert 'ref_images.ref_image_11' in g[r2v]['inputs']

def test_every_built_graph_exports_with_valid_links():
    g=workflows.h3_graph(JOB+'shot_000.mp4',[JOB+'reference_1_prepared.png'],'scene',864,480,107,107,'character',42,8,'2d',[],'human',0)
    out,files,_=workflow_export.portable_graph(g,'p_')
    for n in out.values():
        for v in n['inputs'].values():
            if isinstance(v,list) and len(v)==2 and isinstance(v[0],str):assert v[0] in out
    assert all(not workflow_export.JOB_FILE.match(v) for n in out.values() for v in n['inputs'].values() if isinstance(v,str))

def test_old_local_lora_names_become_the_public_ones():
    g=shot('guide');g['2']={'class_type':'LoraLoaderModelOnly','inputs':{'lora_name':'henge/training_adapter_v2.safetensors'}}
    out,_,_=workflow_export.portable_graph(g,'p_')
    assert out['2']['inputs']['lora_name']=='henge/minimax_h3_ref2va_training_adapter_v2.safetensors'


def test_flat_input_names_do_not_overwrite_distinct_sources():
    g=shot('guide')
    g['7']['inputs']['pictures']=json.dumps([JOB+'one/picture.png',JOB+'two/picture.png'])
    out,files,_=workflow_export.portable_graph(g,'p_')
    assert len(set(files.values()))==len(files)
    assert len({out[k]['inputs']['image'] for k in nodes(out,'LoadImage')})==2


def test_node_package_excludes_notes_caches_and_external_symlinks(tmp_path):
    root=tmp_path/'nodes';root.mkdir();(root/'__init__.py').write_text('# node code')
    (root/'requirements.txt').write_text('example')
    (root/'private-session.txt').write_text('private session')
    (root/'notes.md').write_text('private notes')
    (root/'__pycache__').mkdir();(root/'__pycache__'/'cache.py').write_text('cache')
    outside=tmp_path/'outside.py';outside.write_text('private code');(root/'external.py').symlink_to(outside)
    assert {p.name for p in workflow_export.runtime_node_files(root)}=={'__init__.py','requirements.txt'}


def test_export_full_refiner_preserves_native_sampling_and_packages_both_videos():
    g=workflows.full_refiner_graph(JOB+'first_pass.mp4',JOB+'source.mp4','scene',864,480,1952,1088,107,107,42)
    out,files,_=workflow_export.portable_graph(g,'p_')
    assert len(files)==2
    assert not nodes(out,'HengeLoadShot') and not nodes(out,'HengeH3Conditioning')
    assert out['37']==g['37']
    assert nodes(out,'HengeH3PureWindows')


def test_package_rejects_inputs_outside_staging(tmp_path,monkeypatch):
    import server,pytest
    work=tmp_path/'work';work.mkdir();(work/'h3_segment_000.api.json').write_text('{}')
    inp=tmp_path/'input';inp.mkdir()
    monkeypatch.setattr(server,'load',lambda jid:{'id':jid})
    monkeypatch.setattr(server,'job_path',lambda jid:work)
    monkeypatch.setattr(server,'INPUT',inp)
    monkeypatch.setattr(workflow_export,'portable_graph',lambda *args:({}, {'../private.mp4':'clip.mp4'}, []))
    with pytest.raises(server.HTTPException) as error:server.workflow_pack('a'*32)
    assert error.value.status_code==409 and 'outside' in error.value.detail


def test_readme_links_public_model_names_and_explains_dependencies():
    import server
    g=shot('guide');g['2']={'class_type':'LoraLoaderModelOnly','inputs':{'lora_name':'henge/training_adapter_v2.safetensors'}}
    out,_,notes=workflow_export.portable_graph(g,'p_')
    readme=server.workflow_readme({'id':'a'*32},'h3_segment_000',out,notes)
    assert 'minimax_h3_ref2va_training_adapter_v2.safetensors' in readme
    assert '[download](https://huggingface.co/' in readme
    assert 'Model weights are not included' in readme


def test_visual_workflow_keeps_autogrow_links_and_a_fixed_seed():
    g=workflows.h3_graph(JOB+'shot.mp4',[JOB+'ref.png'],'scene',864,480,107,107,'motion_tara',42,8,'original',[],'human',0,conditioning_mode='tara',context_video=JOB+'context.mp4',context_count=22)
    api,_,_=workflow_export.portable_graph(g,'p_');ui=workflow_export.visual_workflow(api)
    by_id={str(n['id']):n for n in ui['nodes']}
    reference=next((key,node) for key,node in api.items() if node['class_type']=='MiniMaxH3ReferenceToVideo')
    fields=reference[1]['inputs'];ports={p['name']:p for p in by_id[reference[0]]['inputs']}
    assert ports['ref_images.ref_image_1']['link'] is not None
    assert ports['ref_images.ref_image_2']['link'] is not None  # continuity still
    assert ports['ref_videos.ref_video_1']['link'] is not None
    assert by_id['11']['widgets_values']==[42,'fixed']
    assert len(ui['links'])==sum(workflow_export._ref(v) for n in api.values() for v in n['inputs'].values())


def test_visual_layout_covers_current_h3_variants():
    base=(JOB+'shot.mp4',[],'scene',864,480,107,107,'sharpness',42,4,'original',[],'human',0)
    for method in ('h3','regenerate','nvidia'):
        graph=workflows.h3_graph(*base,upscale={'method':method,'model':'upscale.safetensors','steps':2},temporal_windows={'enabled':True})
        api,_,_=workflow_export.portable_graph(graph,'p_');ui=workflow_export.visual_workflow(api)
        assert len(ui['nodes'])==len(api)


def test_unsupported_visual_nodes_fail_instead_of_dropping_connections():
    import pytest
    with pytest.raises(ValueError,match='No portable visual layout'):workflow_export.visual_workflow({'1':{'class_type':'UnavailableCustomNode','inputs':{}}})
