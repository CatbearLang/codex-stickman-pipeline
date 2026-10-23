"""Stills vía API oficial OpenAI Images (clave OPENAI_API_KEY).

Protocolo real verificado: POST
https://api.openai.com/v1/images/generations sin clave responde 401
con cuerpo JSON de error (endpoint existe). Cuerpo {model, prompt,
size} + response_format b64_json; respuesta data[0].b64_json (PNG).
401/403 -> AuthError accionable con la variable. Tamaño configurable
(default 1536x1024 de [images]).
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from stickman import http_client
from stickman.errors import AuthError, ProviderError
from stickman.provider_base import Requirement
from stickman.stills.base import ImageProvider
from stickman.stills.runner import png_dimensions, sha256_file

IMAGES_URL = "https://api.openai.com/v1/images/generations"
KEY_ENV = "OPENAI_API_KEY"


class OpenAIImages(ImageProvider):
    name = "openai-api"
    verified = False

    def __init__(self, *, _http=None, model: str = "gpt-image-1"):
        self._http = _http or http_client.default_post
        self.model = model

    def requirements(self) -> list:
        return [Requirement(kind="key",
                            label=f"Clave OpenAI (variable {KEY_ENV})",
                            env=KEY_ENV, official=True, verified=False),
                Requirement(kind="model",
                            label="Modelo de imagen configurable "
                                  "(default gpt-image-1)")]

    def generate(self, prompt: str, out: Path, *, size: str, quality: str,
                 refs: list[Path]) -> dict:
        _ = (quality, refs)
        key = os.environ.get(KEY_ENV, "")
        if not key:
            raise AuthError(f"stills openai: falta {KEY_ENV}")
        if not prompt or not prompt.strip():
            raise ProviderError("stills openai: prompt vacío")
        resp = http_client.post_with_retry(
            self._http, IMAGES_URL,
            json={"model": self.model, "prompt": prompt, "size": size,
                  "response_format": "b64_json"},
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"},
            key_env=KEY_ENV, what="stills openai")
        try:
            b64 = resp.json()["data"][0]["b64_json"]
            raw = base64.b64decode(b64, validate=True)
        except Exception as e:
            raise ProviderError(f"stills openai: respuesta sin imagen ({e})")
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise ProviderError("stills openai: resultado no es PNG")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        w, h = png_dimensions(out)
        return {"bytes": len(raw), "sha256": sha256_file(out),
                "width": w, "height": h}
