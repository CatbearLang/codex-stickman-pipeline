"""TDD RED: gates de cierre 5-6 min reales + cuota Codex (t_dbdbc827).

Falla en rojo antes del fix; en verde tras el fix. Offline, sin Codex live.
"""
import json

from stickman.scriptx.schema import validate_pacing
from stickman.pipeline import _check_generated_voice_duration


def _script(words_total, concepts):
    # reparte palabras en conceptos con spans <=29 palabras
    per = max(1, words_total // concepts)
    chunks = []
    rest = words_total
    for i in range(concepts):
        n = per if i < concepts - 1 else rest
        n = min(n, 29)
        chunks.append(" ".join(["word"] * n))
        rest -= n
    return {"scenes": [{"voiceover": " ".join(chunks),
                        "concepts": [{"id": f"c{i}", "narration_span": ch}
                                     for i, ch in enumerate(chunks)]}]}


def _voice_dir(tmp_path, total_s):
    voice = tmp_path / "voice"
    voice.mkdir(exist_ok=True)
    (voice / "meta.json").write_text(json.dumps({"s01": {"duration_s": total_s}}))
    return tmp_path


def _cfg(target):
    return {"project": {"target_minutes": target},
            "script": {"provider": "codex-oauth"}}


def test_medida_270s_falla_para_target_5_5(tmp_path):
    # 4.5 min medidos NO bastan para el estandar 5-6 aunque target+-1 lo permitia
    import pytest
    with pytest.raises(RuntimeError, match="Measured narration|300|360"):
        _check_generated_voice_duration(_voice_dir(tmp_path, 270), _cfg(5.5))


def test_medida_ventana_estricta_300_360(tmp_path):
    import pytest
    _check_generated_voice_duration(_voice_dir(tmp_path, 300), _cfg(5.5))
    _check_generated_voice_duration(_voice_dir(tmp_path, 360), _cfg(5.5))
    for bad in (299, 361):
        d = tmp_path / f"v{bad}"
        d.mkdir(exist_ok=True)
        (d / "voice").mkdir(exist_ok=True)
        ((d / "voice") / "meta.json").write_text(
            json.dumps({"s01": {"duration_s": bad}}))
        with pytest.raises(RuntimeError):
            _check_generated_voice_duration(d, _cfg(5.5))


def test_pacing_660_palabras_falla_para_5_5():
    # ~4.5 min estimados no bastan para 5.5 (ventana vieja 653-942 lo pasaba)
    errs = validate_pacing(_script(660, 24), 5.5)
    assert any("Narration" in e for e in errs), errs


def test_pacing_ventana_5_6_ok():
    assert validate_pacing(_script(800, 30), 5.5) == []


def test_mas_de_36_conceptos_falla_cerrado():
    errs = validate_pacing(_script(800, 37), 5.5)
    assert any("36" in e or "concept" in e.lower() or "image" in e.lower()
               for e in errs), errs


def test_tope_duro_36_por_video_y_72_dos_corridas():
    from stickman.stills.runner import (
        MAX_IMAGE_CALLS_PER_VIDEO, MAX_IMAGE_CALLS_TWO_RUNS)
    assert MAX_IMAGE_CALLS_PER_VIDEO == 36
    assert MAX_IMAGE_CALLS_TWO_RUNS == 72
    assert MAX_IMAGE_CALLS_PER_VIDEO * 2 <= MAX_IMAGE_CALLS_TWO_RUNS


def test_estimacion_llamadas_dos_corridas():
    from stickman.stills.runner import estimate_calls
    rep = estimate_calls(30)
    assert rep["per_video_calls"] == 30
    assert rep["two_run_calls"] == 60
    assert rep["two_run_calls"] <= 72
    import pytest
    with pytest.raises(ValueError, match="36"):
        estimate_calls(37)


def test_estimacion_con_reserva_no_supera_36():
    # Rework t_86fd4402: la reserva NUNCA eleva llamadas sobre el tope.
    from stickman.stills.runner import estimate_calls
    rep = estimate_calls(30, reserve=8)
    assert rep["per_video_calls"] == 36
    assert rep["two_run_calls"] == 72
    assert estimate_calls(36, reserve=8)["per_video_calls"] == 36
