"""Preflight local de duración (portado de tts_duration_preflight.py).

Estima audio por s/palabra medido, gate PASS/WARN/BLOCK, nunca recorta
el guion. Los perfiles de voz medidos no se incluyen: el
proyecto trae perfiles vacíos + `stickman calibrate` para medir local.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

WORD_RE = re.compile(r"\b[\w’'-]+\b", re.UNICODE)


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def first_scene_repeats_title(script: dict[str, Any]) -> bool:
    title_words = [w.casefold() for w in WORD_RE.findall(script.get("title", ""))]
    scenes = script.get("scenes", [])
    if not title_words or not scenes:
        return False
    first = [w.casefold()
             for w in WORD_RE.findall(scenes[0].get("voiceover", ""))]
    return first[:len(title_words)] == title_words


def estimate(script: dict[str, Any], profile: dict[str, Any], speed: float,
             target_min_s: float | None = None,
             target_max_s: float | None = None,
             measured: bool = True) -> dict[str, Any]:
    observations = profile.get("observations", [])
    if not observations:
        raise ValueError("duration profile has no observations")
    if speed <= 0:
        raise ValueError("speed must be positive")
    scene_words = sum(word_count(s.get("voiceover", ""))
                      for s in script.get("scenes", []))
    title_words = word_count(script.get("title", ""))
    if scene_words <= 0:
        raise ValueError("script has no narrated scene words")
    scene_rates, title_rates = [], []
    for obs in observations:
        hist_speed = float(obs["speed"])
        sw = int(obs["scene_words"])
        if sw > 0:
            scene_rates.append((float(obs["scene_audio_s"]) / sw)
                               * hist_speed / speed)
        tw = int(obs.get("title_words", 0))
        if tw > 0:
            title_rates.append((float(obs["title_audio_s"]) / tw)
                               * hist_speed / speed)
    if not scene_rates:
        raise ValueError("duration profile has no usable scene observations")
    scene_rate = sum(scene_rates) / len(scene_rates)
    title_rate = (sum(title_rates) / len(title_rates) if title_rates
                  else scene_rate)
    estimate_s = scene_words * scene_rate + title_words * title_rate
    low_s = (scene_words * min(scene_rates)
             + title_words * min(title_rates or scene_rates))
    high_s = (scene_words * max(scene_rates)
              + title_words * max(title_rates or scene_rates))
    gate, reason = "PASS", "estimated interval compatible with target"
    if target_min_s is not None and high_s < target_min_s:
        gate, reason = "BLOCK", "estimate shorter than target"
    elif target_max_s is not None and low_s > target_max_s:
        gate, reason = "BLOCK", "estimate longer than target"
    elif ((target_min_s is not None and estimate_s < target_min_s)
          or (target_max_s is not None and estimate_s > target_max_s)):
        gate, reason = "WARN", "point estimate outside target"
    if first_scene_repeats_title(script):
        gate, reason = "BLOCK", "first scene repeats the spoken title"
    method = ("measured_seconds_per_word_adjusted_by_configured_speed"
              if measured else
              "estimated_seconds_per_word_local_seed")
    return {"schema_version": 1,
            "method": method,
            "estimated": not measured,
            "scene_words_observed": scene_words,
            "title_words_observed": title_words,
            "word_budget_enforced": False, "script_modified": False,
            "title_repeat_detected": first_scene_repeats_title(script),
            "configured_speed": speed,
            "observations_used": len(observations),
            "estimated_total_s": round(estimate_s, 2),
            "estimated_interval_s": [round(low_s, 2), round(high_s, 2)],
            "target_interval_s": [target_min_s, target_max_s],
            "gate": gate, "reason": reason}


def run_preflight(script_path: Path, profiles_path: Path, profile_name: str,
                  speed: float, report_path: Path,
                  target_min_s: float | None = None,
                  target_max_s: float | None = None) -> dict[str, Any]:
    script = json.loads(Path(script_path).read_text(encoding="utf-8"))
    profiles = json.loads(
        Path(profiles_path).read_text(encoding="utf-8"))["profiles"]
    if profile_name not in profiles:
        raise KeyError(f"unknown duration profile: {profile_name}")
    report = estimate(script, profiles[profile_name], speed,
                      target_min_s, target_max_s)
    report.update({"script": str(script_path), "profile": profile_name})
    Path(report_path).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return report
