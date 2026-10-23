"""stickman/align — alineación palabra↔tiempo (plan F7).

Modos:
- edge-words  : VTT word-boundaries de edge-tts (voice/<sid>.vtt). Si una
  escena no tiene VTT utilizable, cae a proporcional para ESA escena
  (fallback documentado en words.json: mode=proportional-fallback).
- proportional: rejilla uniforme sobre la duración medida
  (voice/meta.json → {sid: {"duration_s": s}}).
- whisper-local: lazy faster-whisper (inyectable, word_timestamps=True;
  sin descarga de modelos en tests). Sin el paquete → RuntimeError
  accionable (pip install faster-whisper / doctor). Sin
  voice/<sid>.wav → RuntimeError accionable.

Salida durable: <project>/.stickman/words.json
{"schema":1, "mode":..., "scenes":{sid:{"duration_s","mode","end","words":
 [{"w","t","d"}...]}}}

Sin audio real: usa la duración medida de meta o la semilla local
(words/2.5, la misma del calibrate). $0 y sin red.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SEED_S_PER_WORD = 2.5  # semilla local (calibrate: scene_audio_s = words/2.5)
_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})")
_EDGE = re.compile(r"<(\d{1,2}:\d{2}:\d{2}\.\d{3})><c>([^<]+)</c>")


def _ts_to_s(ts: str) -> float:
    m = _TS.fullmatch(ts.strip())
    if not m:
        raise ValueError(f"timestamp VTT inválido: {ts!r}")
    h, mnt, s, ms = (int(x) for x in m.groups())
    return h * 3600 + mnt * 60 + s + ms / 1000.0


def _parse_edge_vtt(path: Path) -> list[dict]:
    """Extrae [(w, t)] del VTT word-boundaries de edge-tts."""
    text = path.read_text(encoding="utf-8", errors="replace")
    words: list[dict] = []
    for ts, w in _EDGE.findall(text):
        w = w.strip()
        if w:
            words.append({"w": w, "t": _ts_to_s(ts), "d": 0.0})
    return words


def _proportional(text: str, duration: float) -> list[dict]:
    ws = (text or "").split()
    n = len(ws)
    if n == 0:
        return []
    step = float(duration) / n
    return [{"w": w, "t": round(i * step, 3), "d": round(step, 3)}
            for i, w in enumerate(ws)]


def _finalize_edge(words: list[dict], end: float) -> None:
    """Rellena d: la palabra dura hasta la siguiente; la última hasta end."""
    for i, w in enumerate(words):
        nxt = words[i + 1]["t"] if i + 1 < len(words) else float(end)
        w["d"] = round(max(0.0, nxt - w["t"]), 3)
        w["t"] = round(w["t"], 3)


def _whisper_words(wav: Path) -> list[dict]:
    """Adapter lazy faster-whisper: import perezoso + word_timestamps.

    Devuelve [{w,t}] con tiempos medidos del audio real. Sin el paquete
    instalado → RuntimeError accionable (pip/doctor); nunca un stub.
    """
    try:
        from faster_whisper import WhisperModel  # noqa:PLC0415 (lazy)
    except ImportError as e:
        raise RuntimeError(
            "align whisper-local requiere faster-whisper: "
            "instala con `pip install faster-whisper` (o `doctor` para "
            "verificar). Sin el paquete no hay alineación por audio."
        ) from e
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav), word_timestamps=True)
    words: list[dict] = []
    for seg in segments:
        for wd in getattr(seg, "words", None) or []:
            w = (getattr(wd, "word", "") or "").strip()
            t = getattr(wd, "start", None)
            if w and t is not None:
                words.append({"w": w, "t": float(t), "d": 0.0})
    return words


def _scene_words(script_scene: dict, project: Path, mode: str,
                 duration: float) -> tuple[list[dict], str]:
    sid = str(script_scene.get("id") or "?")
    text = script_scene.get("voiceover", "") or ""
    if mode == "proportional":
        return _proportional(text, duration), "proportional"
    if mode == "whisper-local":
        wav = project / "voice" / f"{sid}.wav"
        if not wav.exists(): wav = wav.with_suffix(".mp3")
        if not wav.exists():
            raise RuntimeError(
                f"align whisper-local: falta voice/{sid}.wav (ejecuta la "
                "etapa voice --live antes de align whisper-local). Ruta "
                f"buscada: {wav}")
        words = _whisper_words(wav)
        _finalize_edge(words, duration)
        return words, "whisper-local"
    direct = project / "voice" / f"{sid}.words.json"
    if direct.exists():
        words=json.loads(direct.read_text(encoding="utf-8"))
        if words:
            return words, "edge-words"
    vtt = project / "voice" / f"{sid}.vtt"
    if vtt.exists():
        try:
            words = _parse_edge_vtt(vtt)
        except ValueError:
            words = []
        if words:
            _finalize_edge(words, duration)
            return words, "edge-words"
    raise ValueError(f"{sid}: no measured word timings. Generate voice first, use whisper-local for API voices, or explicitly select proportional for approximate timing.")


def align_words(script: dict, project: str | Path, *, mode: str = "edge-words",
                meta: dict | None = None) -> dict:
    """Alinea las palabras del voiceover y escribe .stickman/words.json.

    meta: {sid: {"duration_s": s}} (duraciones medidas por la etapa voice).
    Escena sin duración medida → semilla local words/2.5 (estimación
    declarada en el resultado; jamás se presenta como medida).
    """
    if mode not in ("edge-words", "proportional", "whisper-local"):
        raise ValueError(f"align.mode desconocido: {mode!r} "
                         "(edge-words|proportional|whisper-local)")
    project = Path(project)
    meta = dict(meta or {})
    scenes: dict = {}
    for sc in script.get("scenes") or []:
        sid = str(sc.get("id") or "?")
        m = meta.get(sid) or {}
        dur = m.get("duration_s")
        estimated = dur is None
        if estimated:
            dur = round(len((sc.get("voiceover") or "").split())
                        / SEED_S_PER_WORD, 3)
        try:
            dur = float(dur)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"align: duration_s inválida para {sid}: {m.get('duration_s')!r}"
            ) from e
        words, used = _scene_words(sc, project, mode, dur)
        scenes[sid] = {"duration_s": round(dur, 3), "end": round(dur, 3),
                       "mode": used, "estimated": estimated, "words": words}
    res = {"schema": 1, "mode": mode, "scenes": scenes}
    out = project / ".stickman"
    out.mkdir(parents=True, exist_ok=True)
    (out / "words.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    return res
