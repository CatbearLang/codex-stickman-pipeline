"""stickman/verify.py — integridad técnica REAL del máster (plan F8).

verify(mp4, expected_duration_s, ...) -> (ok, reporte):
  - decode completo real (`ffmpeg -v error -i x -f null -`): cualquier
    error -> check decode fail citable.
  - resolución via ffprobe == esperada.
  - duración ffprobe vs esperada ±1 s (overhang).
  - loudness integrado ebur128 (±2 LU del objetivo -14) y true peak
    <= -1.0 dBTP. ffmpeg real; sin sustitutos.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

DUR_TOL_S = 1.0
LUFS_TARGET = -14.0
LUFS_TOL = 2.0
TP_MAX = -1.0


def _probe_json(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(path)], capture_output=True, text=True,
        timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe falló: {(r.stderr or '')[-300:]}")
    return json.loads(r.stdout)


def _decode_ok(path: Path) -> tuple[bool, str]:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null",
         "-"], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return False, (r.stderr or "decode sin salida")[-400:]
    return True, ""


def _audio_metrics(path: Path) -> tuple[float | None, float | None, str]:
    r = subprocess.run(
        ["ffmpeg", "-nostats", "-i", str(path), "-map", "0:a",
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300)
    text = r.stderr or ""
    lufs = tp = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("I:") and "LUFS" in s:
            try:
                lufs = float(s.split("I:")[1].split("LUFS")[0].strip())
            except ValueError:
                pass
        if s.startswith("Peak:") and "dBFS" in s:
            try:
                tp = float(s.split("Peak:")[1].split("dBFS")[0].strip())
            except ValueError:
                pass
    return lufs, tp, text[-300:] if r.returncode != 0 else ""


def verify(mp4: str | Path, *, expected_duration_s: float | None = None,
           width: int = 1920, height: int = 1080) -> tuple[bool, dict]:
    p = Path(mp4)
    rep: dict = {"schema": 1, "mp4": str(p), "checks": {}, "ok": False}
    ok_all = True
    if not p.exists():
        rep["checks"]["decode"] = {"ok": False, "motivo": "archivo ausente"}
        return False, rep
    # 1) decode completo real
    dec_ok, motivo = _decode_ok(p)
    rep["checks"]["decode"] = {"ok": dec_ok, **({"motivo": motivo}
                                               if motivo else {})}
    ok_all &= dec_ok
    # 2) metadatos ffprobe
    try:
        meta = _probe_json(p)
    except RuntimeError as e:
        rep["checks"]["decode"] = {"ok": False, "motivo": str(e)}
        return False, rep
    vst = next((s for s in meta.get("streams", [])
                if s.get("codec_type") == "video"), None)
    w = int(vst.get("width", 0)) if vst else 0
    h = int(vst.get("height", 0)) if vst else 0
    res_ok = (w, h) == (width, height)
    rep["checks"]["resolution"] = {"ok": res_ok, "got": [w, h],
                                   "expected": [width, height]}
    ok_all &= res_ok
    try:
        dur = float(meta.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        dur = None
    if expected_duration_s is None or dur is None:
        rep["checks"]["duration"] = {"ok": True, "got": dur,
                                     "motivo": "sin expectativa"}
    else:
        d_ok = abs(dur - float(expected_duration_s)) <= DUR_TOL_S
        rep["checks"]["duration"] = {"ok": d_ok, "got": dur,
                                     "expected": float(expected_duration_s),
                                     "tolerance_s": DUR_TOL_S}
        ok_all &= d_ok
    # 3) loudness / true peak (ebur128 real)
    ast = next((s for s in meta.get("streams", [])
                if s.get("codec_type") == "audio"), None)
    if ast is None:
        rep["checks"]["loudness"] = {"ok": False, "motivo": "sin pista de audio"}
        rep["checks"]["true_peak"] = {"ok": False,
                                      "motivo": "sin pista de audio"}
        ok_all = False
    else:
        lufs, tp, err = _audio_metrics(p)
        l_ok = lufs is not None and abs(lufs - LUFS_TARGET) <= LUFS_TOL
        rep["checks"]["loudness"] = {"ok": l_ok, "lufs": lufs,
                                     "target": LUFS_TARGET,
                                     "tolerance": LUFS_TOL}
        t_ok = tp is not None and tp <= TP_MAX + 1e-6
        rep["checks"]["true_peak"] = {"ok": t_ok, "tp_dbfs": tp,
                                      "max": TP_MAX}
        if err:
            rep["checks"]["loudness"]["motivo"] = err
        ok_all &= l_ok and t_ok
    rep["ok"] = ok_all
    return ok_all, rep
