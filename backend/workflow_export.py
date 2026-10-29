"""Turn a job's API graph into a workflow a person can open and re-run in their own ComfyUI.

Henge builds graphs in code: HengeLoadShot takes file paths as text and HengeH3Conditioning wraps the native H3 nodes.
The export swaps them for loaders with upload buttons and for the native nodes they call, with the same inputs, so
the re-run matches the job:

- HengeLoadShot -> HengeLoadVideo (same FFmpeg decode; ComfyUI's Load Video converts colours slightly differently)
  plus one Load Image per picture (identical to Henge's picture loading);
- HengeH3Conditioning -> MiniMaxH3ReferenceToVideo (or BFS Guide 0 CLIP Context, the same code with the guide shown
  to the text encoder) -> MiniMaxH3AddGuide, Load Audio, Image Scale and Image From Batch, as the node did inside.

Files are renamed to flat names (`henge_<job>_<file>`), because ComfyUI's loaders list the top of the input folder.
"""
import copy,json,re
from pathlib import Path,PurePosixPath

NATIVE_MAX_REFS=9
# Local installs can keep older LoRA file names (localize_loras picks whichever is installed); the export uses the
# public names that the README links download.
PUBLIC_LORAS={old:new for new,old in json.loads(Path(__file__).with_name('legacy_loras.json').read_text()).items()}
JOB_FILE=re.compile(r'henge/[0-9a-f]{32}/')   # inputs staged for one job (model names can also start with henge/)


def _ref(value):
    return isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and type(value[1]) is int


