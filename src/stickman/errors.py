"""Errores de proveedores: jerarquía común, sin fallback silencioso.

ProviderError = fallo de proveedor (exit 3 en CLI).
AuthError     = credencial ausente/inválida (mensaje accionable).
RateLimitError= 429/cuota (no reintenta infinito, no cambia de proveedor).
"""
from __future__ import annotations


class ProviderError(RuntimeError):
    pass


class LiveGateError(RuntimeError):
    """Falta autorización --live (exit 2 en CLI).

    NO es un fallo de proveedor: se lanza ANTES de cualquier llamada
    externa para garantizar cero gasto sin autorización explícita.
    Intencionadamente fuera de la jerarquía ProviderError para que el
    CLI la distinga de un fallo de proveedor (exit 3).
    """


class AuthError(ProviderError):
    pass


class RateLimitError(ProviderError):
    pass


class SchemaError(ProviderError):
    pass
