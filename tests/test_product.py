import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
from stickman.config import default_config
from stickman.cli import main
from stickman.scriptx.schema import validate_docu_en_1
from stickman.scriptx.prompts import build_bundle
from stickman.timeline import concept_timeline
from stickman.stills.runner import run_stills
from stickman.errors import ProviderError,LiveGateError

def doc():
 return {'title':'Paper flight','language':'en','target_minutes':.2,'scenes':[{'id':'s01','voiceover':'The plane rises then it falls.','visual':'stickman throws plane','anchor':'plane','action':'throws','concepts':[{'id':'c01','anchor':'wing','narration_span':'The plane rises','subject':'stickman','visible_action':'throws','object':'plane','spatial_relation':'left','composition':'wide','semantic_visual':'plane rising','overlay_hint':'GO UP'},{'id':'c02','anchor':'ground','narration_span':'then it falls.','subject':'stickman','visible_action':'catches','object':'plane','spatial_relation':'right','composition':'close','semantic_visual':'plane falling','overlay_hint':'GO DOWN'}]}]}

def test_defaults_init_preserves_existing(tmp_path):
 c=default_config();assert c['images']['provider']==c['script']['provider']=='codex-oauth';assert c['voice']['provider']=='edge'
 p=tmp_path/'spaces folder';assert main(['init',str(p),'--topic','Paper flight'])==0
 before=(p/'stickman.toml').read_bytes();assert main(['init',str(p)])==1
 assert (p/'stickman.toml').read_bytes()==before
 assert (p/'banco tema.txt').read_text().strip()=='Paper flight'

def test_import_copied(tmp_path):
 f=tmp_path/'input.json';f.write_text(json.dumps(doc()));p=tmp_path/'project'
 assert main(['init',str(p),'--from-script',str(f)])==0
 f.unlink();assert main(['run','--project',str(p),'--stage','script'])==0
 assert json.loads((p/'script.json').read_text())['title']=='Paper flight'

def test_schema_paths_and_malformed():
 d=doc();d['scenes'][0]['concepts'][0]['id']='../../escape';assert validate_docu_en_1(d)
 assert validate_docu_en_1({'scenes':[None]})
 d=doc();d['scenes'][0]['concepts'][0]['narration_span']='missing';assert validate_docu_en_1(d)

def test_concept_prompts(tmp_path):
 build_bundle(doc(),tmp_path);p=json.loads((tmp_path/'prompts.json').read_text())
 assert p['c01']['prompt']!=p['c02']['prompt']
 assert 'plane rising' in p['c01']['prompt'] and 'plane falling' in p['c02']['prompt']
 prompt=p['c01']['prompt'].lower()
 assert 'warm off-white' in prompt and 'soft cast shadow' in prompt
 assert 'pure white background' not in prompt and 'no cast shadows' not in prompt

def test_measured_concepts_not_equal_slices(tmp_path):
 (tmp_path/'.stickman').mkdir();words=[{'w':w,'t':t,'d':.3} for w,t in zip('The plane rises then it falls'.split(),[0,.2,.4,1,3,5])]
 (tmp_path/'.stickman/words.json').write_text(json.dumps({'scenes':{'s01':{'words':words}}}))
 t=concept_timeline(doc(),tmp_path,{'s01':6});assert t['s01'][0]['end']==1 and t['s01'][1]['end']==6

def test_persistent_image_budget(tmp_path):
 class Broken:
  name='broken'
  def generate(self,*a,**k):raise ProviderError('failure')
 bundle={'c':{'filename':'c.png','prompt':'plane'}}
 for _ in range(2):
  with pytest.raises(ProviderError):run_stills(bundle,Broken(),tmp_path,live=True,reserve=1)
 with pytest.raises(ProviderError,match='HARD_LIMIT'):run_stills(bundle,Broken(),tmp_path,live=True,reserve=1)
 assert json.loads((tmp_path/'manifest.json').read_text())['attempts']==2

def test_codex_stills_batch_one_exec_for_many_concepts(monkeypatch, tmp_path):
    """32 conceptos no deben ser 32 llamadas Codex. Una tanda = un exec."""
    import stickman.stills.codex_oauth as co
    calls = []
    timeouts = []
    def fake(prompt, d, **kw):
        calls.append(prompt)
        timeouts.append(kw.get('timeout'))
        assert kw['image']
        root = Path(d)
        for i in range(1, 33):
            Image.new('RGB', (320, 180), 'white').save(root / f'c{i:02d}.png')
    monkeypatch.setattr(co, 'execute', fake)
    bundle = {f'c{i:02d}': {'filename': f'c{i:02d}.png', 'prompt': f'brief {i}', 'anchor': f'a{i}'} for i in range(1, 33)}
    rep = run_stills(bundle, co.CodexOAuthImages(), tmp_path, live=True, reserve=0)
    assert rep['done'] == 32
    assert len(calls) == 1
    assert timeouts[0] >= 32 * 60
    request = calls[0].lower()
    assert 'warm off-white or muted colored background' in request
    assert 'fully opaque pure white background' not in request
    assert (tmp_path / 'c32.png').exists()

def test_image_resume_hash(tmp_path):
 class Fake:
  name='fake';calls=0
  def generate(self,prompt,out,**kw):
   self.calls+=1;Image.new('RGB',(320,180),'white').save(out);return {'width':320,'height':180}
 p=Fake();b={'c':{'filename':'c.png','prompt':'plane'}}
 for _ in range(2):run_stills(b,p,tmp_path,live=True)
 assert p.calls==1
 (tmp_path/'c.png').write_bytes(b'corrupt');run_stills(b,p,tmp_path,live=True);assert p.calls==2

