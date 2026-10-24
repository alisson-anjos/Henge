"""Decode ComfyUI's per-client binary previews without accepting arbitrary files."""
import io,json,struct
from PIL import Image

def preview_jpeg(payload,prompt_id):
    if not isinstance(payload,(bytes,bytearray)) or not 8<=len(payload)<=16*1024*1024:return None
    kind,field=struct.unpack('>II',payload[:8])
    if kind==1:
        if field not in (1,2):return None
        image=payload[8:]
    elif kind==4:
        if field>65536 or 8+field>=len(payload):return None
        try:meta=json.loads(payload[8:8+field])
        except (ValueError,UnicodeDecodeError):return None
        if not isinstance(meta,dict) or meta.get('prompt_id',prompt_id)!=prompt_id:return None
        image=payload[8+field:]
    else:return None
    try:
        with Image.open(io.BytesIO(image)) as im:
            if im.width*im.height>16_000_000:return None
            im.thumbnail((768,768));rgb=im.convert('RGB');out=io.BytesIO();rgb.save(out,format='JPEG',quality=85);return out.getvalue()
    except (OSError,ValueError,Image.DecompressionBombError):return None
