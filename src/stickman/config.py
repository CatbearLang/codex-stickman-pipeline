"""Configuración `stickman.toml` del proyecto (plan §4.2).

Secretos SOLO por entorno. `config set` rechaza claves cuyo nombre
sugiera secreto (SECRET_KEY_NAMES, plan §4.6) y las redirige a env.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SECRET_KEY_NAMES = (
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "api-key",
    "apikey",
)

VOICE_PROVIDERS = ("edge", "elevenlabs", "http")
IMAGE_PROVIDERS = ("codex-oauth", "openai-api")
SCRIPT_PROVIDERS = ("codex-oauth", "http", "local-advanced")


class ConfigError(Exception):
    pass


def default_config() -> dict:
    return {
        "project": {"slug": "", "language": "en", "target_minutes": 5.5,
                    "aspect": "16:9"},
        "voice": {"provider": "edge", "name": "en-US-AndrewNeural",
                  "speed": 1.0, "target_wpm": 150.0, "endpoint": "", "key_env": "TTS_API_KEY", "model": ""},
        "images": {"provider": "codex-oauth", "size": "1536x1024",
                   "quality": "medium", "reserve_regen": 8},
        "script": {"provider": "codex-oauth", "model": "", "endpoint": "",
                   "api_key_env": ""},
        "align": {"mode": "edge-words"},
        "render": {"fps": 30, "width": 1920, "height": 1080,
                   "xfade_s": 0.25, "lufs": -14.0, "true_peak_dbfs": -1.0,
                   "overhang_s": 0.0, "bgm": "accralate", "bgm_volume": 0.10},
        "paths": {"ffmpeg": ""},
    }


def validate_config(cfg: dict) -> bool:
    """Valida valores conocidos. script.provider "" solo en memoria (init)."""
    if cfg.get("voice", {}).get("provider") not in VOICE_PROVIDERS:
        raise ConfigError(
            f"unknown voice.provider: {cfg['voice']['provider']!r} "
            f"(options: {', '.join(VOICE_PROVIDERS)})")
    if cfg.get("images", {}).get("provider") not in IMAGE_PROVIDERS:
        raise ConfigError(
            f"unknown images.provider: {cfg['images']['provider']!r}")
    sp = cfg.get("script", {}).get("provider", "")
    if sp not in SCRIPT_PROVIDERS and sp != "":
        raise ConfigError(f"unknown script.provider: {sp!r}")
    lang = cfg.get("project", {}).get("language", "en")
    if lang not in ("en", "es"):
        raise ConfigError(f"project.language must be en|es, got {lang!r}")
    import math
    for section, field, low, high in (("voice","speed",0.5,2),("project","target_minutes",0.1,60),("render","fps",1,60),("render","width",320,3840),("render","height",180,2160),("render","xfade_s",0.05,1),("images","reserve_regen",0,36)):
        v=cfg[section][field]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low <= v <= high:
            raise ConfigError(f"{section}.{field} must be between {low} and {high}")
    for field in ("width","height"):
        if int(cfg["render"][field]) != cfg["render"][field] or cfg["render"][field] % 2:
            raise ConfigError("Render dimensions must be even integers")
    return True


def load_config(project_dir: str | Path) -> dict:
    """Lee stickman.toml, fusiona sobre defaults y valida."""
    cfg = default_config()
    path = Path(project_dir) / "stickman.toml"
    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for section, values in data.items():
            if isinstance(values, dict) and section in cfg:
                cfg[section].update(values)
            elif section in cfg:
                cfg[section] = values
            else:
                raise ConfigError(f"unknown section: {section!r}")
    validate_config(cfg)
    return cfg


def config_set(project_dir: str | Path, clave: str, valor: str) -> str:
    """`stickman config set <clave> <valor>`. Rechaza nombres de secreto."""
    lowered = clave.lower()
    for secret_name in SECRET_KEY_NAMES:
        if secret_name.lower() in lowered and not lowered.endswith("_env"):
            env_guess = clave.upper().replace(".", "_").replace("-", "_")
            return (f"use environment variable {env_guess} instead of "
                    f"saving {clave!r} in stickman.toml (secrets must "
                    f"never be stored in project configuration)")
    parts = clave.split(".")
    if len(parts) != 2 or parts[0] not in default_config():
        return (f"error: invalid key {clave!r} "
                f"(use section.field, for example voice.provider)")
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    try:
        cfg = load_config(project_dir)
    except ConfigError:
        cfg = default_config()
    section, field = parts
    raw = valor
    try:
        parsed: object = float(valor)
        if parsed == int(parsed):
            parsed = int(parsed)
        value = parsed
    except ValueError:
        value = raw
    cfg[section][field] = value
    try:
        validate_config(cfg)
    except ConfigError as e:
        return f"error: {e}"
    path = project_dir / "stickman.toml"
    lines = []
    for section_name, values in cfg.items():
        lines.append(f"[{section_name}]")
        for k, v in values.items():
            lines.append(f"{k} = {__import__('json').dumps(v, ensure_ascii=False)}" if isinstance(v, str)
                         else f"{k} = {v}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"ok: {clave} saved in {path}"


def resolve_secret(name: str) -> str:
    """Lee un secreto SOLO del entorno (presencia/longitud, jamás loguear)."""
    return os.environ.get(name, "")
