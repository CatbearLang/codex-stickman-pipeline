"""Guion automático vía HTTP genérica (OpenAI-compatible) del usuario.

Protocolo real verificado contra docs xAI (api.x.ai/v1/chat/completions,
Bearer, cuerpo {model, messages}) y contra la API con clave falsa
(HTTP 400 con cuerpo JSON, confirma endpoint vivo). El usuario aporta
endpoint + modelo + variable de entorno con la clave en [script].

Doble gate: live=True (CLI --live) + SCRIPT_LIVE_OK=1. Sin gate no hay
llamada. Respuesta validada con docu-en-1 ANTES de escribir el fichero.

Sin reintentos implicitos Codex: este provider NO llama a Codex; los
reintentos HTTP solo cubren 5xx/red (jamas 429) segun http_client.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from stickman import http_client
from stickman.errors import AuthError, SchemaError
from stickman.provider_base import Provider, Requirement
from stickman.scriptx import gates, schema

SCRIPT_LIVE_ENV = "SCRIPT_LIVE_OK"

SCRIPT_SYSTEM = (
    "Write an engaging documentary script as JSON using docu-en-1: "
    "{title, language, target_minutes, scenes[] with unique snake_case IDs, "
    "voiceover, visual, anchor, action, concepts[] with narration_span values "
    "that exactly cover the voiceover}. Do not repeat the title in the opening narration. "
    "Write about 145 spoken words per requested minute and include a distinct visual "
    "concept for roughly every 6-12 seconds, with no narration_span over 29 words. "
    "Return only JSON, without Markdown."
)


class HttpLlmScript(Provider):
    """POST JSON al endpoint del usuario (formato chat-completions)."""

    name = "http"
    verified = False

    def __init__(self, *, endpoint: str, api_key_env: str, model: str, target_minutes: float = 5.5, language: str = "en",
                 _http=None, _sleep=None, _max_attempts: int = 3):
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.model = model
        self.target_minutes = target_minutes
        self.language = language
        self._http = _http or http_client.default_post
        self._sleep = _sleep
        self._max_attempts = _max_attempts

    def requirements(self) -> list:
        return [Requirement(kind="key",
                            label=f"Clave LLM (variable {self.api_key_env})",
                            env=self.api_key_env, official=True,
                            verified=False),
                Requirement(kind="model",
                            label=f"Endpoint y modelo del usuario "
                                  f"({self.endpoint or 'sin endpoint'} / "
                                  f"{self.model or 'sin modelo'})")]

    def _extract_doc(self, resp) -> dict:
        try:
            payload = resp.json()
        except Exception as e:
            raise SchemaError(f"guion http: respuesta sin JSON ({e})")
        content = None
        try:
            choices = payload.get("choices") or []
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError, AttributeError):
            pass
        if content is None:
            for key in ("output_text", "text", "content"):
                if isinstance(payload.get(key), str):
                    content = payload[key]
                    break
        if not isinstance(content, str) or not content.strip():
            raise SchemaError("guion http: respuesta sin texto docu-en-1")
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            if text.rsplit("```", 1)[0].strip():
                text = text.rsplit("```", 1)[0]
        try:
            doc = json.loads(text)
        except ValueError as e:
            raise SchemaError(f"guion http: el modelo no devolvió "
                              f"docu-en-1 válido ({e})")
        if not isinstance(doc, dict):
            raise SchemaError("guion http: el modelo no devolvió un objeto")
        return doc

    def draft(self, topic: str, out: Path, *, live: bool) -> dict:
        if not live:
            raise RuntimeError("guion automático requiere --live + "
                               "SCRIPT_LIVE_OK=1 (sin llamadas en otro caso)")
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise AuthError(f"guion http: falta la variable {self.api_key_env} "
                            f"con la clave del usuario")
        body = {"model": self.model,
                "messages": [{"role": "system", "content": SCRIPT_SYSTEM},
                             {"role": "user",
                              "content": f"Topic: {topic}. Write a complete docu-en-1 script for {self.target_minutes:g} minutes in language {self.language}."}],
                "temperature": 0.7}
        resp = http_client.post_with_retry(
            self._http, self.endpoint, json=body,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"},
            max_attempts=self._max_attempts,
            sleep=self._sleep,
            key_env=self.api_key_env, what="guion http")
        doc = self._extract_doc(resp)
        errs = schema.validate_docu_en_1(doc) + schema.validate_pacing(doc, self.target_minutes)
        if doc.get("language") != self.language:
            errs.append(f"Script language must be {self.language!r}")
        if errs:
            raise SchemaError("guion http inválido: " + "; ".join(errs))
        verdict, avg = gates.slideshow_gate(doc)
        if verdict == "fail":
            raise SchemaError(f"guion http: slideshow_gate=fail ({avg})")
        out = Path(out)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        sha = hashlib.sha256(out.read_bytes()).hexdigest()
        return {"script_path": str(out), "script_sha256": sha,
                "model": self.model}
