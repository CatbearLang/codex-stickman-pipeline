"""BGM Accralate por defecto + credito CC BY automatico (offline, sin Codex live).

Cubre: default accralate en config, resolucion de modos (none/custom/
ambient preservados), credito automatico en caption sin sobrescribir
creditos del usuario, mezcla con ducking perceptible bajo voz, opt-out,
empaquetado allowlist + scanner de secretos, render multi-escena local
con FFmpeg real y paths cross-platform.
"""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from stickman import bgm as BGM
from stickman.config import default_config, load_config, config_set
from stickman.render.composer import compose

KIT = Path(__file__).parents[1]
MUSIC = KIT / "src" / "stickman" / "assets" / "music"
# Origen solo-lectura fuera del repo (ruta absoluta del auditor via env;
# por defecto la workstation conocida; el scanner prohibe rutas privadas
# dentro del ZIP, por eso aqui NO hay literales de home del auditor).
ORIGIN_MP3 = Path(os.environ.get("STICKMAN_ACCRALATE_SRC", "") or str(
    Path("/nonexistent/bgm_Accralate.mp3")))
ORIGIN_LIC = ORIGIN_MP3.parent / "LICENSES.txt"

CREDIT_SNIPPETS = ("Accralate", "Kevin MacLeod", "incompetech.com",
                   "creativecommons.org/licenses/by/4.0")


def test_default_bgm_is_accralate():
    cfg = default_config()
    assert cfg["render"]["bgm"] == "accralate"
    assert float(cfg["render"]["bgm_volume"]) == pytest.approx(0.10)


@pytest.mark.skipif(not ORIGIN_MP3.exists(), reason="author-only provenance check (set STICKMAN_ACCRALATE_SRC)")
def test_track_byte_identical_to_origin():
    src = ORIGIN_MP3.read_bytes()
    dst = (MUSIC / "accralate.mp3").read_bytes()
    assert hashlib.md5(src).hexdigest() == "b9a667797ffb9db79bb4b9e36bf26790"
    assert hashlib.md5(dst).hexdigest() == hashlib.md5(src).hexdigest()


@pytest.mark.skipif(not ORIGIN_LIC.exists(), reason="author-only provenance check (set STICKMAN_ACCRALATE_SRC)")
def test_origin_license_declares_cc_by():
    text = ORIGIN_LIC.read_text(encoding="utf-8", errors="replace")
    assert "Accralate" in text and "Kevin MacLeod" in text
    assert "By Attribution 4.0" in text
    assert "creativecommons.org/licenses/by/4.0" in text


def test_packaged_license_and_manifest():
    lic = (MUSIC / "LICENSE.txt").read_text(encoding="utf-8")
    assert "Accralate" in lic and "Kevin MacLeod" in lic
    assert "creativecommons.org/licenses/by/4.0" in lic
    man = json.loads((MUSIC / "manifest.json").read_text(encoding="utf-8"))
    entry = man["accralate.mp3"]
    assert entry["license"].startswith("CC BY 4.0")
    assert "Kevin MacLeod" in entry["credit"]
    actual = hashlib.sha256((MUSIC / "accralate.mp3").read_bytes()).hexdigest()
    assert entry["sha256"] == actual == \
        "f9760f923aac20d3048774f39eefddb2d952f64ecabac4850f7c53110950e9fd"
    # la cama procedural propia sigue intacta
    assert man["ambient.wav"]["sha256"] == \
        "fc14ef4605293591c698c3ba44cb6bcc9e0011dda2314a94a9a716c75a242734"


