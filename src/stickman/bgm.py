"""BGM empaquetada: Accralate (CC BY 4.0) por defecto, ambient propia, none/custom.

Procedencia verificada (solo lectura, sin modificar el origen):
- Fuente: Kevin MacLeod (incompetech.com), CC BY 4.0
- Licencia declarada en the original project LICENSES.txt:
  '"Accralate" por Kevin MacLeod (incompetech.com), Creative Commons:
  By Attribution 4.0, http://creativecommons.org/licenses/by/4.0/,
  descarga: archive.org/details/Incompetech'
- Copia byte-identica en src/stickman/assets/music/accralate.mp3
  (md5 b9a667797ffb9db79bb4b9e36bf26790 en origen y copia).

Modos de `render.bgm`:
- "accralate" (default): pista CC BY 4.0 incluida -> requiere credito.
- "bundled" / "ambient": cama procedural propia (product license).
- "none": sin musica.
- cualquier otro valor: ruta a pista propia del usuario (relativa al
  proyecto o absoluta); el usuario conserva su licencia/atribucion.
"""
from __future__ import annotations

from pathlib import Path

MUSIC_DIR = Path(__file__).resolve().parent / "assets" / "music"

ACCRALATE_CREDIT = (
    '"Accralate" Kevin MacLeod (incompetech.com) — Licensed under '
    "Creative Commons: By Attribution 4.0 — "
    "http://creativecommons.org/licenses/by/4.0/"
)
ACCRALATE_SOURCE = "archive.org/details/Incompetech"

KNOWN_MODES = ("accralate", "bundled", "ambient", "none")


def resolve_bgm(bgm_value: str | None, project_dir: str | Path | None = None
                ) -> tuple[Path | None, str | None, str | None]:
    """Resuelve `render.bgm` a (ruta_audio_o_None, track_id, credito_o_None).

    track_id: "accralate" | "ambient" | "custom" | None (none).
    Lanza FileNotFoundError si una ruta custom no existe (el composer la
    convierte en RenderError accionable).
    """
    value = (bgm_value or "accralate").strip() or "accralate"
    if value == "none":
        return None, None, None
    if value == "accralate":
        return MUSIC_DIR / "accralate.mp3", "accralate", ACCRALATE_CREDIT
    if value in ("bundled", "ambient"):
        return MUSIC_DIR / "ambient.wav", "ambient", None
    p = Path(value)
    if not p.is_absolute() and project_dir is not None:
        p = Path(project_dir) / p
    if not p.exists():
        raise FileNotFoundError(
            f"render.bgm: no existe la pista {value!r} "
            f"(resuelta como {p}); usa accralate|bundled|ambient|none "
            "o una ruta valida a tu propia pista licenciada)")
    return p, "custom", None


def bgm_filter(bgm_index: int, volume: float = 0.10
                ) -> tuple[list[str], str, str]:
    """Fragmentos filter_complex para mezclar el BGM con ducking.

    bgm_index: indice del input ffmpeg de la musica (p. ej. 2 o 3).
    Retorna (labels, narr_mix, bgm_mix): labels para anteponer al
    filter_complex, "[nmix]" (narracion) y "[g]" (musica con ducking)
    como etiquetas listas para el amix final.
    Ducking real con sidechaincompress (voz = key): la musica baja bajo
    la narracion y vuelve en pausas; verificado sin clipping (pico de
    mezcla <= -11 dB, master final con loudnorm TP=-1.5).
    La narracion se divide con asplit porque un pad de filtro solo
    puede consumirse una vez (key del sidechain + mezcla final).
    """
    v = float(volume)
    return ([
        f"[{bgm_index}:a]aresample=44100,volume={v}[g_pre]",
        "[n]asplit=2[nmix][nkey]",
        "[g_pre][nkey]sidechaincompress=threshold=0.02:ratio=8"
        ":attack=5:release=400[g]",
    ], "[nmix]", "[g]")


def caption_block(track_id: str | None, credit: str | None) -> str:
    """Bloque de credito para caption.txt ("" si no hay musica con credito).

    Solo atribuye la pista incluida CC BY; las pistas custom/ambient no
    anaden nada para no sobrescribir creditos del usuario.
    """
    if track_id == "accralate" and credit:
        return f"\nMusic: {credit}\nSource: {ACCRALATE_SOURCE}\n"
    return ""
