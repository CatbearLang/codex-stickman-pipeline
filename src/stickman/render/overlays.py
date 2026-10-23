"""render/overlays.py — motor de overlays portado del canónico overlays_v3.

Cambio clave v6 (lección del origen): composición DIRECTA en Pillow sobre
el frame RGB. NUNCA un mp4 intermedio RGBA (libx264/yuv420p aplasta el
alfa — bug "rectángulo negro" del origen, corregido por construcción).

Contrato visual v2/v6 implementado (paridad con overlays_v3.py, sin
módulos por tema ni rutas privadas):
  Tarjetas : texto Inter Bold tinta #26221C con halo claro, auto-fit al
             riel de safe area (1920-2*240), máx 2 líneas ~37 chars.
  Números  : Inter Bold acento oscuro #9A4A12 + halo, scale-pop 120%->100%
             en 6 frames.
  Flechas  : asta + punta con contorno oscuro y overshoot sinusoidal.
  Safe area: 54 px vert / 240 px horiz; top ancla y=110; bot banda 860-990.
  Timing   : el `at` de la spec ES el instante de la palabra clave;
             duración auto = 0.3 s/palabra + colchón (0.5-1 s), acotada
             [0.83, 7] s.
  Easing   : fade-in smoothstep 0.35 s tarjetas / 0.2 s números, fade-out
             0.25 s, scale-pop ease_out_cubic, overshoot sinusoidal.

Fuentes OFL del proyecto (assets/fonts + textos de licencia), no del
sistema: el proyecto es portable (H3: sin rutas privadas).
spec JSON serializable (H2, plan §2): auditable, sin ejecutar código.

API: normalize_spec, auto_duration, card_box, num_box, compose,
compose_scene, specs_from_script, momentos_num.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FPS = 30

CARBON = (38, 34, 28)          # #26221C — tinta del texto
CAJA = (11, 14, 20)            # contorno oscuro (flechas)
PLACA_CREMA = (242, 227, 198)  # legado: geometría del contrato v2
ACENTO = (255, 214, 64)
NUM_INK = (154, 74, 18)        # acento naranja oscuro legible (v6)
HALO = (255, 251, 240)         # halo casi-blanco cálido
HALO_W_CARD = 3
HALO_W_NUM = 4
RADIO = 20
PAD_X, PAD_Y = 24, 14
MAX_CHARS_LINEA = 37
MAX_LINEAS = 2
SAFE_X, SAFE_Y = 240, 54
TOP_Y = 110
BOT_Y = 985
CARD_SIZE = 72                 # Inter 64-84 (contrato v3.1)
NUM_SIZE = 132                 # League Spartan 110-150 -> Inter Bold aquí
KICKER_SIZE = 38
FADE_IN_CARD = 0.35
FADE_IN_NUM = 0.20
FADE_OUT = 0.25
POP_FRAMES = 6
POP_T = POP_FRAMES / FPS
ARROW_SHAFT = 12
ARROW_HEAD = 34
ARROW_OVERSHOOT = 30
DUR_MIN, DUR_MAX = 0.83, 7.0

PKG_FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_INTER = "Inter-Variable.ttf"

_FCACHE: dict = {}


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key in _FCACHE:
        return _FCACHE[key]
    p = PKG_FONTS / FONT_INTER
    if not p.exists():
        raise RuntimeError(
            f"falta fuente OFL del proyecto: {p} (no instalada o proyecto incompleto; "
            "las fuentes NO se descargan de la red)")
    f = ImageFont.truetype(str(p), size)
    f.set_variation_by_axes([32, 700])   # opsz pantalla + Bold (canónico v6)
    _FCACHE[key] = f
    return f


def fit_font(kind: str, size: int, max_w: int, texto: str,
             min_size: int = 24) -> int:
    while size > min_size:
        if _ancho_texto(_font(kind, size), texto) <= max_w:
            return size
        size -= 2
    return min_size


def _ancho_texto(font, txt: str) -> int:
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    b = d.textbbox((0, 0), txt, font=font)
    return b[2] - b[0]


def _smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def _ease_out_cubic(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1.0 - (1.0 - x) ** 3


def auto_duration(texto: str, colchon: float = 0.8) -> float:
    """0.3 s × palabra + colchón (0.5-1 s), acotada a [0.83, 7] s."""
    if not 0.5 <= colchon <= 1.0:
        raise ValueError("colchón fuera del contrato (0.5-1 s)")
    palabras = len([p for p in texto.split() if p])
    return min(DUR_MAX, max(DUR_MIN, 0.3 * palabras + colchon))


_WS = re.compile(r"\s+")


def _wrap(txt: str) -> str:
    palabras, lines, cur = txt.split(), [], ""
    for p in palabras:
        cand = f"{cur} {p}".strip()
        if len(cand) > MAX_CHARS_LINEA and cur:
            lines.append(cur)
            cur = p
        else:
            cur = cand
    if cur:
        lines.append(cur)
    if len(lines) > MAX_LINEAS:
        raise ValueError(f">{MAX_LINEAS} líneas: {txt!r}")
    return "\n".join(lines)


def normalize_spec(spec: dict) -> dict:
    """Rellena dur (auto) y valida límites de líneas (canónico)."""
    s = dict(spec)
    if s["t"] in ("card", "num", "card_sketch", "num_pop"):
        txt = s.get("l1") or s.get("txt") or ""
        if s.get("l2"):
            txt = f"{txt} {s['l2']}"
        s.setdefault("colchon",
                     1.0 if s["t"] in ("num", "num_pop") else 0.8)
        s.setdefault("dur", round(auto_duration(txt, s["colchon"]), 3))
    else:
        s.setdefault("dur", 1.5)
    if s["t"] in ("card", "card_sketch"):
        if s.get("l1") and len(s["l1"]) > MAX_CHARS_LINEA and not s.get("l2"):
            if len(s["l1"]) > 2 * MAX_CHARS_LINEA:
                raise ValueError(
                    f"l1 no cabe en 2 líneas (<={2 * MAX_CHARS_LINEA} chars): "
                    f"{s['l1'][:40]!r}...")
            s["l1"] = _wrap(s["l1"])
        if s.get("l2") and len(s["l2"]) > MAX_CHARS_LINEA:
            raise ValueError(f"l2 >{MAX_CHARS_LINEA} chars: {s['l2']!r}")
    return s


def _card_lines(spec: dict) -> list:
    l1 = spec.get("l1", "")
    if "\n" in l1:
        return l1.split("\n")
    return [l1] + ([spec["l2"]] if spec.get("l2") else [])


def _anchor_y(spec: dict, box_h: int) -> int:
    if spec.get("pos", "bot") == "top":
        return TOP_Y
    return BOT_Y - box_h


def card_box(spec: dict) -> tuple:
    lines = _card_lines(spec)
    max_w = W - 2 * SAFE_X - 2 * PAD_X
    joined = max(lines, key=len)
    fsz = fit_font("card", CARD_SIZE, max_w, joined)
    f = _font("card", fsz)
    tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    ws, hs = [], []
    for ln in lines:
        b = tmp.textbbox((0, 0), ln, font=f)
        ws.append(b[2] - b[0])
        hs.append(b[3] - b[1])
    box_w = max(ws) + 2 * PAD_X
    box_h = sum(hs) + 10 * (len(lines) - 1) + 2 * PAD_Y
    y0 = _anchor_y(spec, box_h)
    return (SAFE_X, y0, SAFE_X + box_w, y0 + box_h)


def num_box(spec: dict) -> tuple:
    max_w = W - 2 * SAFE_X - 2 * PAD_X
    fsz = fit_font("num", NUM_SIZE, max_w, spec["txt"])
    tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    b = tmp.textbbox((0, 0), spec["txt"], font=_font("num", fsz))
    box_w = (b[2] - b[0]) + 2 * PAD_X
    box_h = (b[3] - b[1]) + 2 * PAD_Y
    y0 = _anchor_y(spec, box_h)
    return (SAFE_X, y0, SAFE_X + box_w, y0 + box_h)


def _alpha_mult(img: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return img
    r, g, b, al = img.split()
    al = al.point(lambda v: int(v * a))
    return Image.merge("RGBA", (r, g, b, al))


def _text_halo(d, xy: tuple, ln: str, font, ink: tuple, halo: tuple,
               w: int) -> None:
    x, y = xy
    for dx in range(-w, w + 1):
        for dy in range(-w, w + 1):
            if dx == 0 and dy == 0:
                continue
            if dx * dx + dy * dy > w * w:
                continue
            d.text((x + dx, y + dy), ln, font=font, fill=halo)
    d.text((x, y), ln, font=font, fill=ink)


def _render_card(spec: dict) -> tuple:
    x0, y0, x1, y1 = card_box(spec)
    w, h = x1 - x0, y1 - y0
    lines = _card_lines(spec)
    max_w = W - 2 * SAFE_X - 2 * PAD_X
    fsz = fit_font("card", CARD_SIZE, max_w, max(lines, key=len))
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    ink = (*CARBON, 255)
    halo = (*HALO, 255)
    f = _font("card", fsz)
    gap = 10
    total_h = sum(d.textbbox((0, 0), ln, font=f)[3] for ln in lines) \
        + gap * (len(lines) - 1)
    y = (h - total_h) / 2
    for ln in lines:
        b = d.textbbox((0, 0), ln, font=f)
        _text_halo(d, (PAD_X - b[0], y - b[1]), ln, f, ink, halo,
                   HALO_W_CARD)
        y += b[3] + gap
    return ov, (x0, y0)


def _render_num(spec: dict, scale: float = 1.0) -> tuple:
    x0, y0, x1, y1 = num_box(spec)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    fsz = fit_font("num", NUM_SIZE, W - 2 * SAFE_X - 2 * PAD_X, spec["txt"])
    fs = int(round(fsz * scale))
    f = _font("num", fs)
    tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    b = tmp.textbbox((0, 0), spec["txt"], font=f)
    tw, th = b[2] - b[0], b[3] - b[1]
    w, h = tw + 2 * PAD_X, th + 2 * PAD_Y
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _text_halo(d, (PAD_X - b[0], PAD_Y - b[1]), spec["txt"], f,
               (*NUM_INK, 255), (*HALO, 255), HALO_W_NUM)
    return ov, (int(cx - w / 2), int(cy - h / 2))


def _render_arrow(p0, p1, overshoot_px: float) -> tuple:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    tip = (p1[0] + ux * overshoot_px, p1[1] + uy * overshoot_px)
    x0 = int(min(p0[0], tip[0]) - ARROW_HEAD - 4)
    y0 = int(min(p0[1], tip[1]) - ARROW_HEAD - 4)
    x1 = int(max(p0[0], tip[0]) + ARROW_HEAD + 4)
    y1 = int(max(p0[1], tip[1]) + ARROW_HEAD + 4)
    ov = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    a = (p0[0] - x0, p0[1] - y0)
    t = (tip[0] - x0, tip[1] - y0)
    perp = (-uy, ux)
    s, hw = ARROW_HEAD, ARROW_SHAFT
    head = [t,
            (t[0] - ux * s + perp[0] * hw, t[1] - uy * s + perp[1] * hw),
            (t[0] - ux * s - perp[0] * hw, t[1] - uy * s - perp[1] * hw)]
    d.line([a, t], fill=(*CAJA, 230), width=hw * 2 + 6)
    d.polygon(head, fill=(*CAJA, 230))
    d.line([a, t], fill=(*ACENTO, 255), width=hw)
    d.polygon(head, fill=(*ACENTO, 255))
    return ov, (x0, y0)


def compose(frame_rgb: Image.Image, spec: dict, t_local: float) -> Image.Image:
    """Compone UN overlay sobre frame RGB en t_local (desde su `at`).
    Muta y devuelve frame_rgb. PIL paste directo (sin RGBA intermedio)."""
    dur = spec.get("dur", 0.0)
    if t_local < 0 or t_local > dur:
        return frame_rgb
    kind = spec["t"]
    if kind in ("card", "card_sketch"):
        a = _smoothstep(t_local / FADE_IN_CARD)
        ov, pos = _render_card(spec)
    elif kind in ("num", "num_pop"):
        a = min(1.0, t_local / FADE_IN_NUM)
        scale = 1.0 + 0.2 * (1.0 - _ease_out_cubic(t_local / POP_T))
        ov, pos = _render_num(spec, scale)
    elif kind == "arrow":
        a = min(1.0, t_local / 0.2)
        extra = ARROW_OVERSHOOT * math.sin(min(1.0, t_local / 0.15)
                                           * math.pi)
        ov, pos = _render_arrow(tuple(spec["from"]), tuple(spec["to"]),
                                extra)
    else:
        raise ValueError(kind)
    if t_local > dur - FADE_OUT:
        a = min(a, max(0.0, (dur - t_local) / FADE_OUT))
    if a <= 0.0:
        return frame_rgb
    ov = _alpha_mult(ov, a)
    frame_rgb.paste(ov, pos, ov)
    return frame_rgb


def compose_scene(frame_rgb: Image.Image, specs: list,
                  t_scene: float) -> Image.Image:
    """Aplica los overlays activos de la escena en t_scene (s desde el
    inicio de la narración de la escena). specs ya normalizadas."""
    for spec in specs:
        tl = t_scene - spec["at"]
        if 0.0 <= tl <= spec["dur"]:
            compose(frame_rgb, spec, tl)
    return frame_rgb


def momentos_num(specs: list) -> list:
    """Instantes `at` de los overlays numéricos (para SFX pop)."""
    return [s["at"] for s in specs if s["t"] == "num"]


# --- specs desde el guion (H2: JSON serializable, sin módulos por tema) -------
_HINT_MIN_WORDS = 1
_HINT_MAX_WORDS = 6


def specs_from_script(script: dict, *, max_per_minute: float = 2.0) -> dict:
    """Deriva specs JSON de overlays desde el guion (overlay_hint).

    Regla del nicho (skill stickman-documental, contract v2): máx ~1-2
    overlays de énfasis por minuto; el `at` se ancla por densidad de
    palabras (sin word timings live: proporcional, citable). Una escena
    sin overlay_hint = escena de descanso ([]), 1 de cada ~4.
    """
    scenes = list(script.get("scenes") or [])
    out: dict = {}
    for idx, sc in enumerate(scenes):
        sid = sc.get("id", f"scene-{idx}")
        hint = (sc.get("overlay_hint") or "").strip()
        vo = sc.get("voiceover") or ""
        n_words = len([p for p in vo.split() if p])
        if not hint or not n_words:
            out[sid] = []
            continue
        words = hint.split()
        if not (_HINT_MIN_WORDS <= len(words) <= _HINT_MAX_WORDS):
            raise ValueError(
                f"{sid}: overlay_hint fuera de contrato ({len(words)} "
                f"palabras, 1-{_HINT_MAX_WORDS})")
        # anclaje proporcional: 25% del narration span (sin timings live)
        at = round(n_words * 0.25, 2)
        pos = "top" if len(words) <= 3 else "bot"
        text = _WS.sub(" ", " ".join(w.upper() for w in words))
        kind = "num" if any(ch.isdigit() for ch in hint) else "card"
        spec = {"t": kind, "at": at, "pos": pos,
                "l1" if kind == "card" else "txt": text}
        out[sid] = [normalize_spec(spec)]
    return out