def test_no_live_no_calls(monkeypatch,tmp_path):
 import stickman.scriptx.codex_oauth as co
 monkeypatch.setattr(co,'execute',lambda *a,**k:pytest.fail('unexpected call'))
 with pytest.raises(LiveGateError):co.CodexOAuthScript().draft('topic',tmp_path/'x',live=False)
 from stickman.voice.edge import EdgeVoice
 with pytest.raises(LiveGateError):EdgeVoice().synthesize('text',tmp_path/'x',voice='v',speed=1,live=False)

def test_codex_script_contract(monkeypatch,tmp_path):
 import stickman.scriptx.codex_oauth as co
 captured=[]
 def fake(prompt,*a,**k):
  captured.append(prompt)
  return json.dumps(doc())
 monkeypatch.setattr(co,'execute',fake)
 p=tmp_path/'script.json';co.CodexOAuthScript(target_minutes=.17).draft('plane',p,live=True);assert not validate_docu_en_1(json.loads(p.read_text()))
 assert 'muted colored backgrounds' in captured[0].lower()
 assert 'white background and selective yellow' not in captured[0].lower()

def test_codex_image_contract(monkeypatch,tmp_path):
 import stickman.stills.codex_oauth as co
 def fake(prompt,d,**kw):
  assert kw['image'];Image.new('RGB',(320,180),'white').save(Path(d)/'image.png')
 monkeypatch.setattr(co,'execute',fake)
 assert co.CodexOAuthImages().generate('plane',tmp_path/'i.png',size='1536x1024',quality='medium',refs=[])['width']==320

def test_artifact_invalidation(tmp_path):
 from stickman.manifest import Manifest
 m=Manifest({'stages':{'voice':{'status':'ok','outputs':{'missing.mp3':'sha'}},'align':{'status':'ok'},'compose':{'status':'ok'},'verify':{'status':'ok'}}})
 assert set(m.revalidate(tmp_path))>={'voice','align','compose','verify'}
 m=Manifest({'stages':{s:{'status':'ok','outputs':{}} for s in ('script','voice','align','stills','compose','verify')},'config_sections_sha':{'render':'a','voice':'a'}})
 stale=m.revalidate(tmp_path,config_sections_sha={'render':'b','voice':'a'})
 assert 'compose' in stale and not set(stale)&{'script','voice','stills'}

def test_elevenlabs_contract(monkeypatch,tmp_path):
 from stickman.voice.elevenlabs import ElevenLabsVoice
 monkeypatch.setenv('ELEVENLABS_API_KEY','test-value');seen={}
 def post(url,**kw):seen.update(kw);return SimpleNamespace(status_code=200,content=b'a'*101)
 r=ElevenLabsVoice(_http=post,_probe=lambda p:2.5).synthesize('hi',tmp_path/'a.mp3',voice='sample',speed=.9,live=True)
 assert r['duration_s']==2.5 and seen['json']['voice_settings']['speed']==.9

def test_http_tts_contract(monkeypatch,tmp_path):
 import stickman.voice.http as h
 monkeypatch.setenv('TTS_API_KEY','test-value');seen={}
 class Response:
  content=b'audio'
  def raise_for_status(self):pass
 def post(url,**kw):seen.update(kw);return Response()
 monkeypatch.setattr(h.httpx,'post',post);monkeypatch.setattr(h,'probe_duration',lambda *args:2)
 r=h.HttpVoice(endpoint='https://example.com/speech',model='voice').synthesize('hi',tmp_path/'v.mp3',voice='narrator',speed=1,live=True)
 assert r['duration_s']==2 and seen['json']['input']=='hi'

def test_transparent_image_becomes_white(monkeypatch,tmp_path):
 import stickman.stills.codex_oauth as co
 def fake(prompt,d,**kw):Image.new('RGBA',(320,180),(0,0,0,0)).save(Path(d)/'image.png')
 monkeypatch.setattr(co,'execute',fake)
 p=tmp_path/'image.png';co.CodexOAuthImages().generate('plane',p,size='1536x1024',quality='medium',refs=[])
 assert Image.open(p).getpixel((0,0))==(255,255,255)

def test_release_scanner_fails_closed(tmp_path):
 import runpy
 funcs=runpy.run_path(str(Path(__file__).parents[1]/'tools/release.py'))
 (tmp_path/'okay.txt').write_text('public')
 assert funcs['scan'](tmp_path,['okay.txt'])==[]
 (tmp_path/'leak.txt').write_text('sk-'+'a'*32)
 findings=funcs['scan'](tmp_path,['okay.txt','leak.txt'])
 assert any(x['category']=='api-token' for x in findings)
 assert funcs['scan'](tmp_path,['okay.txt'])[0]['category']=='allowlist-mismatch'

def test_cli_config_writes_actual_toml(monkeypatch,tmp_path,capsys):
 from stickman.config import load_config
 monkeypatch.chdir(tmp_path)
 assert main(['config','set','project.language','es'])==0
 assert main(['config','set','project.target_minutes','1'])==0
 assert load_config(tmp_path)['project']['language']=='es'
 assert load_config(tmp_path)['project']['target_minutes']==1
 assert main(['config','show'])==0
 assert '"language": "es"' in capsys.readouterr().out
 assert main(['config','set','voice.api_key','do-not-save'])==1

def test_resume_without_active_does_not_consume_bank(tmp_path):
 p=tmp_path/'project';main(['init',str(p),'--topic','Untouched'])
 assert main(['resume','--project',str(p),'--live'])==0
 assert (p/'banco tema.txt').read_text()=='Untouched\n'
