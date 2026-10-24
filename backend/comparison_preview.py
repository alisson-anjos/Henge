"""CPU-only, downloadable guide/result comparison with the original references."""
import json,math,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps

def reference_header(references,width):
    columns=min(6,max(1,len(references)));cell=width//columns;rows=math.ceil(len(references)/columns)
    height=36+rows*150+30;image=Image.new('RGB',(width,height),'#101018');draw=ImageDraw.Draw(image)
    try:font=ImageFont.truetype('DejaVuSans.ttf',15)
    except OSError:font=ImageFont.load_default()
    draw.text((14,10),'Reference pictures',font=font,fill='#bbb1db')
    for i,(slot,path) in enumerate(references):
        x=(i%columns)*cell;y=36+(i//columns)*150
        with Image.open(path) as ref:
            thumb=ImageOps.contain(ref.convert('RGB'),(max(1,cell-16),119))
        image.paste(thumb,(x+(cell-thumb.width)//2,y+23+(119-thumb.height)//2))
        draw.text((x+10,y+3),f'Picture {slot}',font=font,fill='white')
    draw.text((14,height-23),'Guide video',font=font,fill='#bbb1db')
    draw.text((width//2+14,height-23),'Generated result',font=font,fill='#bbb1db')
    return image

def create_comparison_with_refs(comparison,result,references,destination):
    comparison,result,destination=map(Path,(comparison,result,destination))
    if destination.is_file():return destination
    meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(comparison)]))
    video=next(s for s in meta['streams'] if s['codec_type']=='video')
    width=min(1600,int(video['width']));width-=width%4
    height=round(int(video['height'])*width/int(video['width'])/2)*2
    header=destination.with_suffix('.header.png');reference_header(references,width).save(header)
    tmp=destination.with_name(destination.stem+'.tmp.mp4')
    args=['ffmpeg','-v','error','-i',str(comparison),'-loop','1','-framerate',video['r_frame_rate'],'-i',str(header),'-i',str(result),'-filter_complex',f'[0:v]scale={width}:{height},setsar=1[b];[1:v][b]vstack=inputs=2:shortest=1[v]','-map','[v]','-map','2:a?','-c:v','libx264','-threads','2','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-t',meta['format']['duration'],'-movflags','+faststart','-y',str(tmp)]
    run=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=300)
    if run.returncode:raise RuntimeError(run.stderr.decode(errors='replace')[-1200:])
    tmp.replace(destination);return destination
