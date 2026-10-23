"""Logging con redacción de secretos (plan §4.6).

`redact` se aplica ANTES de emitir cualquier mensaje. `check`/`status`/
informes imprimen presencia (set/longitud), jamás valores.
"""
from __future__ import annotations

import logging
import re

SECRET_VALUE_PATTERNS = [
    r"sk-[A-Za-z0-9]{8,}",
    r"xai-[A-Za-z0-9]{8,}",
    r"ghp_[A-Za-z0-9]{8,}",
    r"gho_[A-Za-z0-9]{8,}",
    r"AKIA[0-9A-Z]{8,}",
    r"-----BEGIN .*PRIVATE KEY-----",
    r"bearer\s+[A-Za-z0-9._~+/-]{10,}",
    r"refresh_token\s*[:=]\s*\S{8,}",
]

_REDACT_RES = [re.compile(p, re.I) for p in SECRET_VALUE_PATTERNS]


def redact(text: str) -> str:
    """Sustituye valores con forma de secreto live por [redacted]."""
    out = str(text)
    for rx in _REDACT_RES:
        out = rx.sub("[redacted]", out)
    return out


class _RedactingHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        record.msg = redact(record.getMessage())
        record.args = ()
        super().emit(record)


def get_logger(name: str = "stickman") -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(h, _RedactingHandler) for h in logger.handlers):
        h = _RedactingHandler()
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
