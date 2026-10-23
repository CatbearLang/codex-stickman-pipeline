"""Semantic stickman compositor: no intro, measured concept cuts, motion, overlays and sound."""
from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from PIL import Image

from stickman.render import overlays as OV

W, H, FPS = 1920, 1080, 30
XF_S = 0.25
TITLE_VO_IN = 0.35
TITLE_GAP = 0.40
WPM_TARGET = 150.0
MARGEN = 0.4
PRE_ZOOM = 1.12
PAN_MAX = 0.10
MIN_CUT_S = 2.5
SEC_PER_LETRA = 0.0

ASPECT_MIN, ASPECT_MAX = 1.74, 1.81   # mismos umbrales que stills.runner


class RenderError(RuntimeError):
    """Fallo de composición (exit 3 en CLI)."""


class _NullSink:
    """Sumidero para dobles del encoder sin stdin (los bytes se descartan)."""

    def write(self, _b):
        pass

    def close(self):
        pass


def _default_enc(argv: list, **kw):
    import math as _m
    bufsize = kw.pop("bufsize", None) or W * H * 3 * 4
    return subprocess.Popen(argv, stdin=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=bufsize,
                            **kw)


def _default_probe(p) -> float:
    import json as _json
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    try:
        return float(_json.loads(r.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError) as e:
        raise RenderError(f"ffprobe sin duración para {p} ({e})")


def _run(cmd: list) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        raise RenderError(
            "ffmpeg falló:\n" + " ".join(map(str, cmd)) + "\n"
            + (r.stderr or "")[-1500:])


# --- check_fit (paridad tts_fit_gate.py) --------------------------------------
def _estimate_target(words: int, wpm: float = WPM_TARGET) -> float:
    return round(words / wpm * 60.0, 3)


def check_fit(script_path, durs_path, wpm: float = WPM_TARGET) -> dict:
    """La narración real debe caber en la duración objetivo (origen).

    Regla (plan F7: 150 wpm + MARGEN 0.4 s): el audio puede exceder el
    objetivo hasta max(2*MARGEN, 2% del target) — jitter normal del TTS—
    sin fail. El exceso reportado es siempre sobre target+MARGEN: el
    aire de montaje consumido (exceso = audio - target - MARGEN).
    """
    script = json.loads(Path(script_path).read_text(encoding="utf-8"))
    targets = {}
    for sc in script.get("scenes") or []:
        sid = sc.get("id", "?")
        if isinstance(sc.get("duration"), (int, float)):
            targets[sid] = round(float(sc["duration"]), 3)
        else:
            targets[sid] = _estimate_target(
                len((sc.get("voiceover") or "").split()), wpm)
    audios = {k: round(float(v), 3) for k, v in
              json.loads(Path(durs_path).read_text(encoding="utf-8")).items()}
    overruns = []
    for sid, tgt in targets.items():
        if sid not in audios:
            overruns.append({"scene": sid, "audio": None, "target": tgt,
                             "exceso": None, "motivo": "sin audio medido"})
            continue
        tol = round(max(2 * MARGEN, 0.02 * tgt), 3)
        if audios[sid] - tgt > tol:
            overruns.append({"scene": sid, "audio": audios[sid],
                             "target": tgt,
                             "exceso": round(audios[sid] - tgt - MARGEN, 3)})
    return {"verdict": "fail" if overruns else "pass",
            "overruns": overruns, "targets": targets, "audios": audios}


# --- Ken Burns (paridad composer_time25.py, determinista) ----------------------
def _cover_crop_16x9(img: Image.Image) -> Image.Image:
    """Cover-crop centrado a 16:9 si la fuente no lo es (jamás stretch)."""
    w, h = img.size
    ratio = w / h
    if ASPECT_MIN <= ratio <= ASPECT_MAX:
        return img
    if ratio > 16 / 9:
        nw, nh = int(round(h * 16 / 9)), h
    else:
        nw, nh = w, int(round(w * 9 / 16))
    left, top = (w - nw) // 2, (h - nh) // 2
    return img.crop((left, top, left + nw, top + nh))


def _kb_frames(img: Image.Image, dur: float, seed: str,
               steps: int | None = None) -> list:
    """Plan determinista de frames KB: mismos input+seed -> mismos boxes.

    Retorna solo la lista de frames (el crop cover 16:9 se recalcula
    aparte con _cover_crop_16x9 para no acoplar la firma al plan).
    """
    src = _cover_crop_16x9(img)
    iw, ih = src.size
    rnd = random.Random(seed)
    n = steps or max(1, int(round(dur * FPS)))
    zoom_out = rnd.random() < 0.5
    z0, z1 = (PRE_ZOOM, 1.0) if zoom_out else (1.0, PRE_ZOOM)
    pdir = rnd.choice([-1, 1]) * PAN_MAX
    frames = []
    for i in range(n):
        prog = i / n
        ease = prog * prog * (3.0 - 2.0 * prog)   # smoothstep (canónico)
        zoom = z0 + (z1 - z0) * ease
        cw = iw / zoom
        ch = ih / zoom
        cx = iw / 2.0 + ((iw - cw) / 2.0) * ease * pdir
        cy = ih / 2.0
        frames.append({"box": (cx - cw / 2.0, cy - ch / 2.0,
                               cx + cw / 2.0, cy + ch / 2.0),
                       "zoom": zoom, "ease": ease})
    return frames


def kenburns(img: Image.Image, out: Path, dur: float, seed: str, *,
             _enc=None, w: int = W, h: int = H, fps: int = FPS,
             specs=None, t_offset: float = 0.0) -> Path:
    """Toma -> clip KB Pillow (LANCZOS, float box) con overlays directos.

    Overlays (si specs) compuestos POR FRAME sobre el RGB del frame KB
    antes de codificar: sin mp4 RGBA intermedio (lección v6 del origen).
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = _kb_frames(img, dur, seed, steps=max(1, round(dur * fps)))
    src = _cover_crop_16x9(img)
    enc_fn = _enc or _default_enc
    enc = enc_fn(["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                  "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                  "-pix_fmt", "yuv420p", str(out)], bufsize=w * h * 3 * 4)
    proc = enc[0] if isinstance(enc, tuple) else enc
    stdin = getattr(proc, "stdin", None)
    if not hasattr(stdin, "write"):
        inner = getattr(proc, "p", None)
        stdin = getattr(inner, "stdin", None) if inner is not None else None
    if not hasattr(stdin, "write"):
        stdin = proc if hasattr(proc, "write") else _NullSink()
    for i, fr in enumerate(frames):
        frame = src.resize((w, h), Image.Resampling.LANCZOS, box=fr["box"])
        if specs:
            OV.compose_scene(frame, specs, t_offset + i / fps)
        stdin.write(frame.tobytes())
    stdin.close()
    proc.wait()
    if getattr(proc, "returncode", 0) != 0:
        raise RenderError(f"KB encode falló en {out}")
    return out


# --- composición completa -------------------------------------------------------
def _find_first(paths: list) -> Path | None:
    for p in paths:
        if Path(p).exists():
            return Path(p)
    return None


def _probe_default_factory():
    return _default_probe


def compose(project_dir, script: dict, durs: dict, cfg: dict | None = None,
            *, _enc=None, _probe=None):
    """Compone el máster del guion en <project>/output/master.mp4.

    project_dir : proyecto (stills/, voice/, output/, .stickman/).
    script      : guion docu-en-1 validado (dict).
    durs        : {scene_id: duración VO medida (s)}.
    cfg         : config completa (usa [render]); None -> defaults.

    Retorna la ruta del máster. Escribe .stickman/compose_report.json
    con las expectativas que `verify` comprueba (duración esperada,
    resolución, sondas de overlays).
    """
    from stickman.config import default_config
    project = Path(project_dir)
    base = default_config()["render"]
    rcfg = dict(base)
    rcfg.update((cfg or {}).get("render", {}))
    w = int(rcfg.get("width") or W)
    h = int(rcfg.get("height") or H)
    fps = int(rcfg.get("fps") or FPS)
    xf = float(rcfg.get("xfade_s") or XF_S)
    enc_fn = _enc or _default_enc
    probe_fn = _probe or _default_probe

    scenes = list(script.get("scenes") or [])
    if not scenes:
        raise RenderError("guion sin escenas")

    # --- 0. gates previos a gasto/render (plan §4.5): slideshow prohibido
    from stickman.scriptx import gates as _gates
    verdict, avg = _gates.slideshow_gate(script)
    prompts = {s.get("id", f"scene-{k}"): {
        "visual": s.get("visual", ""), "anchor": s.get("anchor", ""),
        "action": s.get("action", ""),
        "prompt": f"{s.get('visual', '')} {s.get('anchor', '')}"}
        for k, s in enumerate(scenes)}
    verdict_v, viols = _gates.variation_check(prompts)
    if verdict == "fail" or verdict_v == "fail":
        raise RenderError(
            f"slideshow_gate={verdict} (promedio={avg}) / "
            f"variation_check={verdict_v}"
            + (f": {viols[0]}" if viols else "")
            + " — demo slideshow prohibida")

    # --- 1. entradas: VO por escena + title VO opcional + stills
    vdir = project / "voice"
    sdir = project / "stills" / "work"
    vo = {}
    missing = []
    for sc in scenes:
        sid = sc.get("id", "?")
        p = _find_first([vdir / f"{sid}.wav", vdir / f"{sid}.mp3"])
        if p is None:
            missing.append(str(vdir / f"{sid}.<wav|mp3>"))
            continue
        vo[sid] = {"path": p, "dur": round(float(probe_fn(p)), 3)}
    if missing:
        raise RenderError("faltan VO de escenas (corre la etapa voice): "
                          + ", ".join(missing))
    vo_title = None  # No intro or title narration in this product.
    vo_title_dur = round(float(probe_fn(vo_title)), 3) if vo_title else 0.0

    tomas = {}
    for i, sc in enumerate(scenes, start=1):
        sid = sc.get("id", "?")
        files = []
        concepts = sc.get("concepts") or []
        for c in concepts:
            p = sdir / f"s{i:02d}_{c.get('id', 'c1')}.png"
            if p.exists():
                files.append(p)
        if not files:
            p = sdir / f"{sid}.png"
            if p.exists():
                files.append(p)
        if not files:
            raise RenderError(
                f"faltan stills para {sid} en {sdir} "
                f"(s{i:02d}_<concept_id>.png o {sid}.png); "
                "corre la etapa stills")
        tomas[sid] = files

    # Start immediately with the first hook. No title card or intro.
    title_dur = 0.0
    TIMING = {"title_dur": 0.0, "t_scene0": 0.0}
    starts = {}
    cur = 0.0
    for sc in scenes:
        starts[sc["id"]] = cur
        cur += vo[sc["id"]]["dur"]
    from stickman.timeline import concept_timeline
    timeline = concept_timeline(script, project, {sid:v["dur"] for sid,v in vo.items()})
    specs = {}
    for sc in scenes:
        sid=sc["id"]
        specs[sid]=[]
        for k,c in enumerate(sc.get("concepts", [])):
            hint=c.get("overlay_hint", "").strip()
            if hint:
                kind="num" if any(ch.isdigit() for ch in hint) else "card_sketch"
                specs[sid].append(OV.normalize_spec({"t":kind,"at":timeline[sid][k]["start"],"pos":"top" if k%2==0 else "bot", "txt" if kind=="num" else "l1":hint.upper()}))
    tmp = project / ".stickman" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    # --- 4. escenas: KB + overlays directos en Pillow
    scene_files = []
    for k, sc in enumerate(scenes):
        sid = sc["id"]
        scene_dur = round(float(vo[sid]["dur"]) + xf, 3)   # TAIL = xf
        files = tomas[sid]
        if len(files) != len(timeline[sid]):
            raise RenderError("Every concept requires its own image.")
        parts = [c["end"] - c["start"] for c in timeline[sid]]
        parts[-1] += xf if k < len(scenes)-1 else 0
        t_off = 0.0
        cuts = []
        for j, pd in enumerate(parts):
            img = Image.open(files[j % len(files)]).convert("RGB")
            out = tmp / f"kb_{sid}_{j}.mp4"
            kenburns(img, out, pd, f"{sid}-{j}", _enc=enc_fn, w=w, h=h,
                     fps=fps, specs=specs.get(sid) or [], t_offset=t_off)
            t_off += pd
            cuts.append(out)
        if len(cuts) == 1:
            scene_files.append(cuts[0])
        else:
            base_clip = tmp / f"base_{sid}.mp4"
            _run(["ffmpeg", "-y",
                  *[x for p in cuts for x in ("-i", str(p))],
                  "-filter_complex",
                  ";".join(f"[{i}:v]fps={fps},settb=AVTB[v{i}]"
                           for i in range(len(cuts)))
                  + ";" + "".join(f"[v{i}]" for i in range(len(cuts)))
                  + f"concat=n={len(cuts)}:v=1:a=0[vout]",
                  "-map", "[vout]", "-c:v", "libx264", "-preset",
                  "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                  str(base_clip)])
            scene_files.append(base_clip)

    # Crossfade visual tails; narration timing remains contiguous.
    inputs=[]; fc=[]
    for i,sf in enumerate(scene_files):
        inputs += ["-i", str(sf)]
        fc.append(f"[{i}:v]fps={fps},settb=AVTB,format=yuv420p[v{i}]")
    prev="[v0]"
    for i in range(1,len(scene_files)):
        lab=f"[x{i}]"
        fc.append(f"{prev}[v{i}]xfade=transition=fade:duration={xf}:offset={starts[scenes[i]['id']]:.3f}{lab}")
        prev=lab
    fc.append(f"{prev}format=yuv420p[vout]")
    mudo=tmp/"video_mudo.mp4"
    _run(["ffmpeg","-y",*inputs,"-filter_complex", ";".join(fc),"-map","[vout]","-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p",str(mudo)])
    video_dur = round(float(probe_fn(mudo)), 3)

    # --- 6. narración (EQ+comp por escena, delays, loudnorm -16)
    narr_wavs = []
    for sc in scenes:
        sid = sc["id"]
        wv = tmp / f"narr_{sid}.wav"
        _run(["ffmpeg", "-y", "-i", str(vo[sid]["path"]), "-af",
              ("aresample=44100,highpass=f=80,lowpass=f=12000,"
               "equalizer=f=2500:t=q:w=1:g=+3,"
               "acompressor=threshold=-18dB:ratio=3:attack=15:release=150,"
               f"apad=whole_dur={vo[sid]['dur']:.3f}"),
              "-ac", "1", str(wv)])
        narr_wavs.append((wv, starts[sid]))
    vo_title_wav = None
    if vo_title:
        vo_title_wav = tmp / "vo_title.wav"
        _run(["ffmpeg", "-y", "-i", str(vo_title), "-af",
              ("aresample=44100,highpass=f=80,lowpass=f=12000,"
               "equalizer=f=2500:t=q:w=1:g=+3,"
               "acompressor=threshold=-18dB:ratio=3:attack=15:"
               "release=150"), "-ac", "1", str(vo_title_wav)])
    wavs = ([(vo_title_wav, TIMING["t_vo_in"])] if vo_title_wav else []) \
        + narr_wavs
    fc = []
    labs = []
    for i, (p, delay) in enumerate(wavs):
        fc.append(f"[{i}:a]aformat=sample_rates=44100:"
                  "channel_layouts=mono[n{i}]".format(i=i))
        ms = int(max(0.0, delay) * 1000)
        fc.append(f"[n{i}]adelay={ms}|{ms}[d{i}]")
        labs.append(f"[d{i}]")
    fc.append("".join(labs)
              + f"amix=inputs={len(labs)}:normalize=0:duration=longest,"
                "loudnorm=I=-16:TP=-1.5:LRA=7[narr]")
    narr = tmp / "narracion.wav"
    _run(["ffmpeg", "-y", *[x for p, _d in wavs for x in ("-i", str(p))],
          "-filter_complex", ";".join(fc), "-map", "[narr]",
          "-t", f"{video_dur:.3f}", str(narr)])

    # --- 7. SFX sintetizados propios (whoosh transiciones, pop en nums)
    events = []
    for k, sc in enumerate(scenes):
        if k > 0:
            events.append({"kind": "whoosh",
                           "t": round(starts[sc["id"]] - 0.2, 3)})
        for sp in specs.get(sc["id"], []):
            if sp["t"] == "num":
                events.append({"kind": "pop",
                               "t": round(starts[sc["id"]] + sp["at"], 3)})
    fc = []
    labs = []
    for i, ev in enumerate(events):
        if ev["kind"] == "whoosh":
            fc.append(f"[{i}:a]anull[s{i}]")
            fc.append(f"[s{i}]lowpass=f=1200,"
                      "afade=t=in:st=0:d=0.08,"
                      "afade=t=out:st=0.15:d=0.2,"
                      f"volume=0.55,adelay={int(max(0, ev['t']) * 1000)}"
                      f"|{int(max(0, ev['t']) * 1000)}[w{i}]")
            labs.append(f"[w{i}]")
        else:
            fc.append(f"[{i}:a]anull[s{i}]")
            fc.append(f"[s{i}]afade=t=out:st=0.04:d=0.08,volume=0.8,"
                      f"adelay={int(max(0, ev['t']) * 1000)}"
                      f"|{int(max(0, ev['t']) * 1000)}[p{i}]")
            labs.append(f"[p{i}]")
    sfx = None
    if labs:
        fc.append("".join(labs)
                  + f"amix=inputs={len(labs)}:normalize=0:"
                    "duration=longest,volume=1.0[sfx]")
        sfx = tmp / "sfx.wav"
        effects = Path(__file__).resolve().parents[1] / "assets" / "sfx"
        sfx_inputs = [x for ev in events for x in ("-i", str(effects / ("whoosh.wav" if ev["kind"] == "whoosh" else "pop.wav")))]
        _run(["ffmpeg", "-y", *sfx_inputs, "-filter_complex", ";".join(fc),
              "-map", "[sfx]", "-t", f"{video_dur:.3f}", str(sfx)])

    # --- 8. máster -14 LUFS (narr + sfx + BGM opcional del proyecto)
    # BGM: stickman.bgm.resolve_bgm — accralate (CC BY, default),
    # bundled/ambient (propia), none (opt-out), o ruta custom del usuario.
    # El BGM real entra con ducking sidechaincompress (voz = key) para que
    # la música quede perceptible pero siempre bajo la narración.
    outdir = project / "output"
    outdir.mkdir(parents=True, exist_ok=True)
    master = outdir / "master.mp4"
    from stickman import bgm as _bgm
    bgm_raw = rcfg.get("bgm")
    if bgm_raw == "none":
        bgm_path, bgm_track, bgm_credit = None, None, None
    else:
        try:
            bgm_path, bgm_track, bgm_credit = _bgm.resolve_bgm(
                bgm_raw, project)
        except FileNotFoundError as e:
            raise RenderError(str(e))
    fc = []
    inputs = ["-i", str(mudo), "-i", str(narr)]
    labels = ["[1:a]volume=0.95[n]"]
    idx = 2
    if sfx is not None:
        inputs += ["-i", str(sfx)]
        labels.append(f"[{idx}:a]volume=1.0[s]")
        idx += 1
    bgm_labels: list = []
    if bgm_path is not None:
        if not bgm_path.is_absolute():
            bgm_path = project / bgm_path
        if not bgm_path.exists():
            raise RenderError(
                f"render.bgm: no existe la pista {bgm_raw!r} "
                f"({bgm_path}); usa accralate|bundled|ambient|none "
                "o una ruta valida a tu propia pista licenciada")
        inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
        bgm_labels, bgm_narr, bgm_mix = _bgm.bgm_filter(
            idx, volume=float(rcfg.get("bgm_volume", 0.1)))
        labels.extend(bgm_labels)
        idx += 1
    else:
        bgm_narr, bgm_mix = "[n]", "[g]"
    fc += labels
    mix_labels = [(bgm_narr if bgm_path is not None else "[n]")] \
        + (["[s]"] if sfx is not None else []) \
        + ([bgm_mix] if bgm_path is not None else [])
    fc.append("".join(mix_labels)
              + f"amix=inputs={len(mix_labels)}:normalize=0,"
                "loudnorm=I=-14:TP=-1.5:LRA=9,"
                "aresample=48000,"
                "aformat=channel_layouts=stereo[aout]")
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
          "-map", "0:v", "-map", "[aout]",
          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
          "-t", str(video_dur), "-movflags", "+faststart", str(master)])
    master_dur = round(float(probe_fn(master)), 3)

    # --- 9. derivado 480p (Lanczos, paridad qa_cycle: width 854)
    v480 = outdir / "master_480p.mp4"
    _run(["ffmpeg", "-y", "-i", str(master), "-vf",
          "scale=854:-2:flags=lanczos", "-c:v", "libx264", "-preset",
          "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "copy", str(v480)])

    # --- 10. informe para verify (sondas de overlays, expectativas)
    # overlay_probes: caja (px, 854-base) y tiempo global por spec activa.
    # CONTRATO FUTURO para herramientas externas de QA visual; NO hay
    # verificador que las consuma hoy (la sonda alfa de overlays queda
    # cubierta a nivel unitario en tests/test_compose.py).
    scale = w / OV.W
    probes = []
    for k, sc in enumerate(scenes):
        for sp in specs.get(sc["id"], []):
            box = (OV.card_box(sp) if sp["t"].startswith("card")
                   else OV.num_box(sp))
            probes.append({
                "scene": sc["id"],
                "t_global": round(starts[sc["id"]] + sp["at"] + 0.5, 3),
                "t_clean": round(starts[sc["id"]] + sp["at"] - 0.6, 3),
                "box": [int(v * scale) for v in box]})
    report = {
        "schema": 1,
        "tool": "stickman compose",
        "width": w, "height": h, "fps": fps,
        "title_timing": {**TIMING, "title_dur": title_dur},
        "expected_duration_s": round(title_dur
                                     + sum(float(vo[s["id"]]["dur"])
                                           for s in scenes), 3),
        "master_duration_s": master_dur,
        "scenes": {s["id"]: {"vo_s": vo[s["id"]]["dur"],
                             "start_s": starts[s["id"]],
                             "tomas": [str(p) for p in tomas[s["id"]]]}
                   for s in scenes},
        "overlay_probes": probes,
        "sfx_events": events,
        "bgm": {"mode": bgm_raw, "track": bgm_track,
                "credit": bgm_credit},
    }
    (project / ".stickman").mkdir(exist_ok=True)
    (project / ".stickman" / "compose_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    return master
