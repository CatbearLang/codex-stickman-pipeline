"""Gates previos a gasto (plan §4.5 + F2).

Puertas: `slideshow_gate != fail` y `variation_check != fail`.
Portados del canónico (origen solo lectura):
- slideshow_gate.py: score_plan/score_scene/verdict_for (verbatim lógica).
- variation_check.py: check_prompts, TWIN_THRESHOLD=0.75 (verbatim lógica).
"""
from __future__ import annotations

import difflib
import re

_WORD = re.compile(r"[a-z0-9]+")

DIMENSIONS = (
    "repeticion",
    "decorativos",
    "motion_debil",
    "intencion_debil",
    "tipografia",
    "claims_sin_soporte",
)

_DECORATIVOS = {
    "beautiful", "stunning", "gorgeous", "breathtaking", "vibrant", "colorful",
    "decorative", "ornamental", "amazing", "incredible", "spectacular",
    "picturesque", "majestic", "glorious", "lovely", "pretty", "nice",
    "awesome", "fantastic", "wonderful", "exquisite",
}

_VAGAS = {
    "something", "stuff", "things", "various", "generic", "somehow",
    "someone", "somewhere", "very", "really", "just", "quite", "rather",
    "general", "normal", "usual", "typical", "random",
}

_MOTION = {
    "run", "runs", "running", "jump", "jumps", "fly", "flies", "flying",
    "spin", "spins", "fall", "falls", "falling", "rise", "rises", "rising",
    "draw", "draws", "drawing", "brush", "brushes", "brushing", "twitch",
    "twitches", "twitching", "wiggle", "wiggles", "wiggling", "laugh",
    "laughs", "laughing", "squeak", "squeaks", "tickle", "tickles",
    "tickling", "tickled", "drift", "drifts", "drifting", "float", "floats",
    "floating", "punch", "punches", "flinch", "flinches", "flinching",
    "shake", "shakes", "shaking", "wave", "waves", "waving", "point",
    "points", "pointing", "pour", "pours", "pouring", "build", "builds",
    "building", "walk", "walks", "walking", "dance", "dances", "climb",
    "climbs", "dig", "digs", "dive", "dives", "diving", "sail", "sails",
    "drive", "drives", "driving", "explode", "explodes", "burst", "bursts",
    "slide", "slides", "sliding", "swing", "swings", "swinging", "march",
    "marches", "chase", "chases", "chasing", "grab", "grabs", "grabbing",
    "lift", "lifts", "lifting", "drop", "drops", "dropping", "splash",
    "splashes", "erupt", "erupts", "crack", "cracks",
}

_CLAIMS = {
    "best", "greatest", "largest", "biggest", "fastest", "richest",
    "oldest", "newest", "tallest", "first", "only", "always", "never",
    "everyone", "nobody", "proven", "proves", "guarantee", "guaranteed",
    "impossible", "undeniable", "revolutionary", "miraculous",
}


def _tokens(text: str) -> list:
    return _WORD.findall((text or "").lower())


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _overlay_text(scene: dict) -> str:
    ov = scene.get("overlay")
    if isinstance(ov, (list, tuple)) and len(ov) > 1 and isinstance(ov[1], str):
        return ov[1]
    if isinstance(ov, str):
        return ov
    return ""


def _score_scene(scene: dict, others: list) -> dict:
    visual = scene.get("visual") or ""
    anchor = scene.get("anchor") or ""
    action = scene.get("action") or ""
    shot = scene.get("shot") or ""
    voiceover = scene.get("voiceover") or ""

    mine = set(_tokens(f"{visual} {anchor}"))
    rep = max([_jaccard(mine, set(_tokens(o))) for o in others] or [0.0])
    repeticion = round(min(5.0, 5.0 * rep), 3)

    n_dec = sum(1 for t in _tokens(f"{visual} {anchor}") if t in _DECORATIVOS)
    decorativos = round(min(5.0, 2.0 * n_dec), 3)

    n_mot = sum(1 for t in _tokens(f"{visual} {action}") if t in _MOTION)
    motion_debil = round(min(5.0, 4.0 if n_mot == 0
                             else max(0.0, 2.0 - 0.5 * n_mot)), 3)
    if not (isinstance(action, str) and action.strip()):
        motion_debil = round(min(5.0, motion_debil + 1.0), 3)

    n_vag = sum(1 for t in _tokens(f"{visual} {anchor} {action}")
                if t in _VAGAS)
    intencion_debil = round(min(5.0, 1.5 * n_vag
                                + (0.0 if shot and str(shot).strip() else 1.0)), 3)

    n_pal = len(_overlay_text(scene).split())
    if n_pal == 0:
        tipografia = 1.0
    elif n_pal <= 3:
        tipografia = 0.0
    elif n_pal <= 6:
        tipografia = 2.0
    else:
        tipografia = 4.0

    n_claim = sum(1 for t in _tokens(voiceover) if t in _CLAIMS)
    claims_sin_soporte = round(min(5.0, 1.2 * n_claim), 3)

    return {
        "repeticion": repeticion,
        "decorativos": decorativos,
        "motion_debil": motion_debil,
        "intencion_debil": intencion_debil,
        "tipografia": tipografia,
        "claims_sin_soporte": claims_sin_soporte,
    }


