"""Run a short two-stage H3 window test on RunPod Serverless, never on the local GPU.

Requires an already updated worker, the regenerate model profile on its volume, and FFmpeg.
Usage: python scripts/test_h3_windows_serverless.py --connection path/to/connection.json --source clip.mp4 --output /path/to/results
Connection credentials are read but never included in the report.
"""
import argparse,json,os,subprocess,sys,time,uuid
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']=''
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import workflows
from runpod_backend import RunPodBackend
from comfy_client import output_files
from edit_modes import LMS_CAPTION


def main():
 p=argparse.ArgumentParser();p.add_argument('--connection',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--phase',choices=['all','stage1','refine','result_refine','motion','tara'],default='all');p.add_argument('--reference',type=Path);p.add_argument('--start',type=float,default=0.);args=p.parse_args()
 out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);state=out/'state';state.mkdir(exist_ok=True);staging=out/'input';staging.mkdir(exist_ok=True)
 cfg=json.loads(args.connection.read_text());backend=RunPodBackend(staging,state,cfg['runpod_endpoint_id'],cfg['runpod_api_key'])
 inv=backend.call({'op':'inventory'},None,lambda:False)['inventory']
 if args.phase!='stage1' and 'HengeH3PureWindows' not in inv['nodes']:raise RuntimeError('Update the Serverless worker before running the test')
 info=backend.object_info();workflows.INSTALLED={n:set(info.get(n,{}).get('input',{}).get('required',{}).get(key,[[]])[0]) for n,key in workflows.LOADERS.items()}
 record=out/'report.json'
 if record.exists():report=json.loads(record.read_text())
 else:report={'test_id':'windows_'+uuid.uuid4().hex[:12],'seed':42,'frames':124,'fps':24,'first_pass':[1376,768],'output':[1952,1088],'window_frames':73,'overlap_frames':22,'first_pass_steps':4,'refiner_steps':2,'execution':'RunPod Serverless only','runs':[]}
 def persist():record.write_text(json.dumps(report,indent=2))
 inp=staging/'henge'/report['test_id'];inp.mkdir(parents=True,exist_ok=True)
 def run(cmd):subprocess.run(cmd,check=True)
 def ff(*argv):run(['ffmpeg','-v','error',*map(str,argv)])
 def relative(path):return path.relative_to(staging).as_posix()
 def execute(graph,name):
  graph=workflows.localize_loras(graph);(out/(name+'.api.json')).write_text(json.dumps(graph,indent=2));entry={'stage':name,'start':time.time()};report['runs'].append(entry);persist();last=None
  def progress(rid,data):
   nonlocal last
   if entry.get('request_id')!=rid:entry['request_id']=rid;persist()
   if data and data!=last:print(name,json.dumps(data),flush=True);last=data
  try:
   result=backend.run(graph,progress,lambda:False)
   files=output_files(result,'17','videos')
   if not files:raise RuntimeError('Missing expected output video')
   path=out/(name+'.mp4');backend.download(files[0],path);entry.update(status='completed',seconds=round(time.time()-entry['start'],2),file=path.name)
   status=backend.status(entry['request_id']);entry.update({k:status[k] for k in ('workerId','executionTime','delayTime') if k in status});persist();return path
  except Exception as error:entry.update(status='failed',error=str(error));persist();raise
 if args.phase in ('all','stage1'):
  full=inp/'source_full.mp4';ff('-i',args.source,'-vf','fps=24','-frames:v',124,'-an','-c:v','libx264','-threads',2,'-crf',17,'-y',full)
  pieces=[];previous=None
  for index,start in enumerate((0,51)):
   shot=inp/f'shot_{index:03d}.mp4';ff('-i',full,'-vf',f'trim=start_frame={start}:end_frame={start+73},setpts=PTS-STARTPTS','-an','-c:v','libx264','-threads',2,'-crf',17,'-y',shot)
   context=None
   if previous:
    context=inp/'context_001.mp4';ff('-sseof',-22/24,'-i',previous,'-an','-c:v','libx264','-threads',2,'-crf',17,'-y',context)
   graph=workflows.h3_graph(relative(shot),[],LMS_CAPTION,1376,768,73,73,'sharpness',42+index,4,'original',[],'human',start/24,turbo='dmad4',context_video=relative(context) if context else None,context_count=22,skip_frames=14 if index else 0)
   previous=execute(graph,f'lms_segment_{index:03d}');piece=out/f'piece_{index:03d}.mp4';piece.write_bytes(previous.read_bytes());pieces.append(piece)
  os.environ['HENGE_DATA_DIR']=str(state/'bridge');import server
  server.seam_join(pieces[0],pieces[1],8)
  concat=out/'concat.txt';concat.write_text(''.join(f"file '{x.name}'\n" for x in pieces));ff('-f','concat','-safe',1,'-i',concat,'-c','copy','-y',out/'lms_full.mp4')
 if args.phase in ('all','refine'):
  assembled=inp/'first_pass_full.mp4';assembled.write_bytes((out/'lms_full.mp4').read_bytes())
  guide=inp/'source_full.mp4'
  graph=workflows.full_refiner_graph(relative(assembled),relative(guide),'A person moving in the scene. Preserve the original subject, background, camera motion and timing. Natural sharp photographic details.',1376,768,1952,1088,124,124,42,temporal_windows={'enabled':True,'scope':'refiner_full','window_frames':73,'overlap_frames':22})
  result=execute(graph,'refiner_windows')
  ff('-i',guide,'-i',out/'lms_full.mp4','-i',result,'-filter_complex_threads',1,'-filter_complex','[0:v]scale=640:360,setsar=1,drawtext=text=Original:x=12:y=12:fontcolor=white:box=1:boxcolor=black@0.6[a];[1:v]scale=640:360,setsar=1,drawtext=text=LMS-segments:x=12:y=12:fontcolor=white:box=1:boxcolor=black@0.6[b];[2:v]scale=640:360,setsar=1,drawtext=text=Refiner-windows:x=12:y=12:fontcolor=white:box=1:boxcolor=black@0.6[c];[a][b][c]hstack=inputs=3:shortest=1[v]','-map','[v]','-an','-c:v','libx264','-threads',2,'-crf',18,'-y',out/'source_vs_lms_vs_refiner.mp4')
 if args.phase=='result_refine':
  guide=inp/'generated_result_source.mp4';ff('-ss',args.start,'-i',args.source,'-vf','fps=24','-frames:v',124,'-an','-c:v','libx264','-threads',2,'-crf',17,'-y',guide)
  metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(guide)]))['streams'][0];w,h=metadata['width'],metadata['height']
  report.update(input_kind='existing Character Swap result',start_seconds=args.start,first_pass=[w,h],passes='Existing generated result → windowed Open-H3 Refiner + LMS');persist()
  graph=workflows.full_refiner_graph(relative(guide),relative(guide),'A cinematic humanoid character in a ruined stone environment with fire. Preserve the generated character, clothing, body motion, camera movement, scene cuts, background and exact timing. Natural sharp details.',w,h,1952,1088,124,124,42,temporal_windows={'enabled':True,'scope':'refiner_full','window_frames':73,'overlap_frames':22})
  result=execute(graph,'character_result_refiner_windows')
  ff('-i',guide,'-i',result,'-filter_complex_threads',1,'-filter_complex','[0:v]scale=976:544,setsar=1,drawtext=text=Character-Swap-result:x=12:y=12:fontcolor=white:box=1:boxcolor=black@0.6[a];[1:v]scale=976:544,setsar=1,drawtext=text=Sharpness-Refiner-Windows:x=12:y=12:fontcolor=white:box=1:boxcolor=black@0.6[b];[a][b]hstack=inputs=2:shortest=1[v]','-map','[v]','-an','-c:v','libx264','-threads',2,'-crf',18,'-movflags','+faststart','-y',out/'character_result_vs_refiner_windows.mp4')
 if args.phase in ('motion','tara'):
  if not args.reference:raise ValueError('--reference is required for motion/TARA comparison')
  guide=inp/'motion_guide.mp4';ff('-i',args.source,'-vf','fps=24','-frames:v',56,'-an','-c:v','libx264','-threads',2,'-crf',17,'-y',guide)
  reference=inp/('reference'+args.reference.suffix);reference.write_bytes(args.reference.read_bytes())
  tara=args.phase=='tara';profile='motion_tara' if tara else 'motion'
  prompt=('motion_transfer: subject_definitions: <Subject 1> is the humanoid character shown in <Picture 1>, with short silver hair, white cat ears, red eyes, a gray vest and a white blouse. '
          'summary: [reference generation] The reference character follows the exact movements of the sole performer in Video 1. '
          'retention_analysis: <Subject 1>: fully_preserved - keep the reference identity, face, hair, ears and outfit throughout. '
          'detailed_description: [Shot 1] Match the guide body motion, gestures, camera framing and timing frame by frame. Keep the guide background and camera motion. Picture 1 supplies character appearance only; do not copy its black background or freeze its pose. '
          'overall_soundscape: N/A non_diegetic_music: N/A')
  results=[]
  for enabled in (False,True):
   name=profile+('_windows' if enabled else '_standard')
   graph=workflows.h3_graph(relative(guide),[relative(reference)],prompt,864,480,56,56,profile,42,8,'original',[],'human',0,conditioning_mode='tara' if tara else 'guide',turbo='dmd8',temporal_windows={'enabled':enabled,'window_frames':39,'overlap_frames':5})
   results.append(execute(graph,name))
  ff('-i',results[0],'-i',results[1],'-filter_complex_threads',1,'-filter_complex','[0:v][1:v]hstack=inputs=2:shortest=1[v]','-map','[v]','-an','-c:v','libx264','-threads',2,'-crf',18,'-y',out/(profile+'_standard_vs_windows.mp4'))
 persist();print('Results:',out,flush=True)

if __name__=='__main__':main()
