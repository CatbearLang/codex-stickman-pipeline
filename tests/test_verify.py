"""tests/test_verify.py — F8 RED: verify + thumbnail + status.

verify(mp4, cfg) -> (ok, reporte): integridad técnica REAL con ffmpeg/ffprobe
(decode completo, resolución, duración vs esperada ±1 s, loudness -14 LUFS ±2,
true peak <= -1 dBFS con ebur128). Sin red; fixtures locales sintéticos.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from stickman import verify as V
from stickman import thumbnailx as TH


def _sine_wav(path: Path, dur: float = 1.0, freq: int = 440) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={dur:.3f}",
         "-ar", "48000", "-ac", "2", str(path)],
        check=True, capture_output=True)


def _mp4(path: Path, *, dur: float = 1.0, w: int = 1920, h: int = 1080,
         loud: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc=size={w}x{h}:rate=30:duration={dur:.3f}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur:.3f}",
         "-filter_complex", f"[1:a]volume=8dB[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset",
         "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", str(path)],
        check=True, capture_output=True)


def test_mp4_corrupto_falla_decode(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"no es un mp4" * 100)
    ok, rep = V.verify(bad, expected_duration_s=1.0)
    assert ok is False
    assert rep["checks"]["decode"]["ok"] is False
    assert "motivo" in rep["checks"]["decode"]


def test_resolucion_mala_falla_citable(tmp_path):
    p = tmp_path / "small.mp4"
    _mp4(p, w=640, h=360)
    ok, rep = V.verify(p, expected_duration_s=1.0, width=1920, height=1080)
    assert ok is False
    assert rep["checks"]["resolution"]["ok"] is False
    assert "640" in json.dumps(rep["checks"]["resolution"])


def test_duracion_fuera_de_tolerancia_falla(tmp_path):
    p = tmp_path / "short.mp4"
    _mp4(p, dur=1.0)
    ok, rep = V.verify(p, expected_duration_s=10.0)  # ±1 s
    assert ok is False
    assert rep["checks"]["duration"]["ok"] is False


def test_loudness_y_true_peak_mp4_sintetico(tmp_path):
    p = tmp_path / "loud.mp4"
    _mp4(p, dur=1.0, loud=True)
    ok, rep = V.verify(p, expected_duration_s=1.0)
    assert rep["checks"]["loudness"]["ok"] is True, rep["checks"]["loudness"]
    assert rep["checks"]["true_peak"]["ok"] is True
    assert ok is True


def test_thumbnail_exige_from_image(tmp_path):
    with pytest.raises(ValueError):
        TH.make_thumbnail(src=None, out=tmp_path / "thumb.png")


def test_thumbnail_desde_imagen_original(tmp_path):
    src = tmp_path / "still.png"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "testsrc=size=1536x1024:rate=1", "-frames:v", "1",
         str(src)], check=True, capture_output=True)
    out = tmp_path / "thumb.png"
    p = TH.make_thumbnail(src=src, out=out, hook="WOW")
    assert Path(p).exists()
    assert Path(p).suffix == ".png"
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=width,height", "-of", "json", str(p)],
                       capture_output=True, text=True)
    dims = json.loads(r.stdout)["streams"][0]
    assert int(dims["width"]) == 1280 and int(dims["height"]) == 720


def test_status_json_reporta_etapas(tmp_path, capsys):
    from stickman.cli import main
    proj = tmp_path / "proyecto con espacios"
    proj.mkdir()
    (proj / "stickman.toml").write_text(
        '[script]\nprovider = "local-advanced"\n', encoding="utf-8")
    (proj / ".stickman").mkdir()
    rc = main(["status", "--project", str(proj), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "stages" in data
