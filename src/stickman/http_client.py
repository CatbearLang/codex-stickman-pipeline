"""Transporte HTTP compartido: httpx, retries acotados solo en 5xx/red,
timeouts, errores accionables sin filtrar secretos (solo presencia)."""
from __future__ import annotations

import time
from typing import Callable

from stickman.errors import AuthError, ProviderError, RateLimitError

RETRYABLE_STATUS = {500, 502, 503, 504}
DEFAULT_TIMEOUT = 120.0


def default_post(url, *, json=None, headers=None, timeout=None):
    import httpx
    with httpx.Client(timeout=timeout or DEFAULT_TIMEOUT) as client:
        resp = client.post(url, json=json, headers=headers or {})
    return resp


def post_with_retry(post: Callable, url: str, *, json=None, headers=None,
                    timeout=None, max_attempts: int = 3,
                    sleep: Callable[[float], None] | None = None,
                    key_env: str = "", what: str = "proveedor") -> object:
    """POST con reintentos acotados. 401/403->AuthError, 429->RateLimitError.

    429 NO se reintenta (cuota: reintentar quema presupuesto/tiempo; el
    error se propaga y el operador decide). 5xx/errores de red: hasta
    max_attempts con backoff. `sleep` inyectable. Sin fallback.
    """
    _sleep = sleep or (lambda s: time.sleep(s))
    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = post(url, json=json, headers=headers or {},
                        timeout=timeout or DEFAULT_TIMEOUT)
        except Exception as e:  # error de red: reintentable si quedan intentos
            last = e
            if attempt < max_attempts:
                _sleep(min(2.0 * attempt, 10.0))
                continue
            raise ProviderError(
                f"{what}: error de red tras {max_attempts} intentos ({e})")
        status = getattr(resp, "status_code", 200)
        if status == 200:
            return resp
        body = ""
        try:
            body = (resp.text or "")[:300]
        except Exception:
            body = ""
        if status in (401, 403):
            hint = f"revisa {key_env}" if key_env else "revisa la credencial"
            raise AuthError(f"{what}: no autorizado (HTTP {status}). {hint}. "
                            f"Detalle: {body}")
        if status == 429:
            raise RateLimitError(
                f"{what}: cuota/límite excedido (HTTP 429). No se reintenta "
                f"ni se cambia de proveedor. Detalle: {body}")
        if status in RETRYABLE_STATUS and attempt < max_attempts:
            _sleep(min(2.0 * attempt, 10.0))
            continue
        raise ProviderError(f"{what}: HTTP {status}. Detalle: {body}")
    raise ProviderError(f"{what}: fallo tras {max_attempts} intentos ({last})")
