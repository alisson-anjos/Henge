import io,json,struct,sys,unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sampling_preview import preview_jpeg
class PreviewProtocol(unittest.TestCase):
 def png(self):
  b=io.BytesIO();Image.new('RGB',(24,16),'red').save(b,format='PNG');return b.getvalue()
 def test_image_and_metadata_events_decode(self):
  meta=json.dumps({'prompt_id':'ours'}).encode()
  for packet in [struct.pack('>II',1,2)+self.png(),struct.pack('>II',4,len(meta))+meta+self.png()]:
   jpeg=preview_jpeg(packet,'ours');self.assertIsNotNone(jpeg)
   with Image.open(io.BytesIO(jpeg)) as im:self.assertEqual(im.format,'JPEG');self.assertEqual(im.size,(24,16))
 def test_rejects_other_jobs_invalid_headers_and_bad_images(self):
  meta=json.dumps({'prompt_id':'other'}).encode()
  for packet in [b'bad',struct.pack('>II',4,len(meta))+meta+self.png(),struct.pack('>II',1,9)+self.png(),struct.pack('>II',1,1)+b'invalid']:
   self.assertIsNone(preview_jpeg(packet,'ours'))
