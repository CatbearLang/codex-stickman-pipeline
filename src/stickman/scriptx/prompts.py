"""Bundle de prompts por escena (portado de prompt_gen.py).

STYLE_LOCK/PALETTE/NEGATIVES/SAFE_ZONES byte-idénticos al origen
(verificados por test de paridad). Emite prompts.json + mapping.json
con anchors únicos y filenames sNN_concept.png.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MODEL_REF = "native Codex image generation (or explicitly selected API)"

def _require_str(scene: dict, key: str) -> str:
    value = scene.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"escena {scene.get('id', '?')!r} sin {key!r}")
    return value.strip()


def _concepts_of(scene: dict) -> list[dict]:
    """Conceptos de una escena: usa concepts[] o 1 concepto por escena."""
    concepts = scene.get("concepts") or []
    if concepts:
        return concepts
    return [{"id": f"{scene['id']}-c1", "anchor": scene.get("anchor", "")}]


def build_bundle(script: dict[str, Any], out_dir: str | Path) -> dict:
    """Genera prompts.json + mapping.json. Retorna rutas relativas."""
    scenes = script.get("scenes") or []
    if not scenes:
        raise ValueError("script sin escenas")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prompts: dict = {}
    concepts: dict = {}
    seen_anchors: set[str] = set()
    for i, scene in enumerate(scenes, start=1):
        scene_id = _require_str(scene, "id")
        prompt = ""
        for concept in _concepts_of(scene):
            cid = concept.get("id") or f"{scene_id}-c1"
            anchor = concept.get("anchor") or scene.get("anchor", "")
            if anchor in seen_anchors:
                raise ValueError(f"anchor duplicado en bundle: {anchor!r}")
            seen_anchors.add(anchor)
            filename = f"s{i:02d}_{cid}.png"
            from .style import build_concept_prompt
            subject = concept.get("subject") or scene.get("subject") or "object"
            semantic = {"subject": subject, "visible_action": concept.get("visible_action") or scene.get("action", "shown"), "object": concept.get("object") or anchor, "spatial_relation": concept.get("spatial_relation", "center"), "composition": concept.get("composition", "wide"), "semantic_visual": concept.get("semantic_visual") or scene.get("visual", ""), **concept}
            prompt = build_concept_prompt(semantic, scene, len(prompts) + 1)
            prompts[cid] = {"scene_id": scene_id, "index": i,
                            "prompt": prompt, "anchor": anchor,
                            "visual": scene.get("visual", ""),
                            "model": MODEL_REF}
            concepts[cid] = {"scene": i, "scene_id": scene_id,
                             "anchor": anchor, "filename": filename,
                             "prompt_sha256": hashlib.sha256(
                                 prompt.encode()).hexdigest()[:16]}
    (out / "prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    (out / "mapping.json").write_text(
        json.dumps({"expected_images": len(concepts),
                    "concepts": concepts},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"prompts_path": "prompts.json", "mapping_path": "mapping.json"}