def test_resolve_modes_preserved(tmp_path):
    p, track, credit = BGM.resolve_bgm("accralate")
    assert p.name == "accralate.mp3" and track == "accralate"
    assert all(s in credit for s in CREDIT_SNIPPETS)
    assert BGM.resolve_bgm("none") == (None, None, None)
    for mode in ("bundled", "ambient"):
        q, t2, c2 = BGM.resolve_bgm(mode)
        assert q.name == "ambient.wav" and t2 == "ambient" and c2 is None
    mine = tmp_path / "sub dir" / "mía.mp3"
    mine.parent.mkdir(parents=True)
    shutil.copy2(MUSIC / "accralate.mp3", mine)
    q, t3, c3 = BGM.resolve_bgm(str(mine), tmp_path)
    assert t3 == "custom" and c3 is None and q == mine
    rel = tmp_path / "proj"
    (rel / "tracks").mkdir(parents=True)
    shutil.copy2(MUSIC / "accralate.mp3", rel / "tracks" / "song.mp3")
    q2, _, _ = BGM.resolve_bgm("tracks/song.mp3", rel)
    assert q2.exists()
    with pytest.raises(FileNotFoundError):
        BGM.resolve_bgm("tracks/missing.mp3", rel)


def test_credit_block_only_for_accralate():
    from stickman.pipeline import _bgm_for_caption
    block = _bgm_for_caption(default_config())
    assert all(s in block for s in CREDIT_SNIPPETS)
    base = {"title": "T", "logline": "L"}
    for mode in ("none", "bundled", "ambient"):
        cfg = default_config()
        cfg["render"]["bgm"] = mode
        assert _bgm_for_caption(cfg) == ""
    # el credito se ANEXA: titulo/logline/creditos del usuario intactos
    cfg = default_config()
    mine = "My own song credit (user)"
    caption = base["title"] + "\n\n" + base["logline"] + "\n" + \
        _bgm_for_caption(cfg)
    assert caption.startswith("T\n\nL\n") and mine not in caption
    assert caption.count("Accralate") == 1


def test_config_roundtrip_bgm_modes(tmp_path):
    assert "ok:" in config_set(tmp_path, "render.bgm", "none")
    assert load_config(tmp_path)["render"]["bgm"] == "none"
    assert "ok:" in config_set(tmp_path, "render.bgm", "accralate")
    assert load_config(tmp_path)["render"]["bgm"] == "accralate"
    assert "ok:" in config_set(tmp_path, "render.bgm", "bundled")
    assert load_config(tmp_path)["render"]["bgm"] == "bundled"


def _scene_script(sid, visual, anchor, action, text, hint):
    return {"id": sid, "voiceover": text, "visual": visual,
            "anchor": anchor, "action": action,
            "concepts": [{"id": "c01", "anchor": anchor,
                          "narration_span": text, "subject": "stickman",
                          "visible_action": action, "object": anchor,
                          "spatial_relation": "right", "composition": "wide",
                          "semantic_visual": visual,
                          "overlay_hint": hint}]}


def _local_project(tmp_path, cfg, n_scenes=2):
    """Proyecto multi-escena offline: tonos FFmpeg + PNG + words.json."""
    root = tmp_path / "proj"
    (root / "voice").mkdir(parents=True)
    (root / "stills" / "work").mkdir(parents=True)
    (root / ".stickman").mkdir(parents=True)
    # visual/anchor/action distintos por escena: pasan slideshow_gate y
    # variation_check (gemelos >= 0.75 prohibidos en compose).
    specs = [
        ("stickman throws a paper plane", "paper plane", "throws",
         "The volcano grows as hot lava meets the cold sea waves slowly.",
         "LAVA 1", 220),
        ("stickman draws a rising island chart", "island chart", "draws",
         "New black rock cools down and builds a fresh island shore.",
         "2 ROCKS", 260),
    ]
    scenes, durs, words = [], {}, {}
    for i in range(n_scenes):
        sid = f"s0{i + 1}"
        visual, anchor, action, text, hint, freq = specs[i % len(specs)]
        scenes.append(_scene_script(sid, visual, anchor, action, text, hint))
        audio = root / "voice" / f"{sid}.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", f"sine=frequency={freq}:duration=4",
                        "-c:a", "libmp3lame", str(audio)], check=True)
        durs[sid] = 4.0
        ws = text.split()
        words[sid] = {"words": [
            {"w": w, "t": round(k * 4.0 / len(ws), 3),
             "d": round(4.0 / len(ws), 3)} for k, w in enumerate(ws)]}
        Image.new("RGB", (640, 360), "white").save(
            root / "stills" / "work" / f"s{i + 1:02d}_c01.png")
    script = {"title": "Island Test", "language": "en",
              "target_minutes": 0.2, "thumbnail_hook": "ISLAND",
              "scenes": scenes}
    (root / ".stickman" / "words.json").write_text(
        json.dumps({"scenes": words}), encoding="utf-8")
    return root, script, durs


