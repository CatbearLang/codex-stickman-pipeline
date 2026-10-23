"""Schema de guion `docu-en-1` (plan §4.5).

Portado del canónico `sol_script.py:validate_docu_en_1` (origen solo
lectura): misma semántica de aceptación/rechazo y mismos mensajes
descriptivos, pero retorna lista de errores citables (`[]` = válido)
en vez de raise, para que el CLI y los providers los muestren sin
try/except en cada llamada.
"""
from __future__ import annotations

import re
import math

from stickman.stills.runner import (
    MAX_IMAGE_CALLS_PER_VIDEO, MAX_IMAGE_CALLS_TWO_RUNS)

SCHEMA_VERSION = "docu-en-1"


def _norm_w(text: str) -> list:
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)*", (text or "").lower())


def validate_docu_en_1(script: dict) -> list[str]:
    """Valida schema docu-en-1. Retorna errores citables; [] = válido."""
    errs: list[str] = []
    if not isinstance(script, dict):
        return ["script no es objeto"]
    for field in ("title", "language"):
        if not isinstance(script.get(field),str) or not script[field].strip():
            return [f"{field} must be a nonempty string"]
    scenes = script.get("scenes")
    if not isinstance(scenes,list) or not scenes or not all(isinstance(x,dict) for x in scenes):
        return ["scenes must be a nonempty array of objects"]
    for sc in scenes:
        if not isinstance(sc.get("id"), str) or not isinstance(sc.get("voiceover"),str):
            return ["scene id and voiceover must be strings"]
        if not isinstance(sc.get("concepts"),list) or not sc["concepts"]:
            return ["each scene requires concepts"]
        for c in sc["concepts"]:
            if not isinstance(c,dict) or not all(isinstance(c.get(k),str) for k in ("id","anchor","narration_span")):
                return ["concept id, anchor and narration_span must be strings"]
            if not re.fullmatch(r"[a-z][a-z0-9_]*",c["id"]):
                return ["concept id must be a safe snake_case identifier"]
    ids = [s.get("id") for s in scenes]
    if len(set(ids)) != len(ids):
        errs.append(f"scene ids duplicados: {ids}")
    global_concept_ids: set = set()
    for s in scenes:
        sid = s.get("id", "?")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", sid or ""):
            errs.append(f"scene id no snake_case: {sid!r}")
        vo = (s.get("voiceover") or "").strip()
        if not vo:
            errs.append(f"{sid}: voiceover vacío")
        vo_words = _norm_w(vo)
        anchors = [c.get("anchor") for c in s.get("concepts", [])]
        if len(set(anchors)) != len(anchors):
            errs.append(f"{sid}: anchors duplicados: {anchors}")
        spans = [c.get("narration_span", "") for c in s.get("concepts", [])]
        if spans:
            joined = _norm_w(" ".join(spans))
            if joined != vo_words:
                errs.append(
                    f"{sid}: narration_spans no teselan el voiceover "
                    f"(span_words={len(joined)} vo_words={len(vo_words)})")
        for c in s.get("concepts", []):
            for k in ("id", "anchor", "narration_span"):
                if not (c.get(k) or "").strip():
                    errs.append(f"{sid}/{c.get('id')}: falta {k}")
            cid = c.get("id")
            if cid in global_concept_ids:
                errs.append(f"concept id global duplicado: {cid}")
            global_concept_ids.add(cid)
    return errs


def validate_pacing(script: dict, target_minutes: float) -> list[str]:
    """Check generated narration and image density before paid media stages.

    Producto 5-6 min (t_dbdbc827): para target >= 5 el video real debe durar
    300-360 s medidos; a 145 WPM eso son 725-870 palabras y como maximo 36
    conceptos (1 llamada Codex por concepto; tope duro 36/video, 72/dos
    corridas). Fallar cerrado: jamas truncar narracion ni bajar densidad.
    """
    if target_minutes <= 0:
        return ["target_minutes must be positive"]
    scenes = script.get("scenes") or []
    words = sum(len(_norm_w(s.get("voiceover", ""))) for s in scenes)
    concepts = [c for s in scenes for c in s.get("concepts", [])]
    if target_minutes >= 5:
        # Ventana estricta 5-6 min reales (no basta target=5.5 con 4.5-6.5).
        min_words = 5 * 145  # 725
        max_words = 6 * 145  # 870
    else:
        # At 145 WPM, the 5.5-minute standard target keeps a +/-1 minute editorial window (4.5-6.5).
        margin = 1.0 if target_minutes >= 5 else max(0.15, target_minutes * 0.20)
        min_words = math.ceil(max(0, target_minutes - margin) * 145)
        max_words = math.floor((target_minutes + margin) * 145)
    errors = []
    if not min_words <= words <= max_words:
        errors.append(f"Narration has {words} words; target {min_words}-{max_words} words for {target_minutes:g} minutes at 145 WPM")
    if len(concepts) > MAX_IMAGE_CALLS_PER_VIDEO:
        errors.append(
            f"Script has {len(concepts)} image concepts; hard cap is "
            f"{MAX_IMAGE_CALLS_PER_VIDEO} per video "
            f"({MAX_IMAGE_CALLS_TWO_RUNS} for two runs). Reduce concepts "
            f"without truncating narration or lowering density.")
    min_images = math.ceil(words / 29) if words else 0  # about 12 seconds/image
    if len(concepts) < min_images:
        errors.append(f"Script has {len(concepts)} images; at least {min_images} are needed for {words} words (one per ~12 seconds)")
    for scene in scenes:
        for concept in scene.get("concepts", []):
            span_words = len(_norm_w(concept.get("narration_span", "")))
            if span_words > 29:
                errors.append(f"{concept.get('id', '?')}: narration_span has {span_words} words; maximum is 29")
    return errors
