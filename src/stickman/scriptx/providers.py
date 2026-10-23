"""Fábrica de providers de guion + re-exports (providers, http_llm,
codex_oauth). La fábrica elige por config [script] sin defaults
silenciosos: provider vacío -> ConfigError accionable."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stickman.scriptx import gates, schema
from stickman.errors import AuthError, ProviderError, RateLimitError
from stickman.errors import SchemaError as _ErrorsSchemaError


class ScriptError(_ErrorsSchemaError):
    pass


SchemaError = _ErrorsSchemaError

# Re-exports F4: las clases viven en http_llm/codex_oauth; se re-exportan
# aquí para que `stickman.scriptx.providers` sea el punto único de acceso.
from stickman.scriptx.codex_oauth import CodexOAuthScript  # noqa: E402,F401
from stickman.scriptx.http_llm import HttpLlmScript  # noqa: E402,F401


class ScriptProvider:
    name = "base"

    def requirements(self) -> list:
        return []

    def check(self) -> dict:
        return {"ok": True, "details": {}, "hint": ""}

    def draft(self, topic: str, out: Path, *, live: bool) -> dict:
        raise NotImplementedError


class LocalScript(ScriptProvider):
    """Vía avanzada: el usuario aporta el guion; se valida y copia."""

    name = "local-advanced"

    def __init__(self, script_path: str | Path):
        self.script_path = Path(script_path)

    def draft(self, topic: str, out: Path, *, live: bool) -> dict:
        _ = (topic, live)
        raw = self.script_path.read_text(encoding="utf-8")
        try:
            doc = json.loads(raw)
        except ValueError as e:
            raise SchemaError(f"guion no es JSON válido: {e}")
        errs = schema.validate_docu_en_1(doc)
        if errs:
            raise SchemaError("; ".join(errs))
        verdict, avg = gates.slideshow_gate(doc)
        if verdict == "fail":
            raise SchemaError(f"slideshow_gate=fail (promedio={avg})")
        prompts = {s.get("id", f"scene-{k}"): {
            "visual": s.get("visual", ""), "anchor": s.get("anchor", ""),
            "action": s.get("action", ""),
            "prompt": f"{s.get('visual', '')} {s.get('anchor', '')}"}
            for k, s in enumerate(doc.get("scenes", []))}
        verdict_v, viols = gates.variation_check(prompts)
        if verdict_v == "fail":
            raise SchemaError(f"variation_check=fail: {viols[0]}")
        out = Path(out)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        sha = hashlib.sha256(out.read_bytes()).hexdigest()
        return {"script_path": str(out), "script_sha256": sha,
                "model": "local-advanced"}


def make_script_provider(cfg: dict, *, _http=None):
    """Crea el ScriptProvider según cfg['script']. Sin default silencioso."""
    from stickman.config import ConfigError
    from stickman.scriptx import codex_oauth as _co
    from stickman.scriptx import http_llm as _hl
    section = (cfg.get("script") or {})
    provider = (section.get("provider") or "").strip()
    if provider == "local-advanced":
        path = section.get("from_script") or section.get("path") or ""
        if not path:
            raise ConfigError("script local-advanced exige --from-script")
        return LocalScript(path)
    if provider == "http":
        endpoint = (section.get("endpoint") or "").strip()
        api_key_env = (section.get("api_key_env") or "").strip()
        model = (section.get("model") or "").strip()
        missing = [k for k, v in (("endpoint", endpoint),
                                   ("api_key_env", api_key_env),
                                   ("model", model)) if not v]
        if missing:
            raise ConfigError(
                "script http exige en stickman.toml: "
                + ", ".join(missing))
        return _hl.HttpLlmScript(endpoint=endpoint, api_key_env=api_key_env,
                                 model=model, target_minutes=cfg["project"]["target_minutes"], language=cfg["project"]["language"], _http=_http)
    if provider == "codex-oauth":
        model = (section.get("model") or "").strip()
        return _co.CodexOAuthScript(model=model, language=cfg["project"]["language"], target_minutes=cfg["project"]["target_minutes"])
    raise ConfigError(
        "script.provider sin elegir: fija codex-oauth|http|local-advanced "
        "con `stickman init --script-provider ...` o --from-script")
