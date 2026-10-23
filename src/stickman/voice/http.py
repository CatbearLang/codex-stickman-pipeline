"""Configurable OpenAI-compatible speech endpoint (binary audio response)."""
import os
from pathlib import Path
from urllib.parse import urlparse
import httpx
from .base import VoiceProvider, require_live
from .edge import probe_duration, _default_run
from stickman.errors import AuthError, ProviderError

class HttpVoice(VoiceProvider):
    name='http'
    def __init__(self, *, endpoint, key_env='TTS_API_KEY', model=''):
        self.endpoint,self.key_env,self.model=endpoint,key_env,model
    def synthesize(self,text,out,*,voice,speed,live=False):
        require_live(live,'HTTP TTS')
        if urlparse(self.endpoint).scheme!='https': raise ProviderError('voice.endpoint must be HTTPS.')
        key=os.environ.get(self.key_env,'')
        if not key: raise AuthError('Set the environment variable named in voice.key_env.')
        try:
            r=httpx.post(self.endpoint,json={'model':self.model,'input':text,'voice':voice,'speed':speed,'response_format':'mp3'},headers={'Authorization':'Bearer '+key},timeout=180,follow_redirects=False)
            r.raise_for_status()
        except httpx.HTTPError:
            raise ProviderError('HTTP TTS failed. Check endpoint, model, quota and credentials; response omitted for privacy.') from None
        out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(r.content)
        return {'duration_s':probe_duration(_default_run,out),'words_path':None}
