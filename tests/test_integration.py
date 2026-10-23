"""Full local integration with real FFmpeg and deterministic provider doubles."""
import json,shutil,subprocess
from pathlib import Path
import pytest
from PIL import Image
from stickman.cli import main
from stickman.config import config_set
from test_product import doc
@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg required')
def test_full_bank_two_deliveries(monkeypatch,tmp_path):
 import stickman.voice.factory as vf
 import stickman.stills.factory as imf
 class Voice:
  def synthesize(self,text,out,**kw):
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=240:duration=3','-c:a','libmp3lame',str(out)],check=True)
   ws=text.split();Path(out).with_suffix('.words.json').write_text(json.dumps([{'w':w,'t':i*3/len(ws),'d':3/len(ws)} for i,w in enumerate(ws)]));return {'duration_s':3}
 class Images:
  name='local-double'
  def generate(self,prompt,out,**kw):
   Image.new('RGB',(640,360),'#F2E3C6' if 'rising' in prompt else '#FFFFFF').save(out);return {'width':640,'height':360}
 monkeypatch.setattr(vf,'make_voice_provider',lambda cfg:Voice());monkeypatch.setattr(imf,'make_image_provider',lambda cfg:Images())
 source=tmp_path/'source.json';source.write_text(json.dumps(doc()));p=tmp_path/'project'
 assert main(['init',str(p),'--from-script',str(source)])==0
 config_set(p,'render.width','640');config_set(p,'render.height','360')
 (p/'banco tema.txt').write_bytes(b'First topic\nSecond topic\n')
 assert main(['run','--project',str(p),'--batch','2','--live'])==0
 ds=list((p/'deliveries').iterdir());assert len(ds)==2
 assert {json.loads((d/'metadata.json').read_text())['topic'] for d in ds}=={'First topic','Second topic'}
 for d in ds:
  assert (d/'master.mp4').stat().st_size>1000 and (d/'thumbnail.png').exists()
  assert json.loads((d/'technical-check.json').read_text())['ok']
  assert json.loads((d/'metadata.json').read_text())['published'] is False
 r=json.loads((p/'.stickman/compose_report.json').read_text());assert r['title_timing']['title_dur']==0 and r['scenes']['s01']['start_s']==0
 assert not (p/'voice/title.mp3').exists()