def portable_graph(graph,prefix):
    """Return (graph, files, notes): the portable graph, {original input path: packaged name}, and what changed."""
    g=copy.deepcopy(graph);files={};notes=[]
    ids=[int(k) for k in g if k.isdigit()];counter=[max(ids,default=0)]

    def new(class_type,**inputs):
        counter[0]+=1;key=str(counter[0]);g[key]={'class_type':class_type,'inputs':inputs};return key

    def packaged(path):
        if path in files:return files[path]
        name=prefix+PurePosixPath(path).name
        index=len(files)
        while name in files.values():
            name=prefix+str(index)+'_'+PurePosixPath(path).name;index+=1
        files[path]=name;return name

    # Loaders: same node id keeps every [id, 0] frame link valid; the pictures become Load Image nodes.
    pictures={};lengths={}
    for key,n in list(g.items()):
        if n['class_type']!='HengeLoadShot':continue
        i=n['inputs'];lengths[key]=int(i['length'])
        pictures[key]=[new('LoadImage',image=packaged(p)) for p in json.loads(i.get('pictures') or '[]')]
        g[key]={'class_type':'HengeLoadVideo','inputs':{'video':packaged(i['video']),'width':i['width'],'height':i['height'],'length':i['length']}}

    replaced={}
    for key,n in list(g.items()):
        if n['class_type']!='HengeH3Conditioning':continue
        i=n['inputs'];refs=i.get('references')
        if not (_ref(refs) and refs[1]==1 and refs[0] in pictures):raise ValueError(f'Node {key}: references do not come from a Henge loader')
        images=[[p,0] for p in pictures[refs[0]]]
        mode=i.get('conditioning_mode','guide');length=int(i['length']);vae=i['vae']
        context=i.get('context_images');count=int(i.get('context_count') or 0)
        continuity=context is not None and count>=5
        if continuity:
            if not (_ref(context) and context[0] in lengths):raise ValueError(f'Node {key}: continuity frames do not come from a Henge loader')
            # HengeLoadShot returns exactly `length` frames (padded with the last one), so the node's count is known.
            count=min(count,lengths[context[0]],length);count-=max(0,(count-5)%17)
        audio=None
        if i.get('audio_conditioning'):audio=[new('LoadAudio',audio=packaged(i['audio_video'])),0]
        extra={'audio_vae':i['audio_vae']} if _ref(i.get('audio_vae')) else {}
        common={'clip':i['clip'],'vae':vae,'prompt':i['prompt'],'width':i['width'],'height':i['height'],'length':length,'ref_image_size':i['reference_size']}
        if mode=='tara':
            # TARA: the shot is native <Video 1>; within a take the previous shot's last frame is one more picture.
            if continuity:images.append([new('ImageFromBatch',image=context,batch_index=-1,length=1),0])
            video=i['guide'];scale=float(i.get('reference_scale',1.))
            if scale!=1.:
                width,height=int(i['width']),int(i['height'])
                video=[new('ImageScale',image=video,upscale_method='bilinear',width=max(32,int(width*scale)//32*32),height=max(32,int(height*scale)//32*32),crop='disabled'),0]
            inputs={**common,**extra,'ref_videos.ref_video_1':video}
            if audio:inputs['ref_video_audios.ref_video_audio_1']=audio
            node_type='MiniMaxH3ReferenceToVideo' if len(images)<=NATIVE_MAX_REFS else 'BFSMiniMaxH3ReferenceToVideoGuideContext'
        elif mode=='guide':
            inputs=dict(common)
            if i.get('guide_context'):inputs.update(guide_video_0=i['guide'],clip_video_fps=i['clip_video_fps'])
            node_type='BFSMiniMaxH3ReferenceToVideoGuideContext' if i.get('guide_context') or len(images)>NATIVE_MAX_REFS else 'MiniMaxH3ReferenceToVideo'
        else:raise ValueError(f'Node {key}: unknown conditioning mode {mode}')
        inputs.update({f'ref_images.ref_image_{j}':image for j,image in enumerate(images,1)})
        r2v=new(node_type,**inputs);cond=[r2v,0];latent=[r2v,1]
        if mode=='guide':
            guide={'image':i['guide'],**extra,**({'audio':audio} if audio else {})}
            cond=[new('MiniMaxH3AddGuide',positive=cond,latent=latent,frame_idx=0,vae=vae,**guide),0]
        if continuity:
            last=[new('ImageFromBatch',image=context,batch_index=-count,length=count),0]
            cond=[new('MiniMaxH3AddGuide',positive=cond,latent=latent,frame_idx=0,vae=vae,image=last),0]
        replaced[key]=(cond,latent);del g[key]

    for n in g.values():
        for name,value in n['inputs'].items():
            if _ref(value) and value[0] in replaced:n['inputs'][name]=replaced[value[0]][value[1]]
        if n['class_type']=='HengeSaveVideo':n['inputs']['filename']=prefix+PurePosixPath(n['inputs']['filename']).name
        if n['inputs'].get('lora_name') in PUBLIC_LORAS:n['inputs']['lora_name']=PUBLIC_LORAS[n['inputs']['lora_name']]
    # Anything still pointing into the job folder would fail on another machine.
    for key,n in g.items():
        for name,value in n['inputs'].items():
            if isinstance(value,str) and JOB_FILE.match(value):raise ValueError(f'Node {key} ({n["class_type"]}) still reads {name}={value}')
    if pictures:notes.append('Henge loaders replaced by Henge Load Video and Load Image')
    if replaced:notes.append('Henge H3 conditioning expanded into the native MiniMax H3 nodes')
    return g,files,notes


def runtime_node_files(root):
    """Package node runtime code/assets, excluding session notes, caches and external symlinks."""
    root=Path(root).resolve()
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts or not path.is_file():continue
        if not path.resolve().is_relative_to(root):continue
        if path.suffix in ('.py','.js','.json') or path.name=='requirements.txt':yield path


def visual_workflow(graph):
    """Build a ComfyUI workflow with explicit dynamic sockets and fixed seed controls.

    The frontend's API importer currently drops autogrow links. Public node layouts are captured
    from ComfyUI/BFS definitions and contain no model inventories or installation-specific paths.
    """
    layouts=json.loads((Path(__file__).resolve().parents[1]/'config/workflow-node-layouts.json').read_text())['nodes']
    unknown=sorted({n['class_type'] for n in graph.values()}-layouts.keys())
    if unknown:raise ValueError('No portable visual layout for: '+', '.join(unknown))
    ids={key:int(key) for key in graph if key.isdigit()}
    counter=max(ids.values(),default=0)
    for key in graph:
        if key not in ids:counter+=1;ids[key]=counter
    rendered={};rows={};depths={}
    def depth(key):
        if key not in depths:
            parents=[v[0] for v in graph[key]['inputs'].values() if _ref(v)]
            depths[key]=max((depth(p)+1 for p in parents),default=0)
        return depths[key]
    for key,node in graph.items():
        layout=layouts[node['class_type']];inputs=[];seen=set();values=node['inputs']
        for port in layout['inputs']:
            group=port['name'].split('.')[0];dynamic=layout.get('dynamic',{}).get(group)
            if dynamic:
                if group in seen:continue
                seen.add(group);names=[n for n in values if n.startswith(group+'.'+dynamic['prefix'])]
                if not names:names=[port['name']]
                elif len(names)<dynamic['max']:
                    last=max(int(n.rsplit('_',1)[1]) for n in names)
                    names.append(group+'.'+dynamic['prefix']+str(last+1))
                inputs.extend({**port,'name':name,'link':None} for name in names)
            else:inputs.append({**port,'link':None})
        widgets=[('fixed' if w['name'].endswith('control_after_generate') else values.get(w['name'],w.get('default'))) for w in layout['widgets']]
        level=depth(key);row=rows.get(level,0);height=max(220,70+26*(len(inputs)+len(widgets)))
        rendered[key]={'id':ids[key],'type':node['class_type'],'pos':[level*440,row],'size':[360,height],'flags':{},'order':len(rendered),'mode':0,
                       'inputs':inputs,'outputs':[{**p,'links':[]} for p in layout['outputs']],'properties':{'Node name for S&R':node['class_type']},'widgets_values':widgets}
        rows[level]=row+height+70
    links=[]
    for key,node in graph.items():
        for name,value in node['inputs'].items():
            if not _ref(value):continue
            source,slot=value
            target=rendered[key];source_node=rendered[source]
            index=next((i for i,p in enumerate(target['inputs']) if p['name']==name),None)
            if index is None:raise ValueError(f'No visual socket for {node["class_type"]}.{name}')
            link=len(links)+1;kind=source_node['outputs'][slot]['type']
            target['inputs'][index]['link']=link;source_node['outputs'][slot]['links'].append(link)
            links.append([link,ids[source],slot,ids[key],index,kind])
    return {'last_node_id':max(ids.values(),default=0),'last_link_id':len(links),'nodes':list(rendered.values()),'links':links,'groups':[],'config':{},'extra':{},'version':.4}
