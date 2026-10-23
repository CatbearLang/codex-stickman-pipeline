"""stickman/pipeline.py — builder real F9 (banco→…→MP4).

build_pipeline(project, occ, manifest, live) ejecuta las etapas del active
según el manifiesto: reutiliza etapas ok no-stale (revalidate §4.4) y llama
los mismos handlers de etapa que el CLI (factories idénticos).

Errores: LiveGateError → exit 2 (flow); RuntimeError de proveedor/render →
exit 3 reanudable (flow.run_one los traduce; el manifiesto queda durable
con las etapas ok).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _bgm_for_caption(cfg: dict | None) -> str:
    """Bloque de credito BGM para caption.txt (sin tocar creditos del usuario).

    Solo la pista incluida CC BY (accralate) aporta su atribucion
    obligatoria; ambient/custom/none no anaden nada.
    """
    try:
        from stickman import bgm as _bgm
        _path, track, credit = _bgm.resolve_bgm(
            (cfg or {}).get("render", {}).get("bgm"))
        return _bgm.caption_block(track, credit)
    except (OSError, ValueError):
        return ""


def _scene_meta(voice_dir: Path) -> dict:
    """{sid: {"duration_s": s}} desde voice/meta.json (escrito por voice)."""
    p = voice_dir / "meta.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _check_generated_voice_duration(project: Path, cfg: dict) -> None:
    """Check duracion MEDIDA antes de gastar cuota en imagenes (t_dbdbc827).

    Producto 5-6 min: para target >= 5 el video real debe medir 300-360 s.
    Falla cerrado ANTES de stills; jamas trunca narracion ni baja densidad.
    """
    if cfg["script"]["provider"] == "local-advanced":
        return  # User-provided scripts can intentionally be any length.
    target = float(cfg["project"]["target_minutes"])
    if target < 5:
        return
    meta = _scene_meta(project / "voice")
    actual_s = sum(float(item.get("duration_s", 0)) for item in meta.values())
    if not 300 <= actual_s <= 360:
        actual_min = actual_s / 60
        raise RuntimeError(
            f"Measured narration is {actual_min:.2f} minutes ({actual_s:.1f}s); "
            f"producto 5-6 min exige 300-360s medidos antes de imagenes. "
            f"Adjust voice.speed or regenerate the script, then resume "
            f"before image generation.")


def build_pipeline(project: Path, occ, manifest, live: bool) -> Path:
    """Ejecuta las etapas pendientes/stale del manifiesto. Retorna el MP4."""
    project = Path(project)
    from stickman import cli as _cli
    from stickman import align as _align
    from stickman import verify as _verify
    from stickman.manifest import config_sections_sha, sha256_file
    from stickman.render.composer import compose, RenderError

    # --- revalidación: solo re-ejecutar pendientes/stale (§4.4) ----------
    # rework D2: shas POR SECCIÓN de la config efectiva (defaults +
    # stickman.toml): un cambio irrelevante ([render].xfade_s) NO marca
    # stale etapas pagas; [voice]/[script]/[project]/[images]/[align]
    # invalidan por su scope. El config_sha global NO se usa (sobre-
    # invalidaba: regeneraba voz pagada por un cambio de render).
    script_path = project / "script.json"
    stale = manifest.revalidate(
        project, script_sha=_sha(script_path),
        config_sections_sha=config_sections_sha(project))
    for st in stale:
        print(f"pipeline: {st} stale -> re-ejecutar")
    stages = manifest.stages

    # --- script -----------------------------------------------------------
    if stages.get("script", {}).get("status") != "ok":
        rc = _cli._run_stage_script(project, live)
        if rc:
            raise RuntimeError(f"etapa script falló (exit {rc})")
        manifest.mark_ok("script", {},
                         {"script.json": sha256_file(script_path)})
        # rework D2: el guion EFECTIVO es el recién generado; el baseline
        # del manifiesto debe ser el sha PRODUCIDO (si el manifiesto se
        # sembró con el sha de un guion previo distinto, el resume vería
        # un "cambio de guion" fantasma y regeneraría voz paga).
        manifest.data["script_sha256"] = sha256_file(script_path)
        manifest.save(project)

    # --- voice (TODAS las escenas) ------------------------------------------
    if stages.get("voice", {}).get("status") != "ok":
        rc = _cli._run_stage_voice_full(project, live)
        if rc:
            raise RuntimeError(f"etapa voice falló (exit {rc})")
        meta_path = project / "voice" / "meta.json"
        manifest.mark_ok("voice", {}, {str(p.relative_to(project)): sha256_file(p) for p in (project / "voice").glob("*") if p.is_file()})
        manifest.save(project)

    from stickman.config import load_config
    _check_generated_voice_duration(project, load_config(project))

    # --- pre-gasto imagenes: estima y falla cerrado ANTES de Codex ------
    # t_dbdbc827 + rework t_86fd4402: 1 concepto = 1 llamada Codex;
    # tope 36/video, 72/dos corridas. preflight_budget usa la reserva
    # efectiva (images.reserve_regen) y el ledger durable
    # (STICKMAN_BUDGET_LEDGER o .stickman/image_budget.json): falla
    # cerrado ANTES de gastar si el guion supera 36, si una corrida
    # rompe 72, o si el acumulado entre proyectos supera 72.
    # Sin reintentos automaticos.
    try:
        _script_doc = json.loads(script_path.read_text(encoding="utf-8"))
        _n_concepts = sum(len(s.get("concepts", []))
                          for s in _script_doc.get("scenes", []))
        from stickman.stills.runner import preflight_budget as _preflight
        _cfg_eff = load_config(project)
        _reserve_eff = int((_cfg_eff.get("images", {}) or {}).get(
            "reserve_regen", 8))
        _pre = _preflight(_n_concepts, reserve=_reserve_eff,
                          project=project)
        print(f"pipeline: pre-gasto imagenes: {_n_concepts} conceptos "
              f"(reserva {_reserve_eff}) -> "
              f"{_pre['per_video_calls']} llamadas/video, "
              f"acumulado {_pre['consumed_before']}->"
              f"{_pre['consumed_after']}/{_pre['two_run_budget']} "
              f"(ledger {_pre['ledger']})")
    except ValueError as e:
        raise RuntimeError(f"pre-gasto imagenes: {e}")

    # --- align ----------------------------------------------------------------
    if stages.get("align", {}).get("status") != "ok":
        script = json.loads(script_path.read_text(encoding="utf-8"))
        cfg = _cli._project_cfg(project)
        mode = (cfg or {}).get("align", {}).get("mode") or "edge-words"
        _align.align_words(script, project, mode=mode,
                           meta=_scene_meta(project / "voice"))
        manifest.mark_ok(
            "align", {},
            {".stickman/words.json":
             sha256_file(project / ".stickman" / "words.json")})
        manifest.save(project)

    # --- stills -----------------------------------------------------------------
    if stages.get("stills", {}).get("status") != "ok":
        rc = _cli._run_stage_stills(project, live)
        if rc:
            raise RuntimeError(f"etapa stills falló (exit {rc})")
        outputs = {}
        wdir = project / "stills" / "work"
        if wdir.exists():
            for p in sorted(wdir.glob("*.png")):
                outputs[f"stills/work/{p.name}"] = sha256_file(p)
        manifest.mark_ok("stills", {}, outputs)
        manifest.save(project)

    # --- compose -----------------------------------------------------------------
    outdir = project / "output"
    master = outdir / "master.mp4"
    if stages.get("compose", {}).get("status") != "ok" or not master.exists():
        cfg = _cli._project_cfg(project)
        if cfg is None:
            raise RuntimeError("config inválida para compose")
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            durs = {sid: float(v.get("duration_s"))
                    for sid, v in _scene_meta(project / "voice").items()
                    if isinstance(v, dict) and v.get("duration_s")}
            compose(project, script, durs, cfg)
        except RenderError as e:
            raise RuntimeError(f"compose falló: {e}")
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise RuntimeError(f"compose falló: {e}")
        manifest.mark_ok("compose", {},
                         {"output/master.mp4": sha256_file(master)})
        manifest.save(project)

    # --- verify --------------------------------------------------------------------
    if stages.get("verify", {}).get("status") != "ok":
        rep_path = project / ".stickman" / "compose_report.json"
        try:
            exp = json.loads(rep_path.read_text(encoding="utf-8")).get(
                "expected_duration_s")
        except (OSError, ValueError):
            exp = None
        cfg = _cli._project_cfg(project)
        ok, rep = _verify.verify(master, expected_duration_s=exp, width=cfg["render"]["width"], height=cfg["render"]["height"])
        (project / ".stickman" / "verify_report.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        if not ok:
            raise RuntimeError(f"verify falló: {rep}")
        manifest.mark_ok("verify", {},
                         {"output/master.mp4": sha256_file(master)})
        manifest.save(project)

    from stickman.thumbnailx import make_thumbnail
    import shutil
    candidates=sorted((project/"stills/work").glob("*.png"))
    script=json.loads(script_path.read_text(encoding="utf-8"))
    make_thumbnail(src=candidates[0],out=outdir/"thumbnail.png",hook=script.get("thumbnail_hook") or script["title"])
    metadata={"schema":1,"topic":occ.topic,"title":script["title"],"published":False,"status":"rendered","files":{"video":"master.mp4","preview":"master_480p.mp4","thumbnail":"thumbnail.png"}}
    (outdir/"metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2), encoding="utf-8")
    (outdir/"caption.txt").write_text(
        script["title"]+"\n\n"+script.get("logline", "")+"\n"
        + _bgm_for_caption(cfg), encoding="utf-8")
    # Preserve each completed video; subsequent bank jobs must not overwrite it.
    delivered=project/"deliveries"/occ.occ_id
    delivered.mkdir(parents=True,exist_ok=True)
    for path in outdir.iterdir():
        if path.is_file(): shutil.copy2(path,delivered/path.name)
    shutil.copy2(script_path,delivered/"script.json")
    shutil.copy2(project/".stickman/verify_report.json",delivered/"technical-check.json")
    return delivered/"master.mp4"
