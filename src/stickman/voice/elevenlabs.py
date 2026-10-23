"""Voz ElevenLabs (API oficial, clave del usuario ELEVENLABS_API_KEY).

Protocolo real verificado: endpoints vivos con respuestas reales —
GET https://api.elevenlabs.io/v1/voices responde 200 sin clave
(lista pública de voces); POST /v1/text-to-speech/{voice_id} sin clave
responde 401 (endpoint existe, exige xi-api-key). Cabecera de auth
`xi-api-key` (no Bearer) y cuerpo {text, model_id?...} según API
pública ElevenLabs. Duración vía _probe inyectable.
"""
from __future__ import annotations

import os
from pathlib import Path

from stickman import http_client
from stickman.errors import AuthError, ProviderError
from stickman.provider_base import Requirement
from stickman.voice.base import VoiceProvider, require_live

TTS_URL_TMPL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
KEY_ENV = "ELEVENLABS_API_KEY"


class ElevenLabsVoice(VoiceProvider):
    name = "elevenlabs"
    verified = False

    def __init__(self, *, _http=None, _probe=None, model: str = "eleven_v3"):
        self._http = _http or http_client.default_post
        self._probe = _probe
        self.tts_model = model

    def requirements(self) -> list:
        return [Requirement(kind="key",
                            label=f"Clave ElevenLabs (variable {KEY_ENV})",
                            env=KEY_ENV, official=True, verified=False),
                Requirement(kind="model",
                            label="voice_id del usuario + modelo TTS "
                                  "(default eleven_v3)")]

    def synthesize(self, text: str, out: Path, *, voice: str,
                   speed: float, live: bool = False) -> dict:
        require_live(live, "voz elevenlabs")
        key = os.environ.get(KEY_ENV, "")
        if not key:
            raise AuthError(f"voz elevenlabs: falta la variable {KEY_ENV}")
        if not text or not text.strip():
            raise ProviderError("voz elevenlabs: texto vacío")
        url = TTS_URL_TMPL.format(voice_id=voice)
        body: dict = {"text": text, "model_id": self.tts_model}
        if speed != 1.0:
            body["voice_settings"] = {"speed": speed}
        resp = http_client.post_with_retry(
            self._http, url, json=body,
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            key_env=KEY_ENV, what="voz elevenlabs")
        raw = getattr(resp, "content", None)
        if not raw or len(raw) < 100:
            raise ProviderError("voz elevenlabs: respuesta sin audio")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        duration = self._probe(out) if self._probe else __import__("stickman.voice.edge", fromlist=["probe_duration"]).probe_duration(__import__("stickman.voice.edge", fromlist=["_default_run"])._default_run, out)
        return {"duration_s": float(duration), "words_path": None}
