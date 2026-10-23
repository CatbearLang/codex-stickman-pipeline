"""Interfaz VoiceProvider (§4.3): synthesize -> {duration_s, words_path}.

Contrato de gasto (rework t_cef89cbd, D1 BLOQUEANTE): TODA síntesis de
voz es una llamada externa (red con clave/token o subproceso edge-tts)
y exige autorización explícita `live=True`. Sin live el adaptador
lanza RuntimeError ANTES de leer credenciales o tocar red/subproceso
(cero llamadas externas). La presencia de una clave o token en el
entorno NUNCA autoriza gasto por sí sola. `stickman run --stage voice`
solo pasa live=True con `--live` y mapea la falta de autorización a
exit 2. Cualquier flow futuro (banco F9, compose, etc.) debe propagar
este mismo flag `live` hasta synthesize; no llamar a synthesize sin
`live=True` fuera de tests con doubles.
"""
from __future__ import annotations

from pathlib import Path

from stickman.provider_base import Provider


def require_live(live: bool, what: str) -> None:
    """Gate central de gasto: lanza LiveGateError si no hay autorización.

    Debe ser la PRIMERA línea de todo `synthesize` real, antes de leer
    variables de entorno o invocar red/subproceso, para que ningún
    bypass (clave presente sin --live) genere llamadas externas.
    """
    from stickman.errors import LiveGateError

    if not live:
        raise LiveGateError(
            f"{what}: exige autorización --live (sin --live no hay "
            f"llamadas externas; en tests usa doubles con live=True)")


class VoiceProvider(Provider):
    def synthesize(self, text: str, out: Path, *, voice: str,
                   speed: float, live: bool = False) -> dict:
        raise NotImplementedError