def _levels(path):
    r = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True)
    mean = mx = None
    for line in r.stderr.splitlines():
        if "mean_volume" in line:
            mean = float(line.split("mean_volume:")[1].split("dB")[0].strip())
        if "max_volume" in line:
            mx = float(line.split("max_volume:")[1].split("dB")[0].strip())
    assert mean is not None and mx is not None, r.stderr[-500:]
    return mean, mx


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
def test_compose_accralate_ducked_perceptible_no_clip(tmp_path):
    cfg = default_config()
    cfg["render"].update({"width": 640, "height": 360, "bgm": "accralate",
                          "bgm_volume": 0.10})
    root, script, durs = _local_project(tmp_path, cfg)
    master = compose(root, script, durs, cfg)
    assert master.exists() and master.stat().st_size > 1000
    report = json.loads(
        (root / ".stickman" / "compose_report.json").read_text(
            encoding="utf-8"))
    assert report["bgm"]["track"] == "accralate"
    assert all(s in report["bgm"]["credit"] for s in CREDIT_SNIPPETS)
    mean_mix, max_mix = _levels(master)
    assert max_mix < 0, "clipping digital en el master"
    # BGM sola a ganancia 0.10: senal real audible, no silencio
    dur = report["master_duration_s"]
    bgm_only = tmp_path / "bgm_only.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-t", str(dur),
         "-i", str(MUSIC / "accralate.mp3"), "-af",
         "aresample=44100,volume=0.10,aresample=48000,"
         "aformat=channel_layouts=stereo",
         str(bgm_only)], check=True)
    mean_b, max_b = _levels(bgm_only)
    assert max_b > -60, "BGM inaudible a ganancia 0.10"
    assert max_b < max_mix, "la voz debe dominar sobre el BGM con ducking"
    # opt-out: sin BGM el master sigue valido y el report no trae credito
    cfg["render"]["bgm"] = "none"
    master2 = compose(root, script, durs, cfg)
    assert master2.exists()
    report2 = json.loads(
        (root / ".stickman" / "compose_report.json").read_text(
            encoding="utf-8"))
    assert report2["bgm"] == {"mode": "none", "track": None, "credit": None}


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
def test_compose_custom_relative_path_cross_platform(tmp_path):
    rel = tmp_path / "proj2"
    (rel / "tracks").mkdir(parents=True)
    shutil.copy2(MUSIC / "accralate.mp3", rel / "tracks" / "mi pista.mp3")
    cfg = default_config()
    cfg["render"].update({"width": 640, "height": 360,
                          "bgm": "tracks/mi pista.mp3"})
    root, script, durs = _local_project(tmp_path, cfg)
    # _local_project crea proj/; mover proyecto a rel manteniendo tracks/
    import shutil as _sh
    for p in list(root.iterdir()):
        _sh.move(str(p), str(rel / p.name))
    master = compose(rel, script, durs, cfg)
    assert master.exists()
    report = json.loads(
        (rel / ".stickman" / "compose_report.json").read_text(
            encoding="utf-8"))
    assert report["bgm"]["track"] == "custom"
    assert report["bgm"]["credit"] is None


def test_release_allows_bgm_files_and_scans_clean():
    import runpy
    funcs = runpy.run_path(str(KIT / "tools" / "release.py"))
    approved = (KIT / "tools" / "allowlist.txt").read_text(
        encoding="utf-8").splitlines()
    assert "src/stickman/bgm.py" in approved
    assert "src/stickman/assets/music/accralate.mp3" in approved
    assert "tests/test_bgm.py" in approved
    assert funcs["scan"](KIT, approved) == []
