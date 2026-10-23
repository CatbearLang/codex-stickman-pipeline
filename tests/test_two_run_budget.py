"""Rework t_86fd4402 (offline, sin Codex live): presupuesto real 36/video y 72/dos.

TDD RED->GREEN contra el gate NO PASS t_b8de29b6:
- el preflight estima intentos REALES con la reserva efectiva (clamp 36);
- `reserve_regen` nunca eleva llamadas sobre 36 (hard_limit/effective_limit);
- el ledger durable acumula consumo ENTRE proyectos/corridas hacia 72;
- el resume tras fallo no reemite successful ni evade el tope;
- todo por el camino CLI real (`run --stage stills`), no mero helper.
Sin reintentos automaticos: cada intento cuenta ANTES del exec, incluso fallido.
"""
import json
import os
from pathlib import Path

import pytest
from PIL import Image

from stickman.cli import main
from stickman.config import config_set
from stickman.errors import ProviderError
from stickman.stills import runner as R
import stickman.stills.factory as imf


def _doc(n, tag):
    scenes = []
    k = 0
    si = 0
    while k < n:
        take = min(2, n - k)
        vo = []
        cons = []
        for j in range(k, k + take):
            w = f"alpha{j} beta{j}"
            vo.append(w)
            cons.append({"id": f"{tag}c{j:02d}",
                         "anchor": f"{tag}a{j:02d}",
                         "narration_span": w})
        scenes.append({"id": f"s{si + 1:02d}",
                       "voiceover": " ".join(vo), "visual": "v",
                       "anchor": f"sanchor{si}", "concepts": cons})
        si += 1
        k += take
    return {"title": f"T {tag}", "language": "en",
            "target_minutes": 0.2, "scenes": scenes}


def _init_project(tmp_path, name, tag, n, monkeypatch):
    monkeypatch.setenv("STICKMAN_BUDGET_LEDGER",
                       str(tmp_path / "ledger.json"))
    p = tmp_path / name
    assert main(["init", str(p), "--topic", tag]) == 0
    config_set(p, "render.width", "640")
    config_set(p, "render.height", "360")
    (p / "script.json").write_text(json.dumps(_doc(n, tag)))
    return p


class _Img:
    name = "fail-once"
    model = "m"

    def __init__(self, fail_at=None):
        self.calls = 0
        self.fail_at = fail_at

    def generate(self, prompt, out, **kw):
        self.calls += 1
        if self.fail_at is not None and self.calls == self.fail_at:
            raise ProviderError(f"boom at {self.calls}")
        Image.new("RGB", (320, 180), "white").save(out)
        return {"width": 320, "height": 180}


# --- (2) la reserva nunca eleva llamadas sobre 36 ---------------------------
def test_reserva_no_eleva_sobre_36():
    assert R.effective_limit(30, 8) == 36
    assert R.effective_limit(36, 8) == 36
    assert R.hard_limit(30, 8) == 36
    assert R.hard_limit(36, 8) == 36
    assert R.estimate_calls(30, reserve=8)["per_video_calls"] == 36
    assert R.estimate_calls(30, reserve=8)["two_run_calls"] == 72
    for n in range(0, 37):
        for r in (0, 1, 8, 36):
            est = R.estimate_calls(n, reserve=r)
            assert est["per_video_calls"] <= 36, (n, r, est)
            assert est["two_run_calls"] <= 72, (n, r, est)


def test_preflight_con_reserva_falla_cerrado_antes_de_gastar(tmp_path,
                                                             monkeypatch):
    monkeypatch.setenv("STICKMAN_BUDGET_LEDGER",
                       str(tmp_path / "ledger.json"))
    pre = R.preflight_budget(30, reserve=8, project=tmp_path)
    assert pre["per_video_calls"] == 36
    assert pre["allowed_attempts"] == 36
    with pytest.raises(ValueError, match="36"):
        R.preflight_budget(37, reserve=8, project=tmp_path)


def test_config_rechaza_reserva_mayor_36(tmp_path):
    from stickman import config as cfgmod
    with pytest.raises(cfgmod.ConfigError):
        cfg = cfgmod.default_config()
        cfg["images"]["reserve_regen"] = 100
        cfgmod.validate_config(cfg)


# --- (1)+(3) camino CLI real: resume sin reemision, ledger entre proyectos --
def test_cli_resume_no_reemite_ni_evade_tope(tmp_path, monkeypatch):
    p = _init_project(tmp_path, "projA", "Alpha", 30, monkeypatch)
    fails = _Img(fail_at=15)
    monkeypatch.setattr(imf, "make_image_provider", lambda cfg: fails)
    assert main(["run", "--project", str(p),
                 "--stage", "stills", "--live"]) == 3
    assert fails.calls == 15
    man = json.loads((p / "stills" / "work" / "manifest.json").read_text())
    assert man["attempts"] == 15  # el intento fallido tambien conto
    assert json.loads((tmp_path / "ledger.json").read_text())[
        "consumed_calls"] == 15
    oks = _Img()
    monkeypatch.setattr(imf, "make_image_provider", lambda cfg: oks)
    assert main(["run", "--project", str(p),
                 "--stage", "stills", "--live"]) == 0
    assert oks.calls == 16  # solo las restantes, sin reemitir 14 ok
    man = json.loads((p / "stills" / "work" / "manifest.json").read_text())
    assert man["attempts"] == 31
    assert man["failed"] == []
    assert json.loads((tmp_path / "ledger.json").read_text())[
        "consumed_calls"] == 31


def test_cli_segundo_proyecto_acumula_y_tercero_falla_cerrado(tmp_path,
                                                              monkeypatch):
    pa = _init_project(tmp_path, "projA", "Alpha", 30, monkeypatch)
    monkeypatch.setattr(imf, "make_image_provider", lambda cfg: _Img())
    assert main(["run", "--project", str(pa),
                 "--stage", "stills", "--live"]) == 0
    assert json.loads((tmp_path / "ledger.json").read_text())[
        "consumed_calls"] == 30
    pb = _init_project(tmp_path, "projB", "Beta", 30, monkeypatch)
    monkeypatch.setattr(imf, "make_image_provider", lambda cfg: _Img())
    assert main(["run", "--project", str(pb),
                 "--stage", "stills", "--live"]) == 0
    assert json.loads((tmp_path / "ledger.json").read_text())[
        "consumed_calls"] == 60
    # Tercer video por CLI real: el preflight del pipeline debe fallar
    # cerrado ANTES de gastar (60 + 30 > 72).
    with pytest.raises(ProviderError, match="cuota no disponible"):
        R.preflight_budget(30, reserve=0, project=pb)
    with pytest.raises(ProviderError, match="cuota no disponible"):
        R.preflight_budget(30, reserve=8, project=pb)


def test_cli_estima_con_reserva_efectiva_antes_de_gastar(tmp_path,
                                                         monkeypatch):
    p = _init_project(tmp_path, "projC", "Gamma", 30, monkeypatch)
    config_set(p, "images.reserve_regen", "8")
    pre = R.preflight_budget(
        30, reserve=8, project=p)
    assert pre["per_video_calls"] == 36  # 30 + 8 recortado a 36, no 38
    assert pre["consumed_before"] == 0
