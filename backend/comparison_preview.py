"""CPU-only, downloadable guide/result comparison with the original references."""
import json,math,subprocess,textwrap
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps

def settings_block(settings,prompt,width,small):
    """Small print of what produced the result: one settings line and the executed prompt (at most 14 lines)."""
    chars=max(40,int(width/6.4));lines=textwrap.wrap(settings,chars)+[''] if settings else []
    wrapped=textwrap.wrap(' '.join(prompt.split()),chars) if prompt else []
    if len(wrapped)>14:wrapped=wrapped[:14];wrapped[-1]=wrapped[-1][:chars-1]+'…'
    lines+=wrapped
    image=Image.new('RGB',(width,16*len(lines)+14),'#101018');draw=ImageDraw.Draw(image);y=6
    for i,line in enumerate(lines):
        draw.text((14,y),line,font=small,fill='#d6d0ea' if settings and i==0 else '#9a94b0');y+=16
    return image

def reference_header(references,width,settings='',prompt=''):
    """references: (slot, path) for a user picture, or (label, path, True) for an image generated from them (FIBO),
    drawn with an accent label and frame."""
    columns=min(6,max(1,len(references)));cell=width//columns;rows=math.ceil(len(references)/columns)
    height=36+rows*150+30;image=Image.new('RGB',(width,height),'#101018');draw=ImageDraw.Draw(image)
    try:font=ImageFont.truetype('DejaVuSans.ttf',15)
    except OSError:font=ImageFont.load_default()
    draw.text((14,10),'Reference pictures',font=font,fill='#bbb1db')
    for i,(slot,path,*generated) in enumerate(references):
        x=(i%columns)*cell;y=36+(i//columns)*150
        with Image.open(path) as ref:
            thumb=ImageOps.contain(ref.convert('RGB'),(max(1,cell-16),119))
        left,top=x+(cell-thumb.width)//2,y+23+(119-thumb.height)//2
        image.paste(thumb,(left,top))
        if generated and generated[0]:
            draw.rectangle((left-3,top-3,left+thumb.width+2,top+thumb.height+2),outline='#a78bfa',width=3)
            draw.text((x+10,y+3),str(slot),font=font,fill='#c4b5fd')
        else:draw.text((x+10,y+3),f'Picture {slot}',font=font,fill='white')
    draw.text((14,height-23),'Guide video',font=font,fill='#bbb1db')
    draw.text((width//2+14,height-23),'Generated result',font=font,fill='#bbb1db')
    if not (settings or prompt):return image
    try:small=ImageFont.truetype('DejaVuSans.ttf',11)
    except OSError:small=ImageFont.load_default()
    info=settings_block(settings,prompt,width,small)
    # Settings sit between the references and the guide/result labels.
    body=image.crop((0,0,width,height-30));labels=image.crop((0,height-30,width,height))
    out=Image.new('RGB',(width,body.height+info.height+30),'#101018')
    out.paste(body,(0,0));out.paste(info,(0,body.height));out.paste(labels,(0,body.height+info.height))
    return out

def create_comparison_with_refs(comparison,result,references,destination,settings='',prompt=''):
    comparison,result,destination=map(Path,(comparison,result,destination))
    if destination.is_file():return destination
    meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(comparison)]))
    video=next(s for s in meta['streams'] if s['codec_type']=='video')
    width=min(1600,int(video['width']));width-=width%4
    height=round(int(video['height'])*width/int(video['width'])/2)*2
    header=destination.with_suffix('.header.png');reference_header(references,width,settings,prompt).save(header)
    tmp=destination.with_name(destination.stem+'.tmp.mp4')
    args=['ffmpeg','-v','error','-i',str(comparison),'-loop','1','-framerate',video['r_frame_rate'],'-i',str(header),'-i',str(result),'-filter_complex',f'[0:v]scale={width}:{height},setsar=1[b];[1:v][b]vstack=inputs=2:shortest=1[v]','-map','[v]','-map','2:a?','-c:v','libx264','-threads','2','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-t',meta['format']['duration'],'-movflags','+faststart','-y',str(tmp)]
    run=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=300)
    if run.returncode:raise RuntimeError(run.stderr.decode(errors='replace')[-1200:])
    tmp.replace(destination);return destination