def _verdict_for(average: float) -> str:
    if average < 2.0:
        return "strong"
    if average < 3.0:
        return "acceptable"
    if average < 4.0:
        return "revise"
    return "fail"


def slideshow_gate(doc: dict) -> tuple[str, float]:
    """(verdict, promedio) sobre doc['scenes']. fail si promedio >= 4.0."""
    scenes = list(doc.get("scenes") or [])
    if not scenes:
        raise ValueError("plan sin escenas")
    pares = [f"{s.get('visual', '')} {s.get('anchor', '')}" for s in scenes]
    totales = []
    for i, sc in enumerate(scenes):
        sides = _score_scene(sc, pares[:i] + pares[i + 1:])
        totales.append(sum(sides[d] for d in DIMENSIONS) / len(DIMENSIONS))
    avg = round(sum(totales) / len(totales), 3)
    return _verdict_for(avg), avg


TWIN_THRESHOLD = 0.75

GENERIC_PHRASES = [
    "breathtaking", "stunning", "jaw-dropping", "awe-inspiring",
    "masterpiece", "highly detailed", "ultra detailed", "intricate details",
    "rich details", "vibrant colors", "dynamic composition",
    "cinematic lighting", "dramatic lighting", "visually striking",
    "beautiful scene", "amazing", "gorgeous", "epic",
]

_WS = re.compile(r"\s+")

_ANCHOR_ALIASES = {
    "forecast pin": "forecast marker",
    "prediction pin": "forecast marker",
    "prediction marker": "forecast marker",
}


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").lower()).strip()


def _as_items(prompts) -> list:
    if isinstance(prompts, dict):
        seq = prompts.items()
    else:
        seq = [(p.get("scene_id", f"scene-{i}") if isinstance(p, dict)
                else f"scene-{i}", p) for i, p in enumerate(prompts)]
    items = []
    for sid, p in seq:
        if isinstance(p, dict):
            visual = p.get("semantic_visual", p.get("visual", ""))
            anchor = p.get("anchor", "")
            action = p.get("action", "")
            text = p.get("prompt", p.get("text", ""))
        else:
            visual, anchor, action, text = str(p), "", "", str(p)
        canonical = _ANCHOR_ALIASES.get(_norm(str(anchor)), _norm(str(anchor)))
        semantic = _norm(f"{visual} {anchor} {action}")
        items.append((str(sid), semantic, _norm(str(text)), canonical))
    return items


def variation_check(prompts) -> tuple[str, list[str]]:
    """(verdict, violaciones). fail si hay gemelos (>=0.75) o genéricos."""
    items = _as_items(prompts)
    violations: list[str] = []
    n = len(items)
    if n == 0:
        return "fail", ["sin prompts que revisar"]
    for i in range(n):
        for j in range(i + 1, n):
            sim = difflib.SequenceMatcher(None, items[i][1],
                                          items[j][1]).ratio()
            same_anchor = bool(items[i][3] and items[i][3] == items[j][3])
            if sim >= TWIN_THRESHOLD or same_anchor:
                violations.append(
                    f"gemelos {items[i][0]} ~ {items[j][0]} "
                    f"(similitud={sim:.2f} >= {TWIN_THRESHOLD}"
                    f"{', anchor equivalente' if same_anchor else ''})")
    for sid, _va, text, _anchor in items:
        for phrase in GENERIC_PHRASES:
            if phrase in text:
                violations.append(f"generico en {sid}: {phrase!r}")
    return ("fail" if violations else "pass"), violations
