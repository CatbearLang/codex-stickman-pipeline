"""CLI Stickman Video CLI — 10 comandos top-level exactos (plan §4.1).

Reglas: argparse únicamente; pathlib (espacios OK); subprocesos sin
shell=True y sin Bash; sin publicar/aprobar/enviar mensajes.
Exit codes: 0 ok / 1 uso / 2 fallo reintentable / 3 proveedor-verificación.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stickman import config as config_mod
from stickman import logx

STAGES = ("script", "voice", "align", "stills", "compose", "verify")

PROVIDERS_CHECK = ("voice.edge", "voice.elevenlabs", "voice.http", "images.codex-oauth", "images.openai-api", "script.codex-oauth", "script.http")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stickman",
                                description="Stickman Video CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="create a project")
    i.add_argument("dir")
    i.add_argument("--script-provider", choices=["codex-oauth", "http"])
    i.add_argument("--topic")
    i.add_argument("--from-script")

    c = sub.add_parser("config", help="view or update project settings")
    csub = c.add_subparsers(dest="config_cmd", required=True)
    csub.add_parser("show", help="show settings")
    cs = csub.add_parser("set", help="set a value")
    cs.add_argument("clave", metavar="key")
    cs.add_argument("valor", metavar="value")

    k = sub.add_parser("check", help="check local tools and providers")
    k.add_argument("--provider", choices=list(PROVIDERS_CHECK))

    s = sub.add_parser("script", help="script operations")
    ssub = s.add_subparsers(dest="script_cmd", required=True)
    sv = ssub.add_parser("validate", help="validate a docu-en-1 script")
    sv.add_argument("script_json")

    r = sub.add_parser("run", help="make a video from the topic bank or one topic")
    r.add_argument("--project", default=".")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--topic")
    g.add_argument("--batch", nargs="?", const=1, type=int)
    g.add_argument("--stage", choices=list(STAGES))
    r.add_argument("--resume", action="store_true")
    r.add_argument("--live", action="store_true")

    t = sub.add_parser("thumbnail", help="make a thumbnail")
    t.add_argument("--from-image")
    t.add_argument("--hook")
    t.add_argument("--out")

    cl = sub.add_parser("clean", help="remove derived assets")
    cl.add_argument("--project", default=".")
    cl.add_argument("--stage", choices=["stills", "voice", "compose",
                                        "verify"])
    cl.add_argument("--force", action="store_true")

    rs = sub.add_parser("resume", help="resume an interrupted run")
    rs.add_argument("--project", default=".")
    rs.add_argument("--from-stage", choices=list(STAGES))
    rs.add_argument("--live", action="store_true")

    st = sub.add_parser("status", help="show job and topic bank status")
    st.add_argument("--project", default=".")
    st.add_argument("--json", action="store_true")

    cb = sub.add_parser("calibrate", help="estimate local voice duration")
    cb.add_argument("--voice", required=True)

    return p


def _cmd_init(args: argparse.Namespace) -> int:
    import json, shutil
    target = Path(args.dir)
    if (target / "stickman.toml").exists():
        print("Project already initialized; existing configuration preserved.", file=sys.stderr)
        return 1
    source = Path(args.from_script).resolve() if args.from_script else None
    if source:
        from stickman.scriptx.schema import validate_docu_en_1
        try:
            errors = validate_docu_en_1(json.loads(source.read_text(encoding="utf-8")))
            if errors: raise ValueError("; ".join(errors))
        except (OSError, ValueError) as e:
            print(str(e),file=sys.stderr); return 1
    target.mkdir(parents=True, exist_ok=True)
    (target / "banco tema.txt").touch(exist_ok=True)
    (target / ".stickman").mkdir(exist_ok=True)
    provider = "local-advanced" if source else args.script_provider or "codex-oauth"
    config_mod.config_set(target, "script.provider", provider)
    if source:
        shutil.copy2(source, target / "input-script.json")
        config_mod.config_set(target, "script.from_script", "input-script.json")
    if args.topic:
        config_mod.config_set(target, "project.slug", args.topic)
        (target / "banco tema.txt").write_text(
            args.topic.strip() + "\n", encoding="utf-8", newline="\n")
    print(f"Project ready: {target}. Run stickman check; then stickman run --project <folder> --live.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """stickman check [--provider ...]: requisitos + official/verified."""
    from stickman.doctor import doctor
    return doctor(args.provider)


def _cmd_status(args: argparse.Namespace) -> int:
    """stickman status [--json]: estado del trabajo activo y etapas.

    Punto de recogida para integraciones externas (plan §4.4): stages
    {stage: status|sha}, banco (pendientes) y active (occ_id/topic).
    Sin valores de secretos jamás (solo presencia).
    """
    import json as _json
    project = Path(args.project)
    state = project / ".stickman"
    data: dict = {"schema": 1, "project": str(project), "stages": {},
                  "active": None, "bank_pending": None}
    mp = state / "manifest.json"
    if mp.exists():
        try:
            man = _json.loads(mp.read_text(encoding="utf-8"))
            data["active"] = {k: man.get(k) for k in
                              ("occ_id", "topic", "slug")}
            for st, info in (man.get("stages") or {}).items():
                data["stages"][st] = {
                    "status": info.get("status"),
                    "at": info.get("at")}
        except ValueError as e:
            print(f"status: unreadable manifest ({e})", file=sys.stderr)
            return 3
    bank = project / "banco tema.txt"
    if bank.exists():
        try:
            lines = bank.read_text(encoding="utf-8-sig").splitlines()
            data["bank_pending"] = sum(1 for l in lines if l.strip())
        except OSError:
            data["bank_pending"] = None
    if args.json:
        print(_json.dumps(data, ensure_ascii=False))
    else:
        print(f"project {project}")
        for st, info in data["stages"].items():
            print(f"  {st}: {info['status']} ({info.get('at')})")
        if data["active"]:
            print(f"  active: {data['active'].get('occ_id')} "
                  f"({data['active'].get('topic')})")
        if data["bank_pending"] is not None:
            print(f"  pending topics: {data['bank_pending']}")
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    """stickman calibrate --voice <nombre>: estimación semilla local.

    Ejecuta preflight sobre el guion demo incluido
    (fixtures/script_demo.json) usando --voice como nombre de perfil y
    guarda el informe en <cwd>/.stickman/calibrate_<voz>.json. Solo usa
    conteo de palabras local (portado de tts_duration_preflight.py);
    NO mide audio real: la tasa words/2.5 es una ESTIMACIÓN semilla
    inequívoca (method=estimated_seconds_per_word_local_seed,
    estimated=true, local_seed=true). NO sintetiza audio, NO consume créditos, NO
    incluye perfiles de ejemplo. El usuario reemplaza la semilla
    midiendo su propia voz. Salida 2 si el gate es BLOCK
    (título repetido), 0 si no.
    """
    import json as _json
    from pathlib import Path as _Path
    from stickman.voice import preflight as _pf
    fixtures = _Path(__file__).resolve().parent / "assets"
    demo = fixtures / "script-example.json"
    try:
        script = _json.loads(demo.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"calibrate: demo script missing ({e})", file=sys.stderr)
        return 3
    words = sum(_pf.word_count(s.get("voiceover", ""))
                for s in script.get("scenes", []))
    if words <= 0:
        print("calibrate: demo script has no words", file=sys.stderr)
        return 3
    # Perfil semilla local: el usuario lo reemplaza midiendo su propia
    # voz con --live (no se incluyen perfiles de voz de terceros).
    profile = {"observations": [{"speed": 1.0, "scene_words": words,
                                 "scene_audio_s": words / 2.5,
                                 "title_words": 0, "title_audio_s": 0.0}]}
    try:
        report = _pf.estimate(script, profile, 1.0, measured=False)
    except ValueError as e:
        print(f"calibrate: {e}", file=sys.stderr)
        return 3
    outdir = _Path.cwd() / ".stickman"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"calibrate_{args.voice}.json"
    out.write_text(_json.dumps({**report, "voice": args.voice,
                                "local_seed": True}, ensure_ascii=False,
                               indent=1) + "\n", encoding="utf-8")
    print(f"calibrate voice={args.voice}: gate={report['gate']} "
          f"({report['reason']}) -> {out}")
    return 2 if report["gate"] == "BLOCK" else 0


def _run_stage_voice_full(project, live: bool) -> int:
    """Voz de TODAS las escenas (+ title opcional) del guion.

    Escribe voice/<sid>.wav|mp3 + VTT word-boundaries y voice/meta.json
    {sid: {"duration_s": s}} para align/compose. Exit: 0 ok, 1 faltan
    entradas, 2 sin gate live, 3 proveedor/guion.
    """
    import json as _json
    script_path = project / "script.json"
    if not script_path.exists():
        print("run voice: missing script.json (run `run --stage script` first)", file=sys.stderr)
        return 1
    from stickman.errors import LiveGateError as _LiveGateError
    from stickman.voice.factory import make_voice_provider
    cfg = _project_cfg(project)
    if cfg is None:
        return 1
    try:
        script = _json.loads(script_path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"run voice: invalid script ({e})", file=sys.stderr)
        return 3
    try:
        prov = make_voice_provider(cfg)
    except Exception as e:
        print(f"run voice: {e}", file=sys.stderr)
        return 1
    voice = (cfg.get("voice", {}).get("name") or "en-US-AndrewNeural")
    try:
        speed = float(cfg.get("voice", {}).get("speed", 1.0))
    except (TypeError, ValueError):
        print("run voice: voice.speed must be numeric", file=sys.stderr)
        return 1
    scenes = script.get("scenes", [])
    if not scenes:
        print("run voice: script has no scenes", file=sys.stderr)
        return 3
    vdir = project / "voice"
    vdir.mkdir(parents=True, exist_ok=True)
    items = [
        (str(sc.get("id") or f"s{k+1:02d}"),
         str(sc.get("voiceover") or ""))
        for k, sc in enumerate(scenes)]
    items = [(sid, text) for sid, text in items if text]
    import hashlib
    mp = vdir / "meta.json"
    try: meta = _json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError): meta = {}
    for sid, text in items:
        out = vdir / f"{sid}.mp3"
        ident=hashlib.sha256(_json.dumps({"text":text,"config":cfg["voice"]},sort_keys=True).encode()).hexdigest()
        cached=meta.get(sid,{})
        if out.exists() and cached.get("identity")==ident and cached.get("sha256")==hashlib.sha256(out.read_bytes()).hexdigest() and (cfg["voice"]["provider"] != "edge" or out.with_suffix(".words.json").exists()):
            continue
        try:
            res = prov.synthesize(text, out, voice=voice, speed=speed,
                                  live=live)
        except _LiveGateError as e:
            print(f"run voice: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"run voice: provider failed in {sid}: {e}",
                  file=sys.stderr)
            return 3
        dur = res.get("duration_s")
        if dur is None or float(dur) <= 0:
            from stickman.render.composer import _default_probe
            dur = float(_default_probe(out))  # medición real por ffprobe
        meta[sid] = {"duration_s": round(float(dur), 3), "identity":ident, "sha256":hashlib.sha256(out.read_bytes()).hexdigest()}
        mp.write_text(_json.dumps(meta,indent=2), encoding="utf-8")
    (vdir / "meta.json").write_text(
        _json.dumps(meta, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(f"voice ok: {len(meta)} audio files in {vdir}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """`run`: modo banco F9 por defecto; `--stage X` ejecuta una etapa.

    Modo banco: lock exclusivo completo, banco → active → pipeline real
    (script auto → voz todas las escenas → align → stills → compose →
    verify), journal y exit-codes de flow.py (2 gate, 3 fallo reanudable,
    4 lock ocupado). Rework D1: sin --batch produce EXACTAMENTE 1 video;
    `--batch N` (N>=1) itera hasta N; --batch<=0 -> error exit 1 sin
    tocar banco ni proveedores. `--topic T`: single-shot del tema
    EXPLICITO sin tocar el banco (reanudable con el mismo comando).
    `--stage` (etapa suelta, para depurar):
    script|voice|align|stills|compose|verify.
    """
    from stickman.flow import run_bank, run_single_shot, RunBusyError
    project = Path(args.project)
    live = bool(args.live)
    if args.batch is not None and args.batch <= 0:
        print(f"run: --batch must be a positive integer (received "
              f"{args.batch}); without --batch one video is produced",
              file=sys.stderr)
        return 1
    if args.stage:
        stage = args.stage
        if stage not in ("script", "voice", "align", "stills",
                         "compose", "verify"):
            print(f"run --stage {stage}: unknown stage", file=sys.stderr)
            return 1
        # stages sueltos F4-F6 (contrato existente, no toco)
        if stage in ("script", "voice", "stills"):
            return {"script": _run_stage_script,
                    "voice": _run_stage_voice_full,
                    "stills": _run_stage_stills}[stage](project, live)
        # align/compose/verify: ejecutar sobre el proyecto directamente
        if stage == "align":
            return _run_stage_align(project)
        if stage == "compose":
            return _run_stage_compose(project)
        return _run_stage_verify(project)

    if args.resume:
        return _cmd_resume(args)
    from stickman import pipeline as PM
    if args.topic is not None:
        return run_single_shot(project, args.topic, live=live,
                               pipeline=PM.build_pipeline)
    try:
        return run_bank(project, batch=args.batch, live=live,
                        pipeline=PM.build_pipeline)
    except RunBusyError as e:
        print(f"run: {e}", file=sys.stderr)
        return 4


def _run_stage_align(project) -> int:
    import json as _json
    from stickman import align as _align
    script_path = project / "script.json"
    if not script_path.exists():
        print("run align: missing script.json", file=sys.stderr)
        return 1
    try:
        script = _json.loads(script_path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"run align: invalid script ({e})", file=sys.stderr)
        return 3
    cfg = _project_cfg(project)
    if cfg is None:
        return 1
    mode = (cfg.get("align", {}) or {}).get("mode") or "edge-words"
    try:
        meta = {}
        mpath = project / "voice" / "meta.json"
        if mpath.exists():
            meta = _json.loads(mpath.read_text(encoding="utf-8"))
        _align.align_words(script, project, mode=mode, meta=meta)
    except NotImplementedError as e:
        print(f"run align: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"run align: {e}", file=sys.stderr)
        return 3
    print("align ok: .stickman/words.json")
    return 0


def _run_stage_compose(project) -> int:
    import json as _json
    from stickman.render.composer import compose, RenderError
    script_path = project / "script.json"
    if not script_path.exists():
        print("run compose: missing script.json (run `run --stage script` first)", file=sys.stderr)
        return 1
    cfg = _project_cfg(project)
    if cfg is None:
        return 1
    try:
        script = _json.loads(script_path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"run compose: invalid script ({e})", file=sys.stderr)
        return 3
    try:
        meta = _json.loads((project / "voice" / "meta.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("run compose: missing voice/meta.json (run the voice stage: "
              f"{e})", file=sys.stderr)
        return 1
    durs = {sid: float(v.get("duration_s"))
            for sid, v in meta.items()
            if isinstance(v, dict) and v.get("duration_s")}
    try:
        master = compose(project, script, durs, cfg)
    except RenderError as e:
        print(f"run compose: {e}", file=sys.stderr)
        return 3
    print(f"compose ok: {master}")
    return 0


def _run_stage_verify(project) -> int:
    import json as _json
    from stickman import verify as _verify
    master = project / "output" / "master.mp4"
    if not master.exists():
        print("run verify: missing output/master.mp4 (run `run --stage compose` first)", file=sys.stderr)
        return 1
    rep_path = project / ".stickman" / "compose_report.json"
    try:
        exp = _json.loads(rep_path.read_text(encoding="utf-8")).get(
            "expected_duration_s")
    except (OSError, ValueError):
        exp = None
    cfg = _project_cfg(project)
    ok, rep = _verify.verify(master, expected_duration_s=exp, width=cfg["render"]["width"],height=cfg["render"]["height"])
    (project / ".stickman" / "verify_report.json").write_text(
        _json.dumps(rep, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    if not ok:
        fallos = [k for k, v in rep.get("checks", {}).items()
                  if not v.get("ok")]
        print(f"run verify: failed ({', '.join(fallos) or rep.get('mp4')})",
              file=sys.stderr)
        return 3
    print("verify ok")
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    """Reanuda el active (etapas ok se reutilizan; pendientes re-ejecutan).

    Sin active ni banco: exit 0 (nada reanudable, CERO llamadas).
    """
    from stickman.flow import run_bank, RunBusyError
    from stickman import pipeline as PM
    project = Path(args.project)
    live = bool(getattr(args, "live", False))
    if getattr(args, "from_stage", None):
        print("run --from-stage is unavailable; resume uses the saved manifest", file=sys.stderr)
        return 1
    try:
        return run_bank(project, live=live, resume=True,
                        pipeline=PM.build_pipeline)
    except RunBusyError as e:
        print(f"resume: {e}", file=sys.stderr)
        return 4


def _project_cfg(project):
    from stickman import config as _cfg
    try:
        return _cfg.load_config(project)
    except Exception as e:
        print(f"run: project has no valid stickman.toml ({e})",
              file=sys.stderr)
        return None


def _run_stage_script(project, live: bool) -> int:
    import json as _json
    from stickman.scriptx.providers import make_script_provider
    cfg = _project_cfg(project)
    if cfg is None:
        return 1
    try:
        prov = make_script_provider(cfg)
    except Exception as e:
        print(f"run script: {e}", file=sys.stderr)
        return 1
    out = project / "script.json"
    topic = (cfg.get("project", {}).get("slug") or project.name)
    mp = project / ".stickman" / "manifest.json"
    if mp.exists():
        topic = _json.loads(mp.read_text(encoding="utf-8")).get("topic") or topic
    if cfg["script"]["provider"] == "local-advanced":
        from stickman.scriptx.providers import LocalScript
        src = Path(cfg["script"]["from_script"])
        prov = LocalScript(src if src.is_absolute() else project / src)
    try:
        res = prov.draft(topic, out, live=live)
    except RuntimeError as e:  # falta gate live
        print(f"run script: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"run script: provider failed: {e}", file=sys.stderr)
        return 3
    print(f"script ok: {res['script_path']} sha={res['script_sha256'][:12]} "
          f"modelo={res['model']}")
    return 0


def _stills_job_scope(project) -> str:
    """Identidad de trabajo para el checkpoint de stills (rework D2).

    Dos temas distintos NO comparten entradas de caché aunque el script
    (fixture) y los cids sean idénticos: el scope es el occ_id del
    trabajo activo (leído del manifiesto durable). Sin manifiesto
    (`run --stage stills` CLI aislado) queda "" — comportamiento previo.
    """
    import json as _json
    try:
        data = _json.loads((Path(project) / ".stickman" / "manifest.json")
                           .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("occ_id") or "")


def _run_stage_stills(project, live: bool) -> int:
    import json as _json
    script_path = project / "script.json"
    if not script_path.exists():
        print("run stills: missing script.json (run `run --stage script` first)", file=sys.stderr)
        return 1
    from stickman.scriptx import prompts as _pr
    from stickman.stills.factory import make_image_provider
    from stickman.stills import runner as _rn
    cfg = _project_cfg(project)
    if cfg is None:
        return 1
    try:
        script = _json.loads(script_path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"run stills: invalid script ({e})", file=sys.stderr)
        return 3
    sdir = project / "stills"
    sdir.mkdir(parents=True, exist_ok=True)
    try:
        bundle_paths = _pr.build_bundle(script, sdir / "bundle")
    except ValueError as e:
        print(f"run stills: invalid prompt bundle ({e})", file=sys.stderr)
        return 3
    bundle = _rn.load_bundle(sdir / "bundle" / bundle_paths["mapping_path"],
                             sdir / "bundle" / bundle_paths["prompts_path"])
    try:
        prov = make_image_provider(cfg)
    except Exception as e:
        print(f"run stills: {e}", file=sys.stderr)
        return 1
    section = cfg.get("images", {})
    size = section.get("size") or "1536x1024"
    quality = section.get("quality") or "medium"
    try:
        from stickman.stills.runner import ledger_path as _ledger_path
        rep = _rn.run_stills(bundle, prov, sdir / "work", live=live,
                             size=size, quality=quality,
                             job_scope=_stills_job_scope(project),
                             reserve=int(section.get("reserve_regen", 8)),
                             attempts_ledger=_ledger_path(project))
    except Exception as e:
        from stickman.errors import ProviderError as _ProviderError
        if isinstance(e, _ProviderError):
            print(f"run stills: provider failed: {e}", file=sys.stderr)
            return 3
        print(f"run stills: {e}", file=sys.stderr)
        return 2
    print(f"stills ok: done={rep['done']} hard_limit={rep['hard_limit']} "
          f"failed={rep['failed']}")
    return 0


def _cmd_thumbnail(args: argparse.Namespace) -> int:
    from stickman.thumbnailx import make_thumbnail
    try:
        out = make_thumbnail(src=args.from_image,
                             out=(args.out or "thumbnail.png"),
                             hook=(args.hook or ""))
    except ValueError as e:
        print(f"thumbnail: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"thumbnail: {e}", file=sys.stderr)
        return 1
    print(f"thumbnail ok: {out}")
    return 0


def _cmd_clean(args: argparse.Namespace) -> int:
    """Borra derivados (output/, stills/work, voice, .stickman reports)."""
    project = Path(args.project)
    if not args.force and not sys.stdin.isatty():
        print("clean: --force is required in a noninteractive terminal", file=sys.stderr)
        return 1
    import shutil
    borrados = []
    targets = [project / "output", project / "stills" / "work",
               project / "voice"]
    if args.stage:
        allowed = {"compose": [project / "output"],
                   "verify": [project / ".stickman" / "verify_report.json"],
                   "stills": [project / "stills" / "work"],
                   "voice": [project / "voice"]}
        if args.stage not in allowed:
            print(f"clean --stage {args.stage}: unsupported", file=sys.stderr)
            return 1
        targets = allowed[args.stage]
    for t in targets:
        if t.is_dir():
            shutil.rmtree(t)
            borrados.append(str(t))
        elif t.exists():
            t.unlink()
            borrados.append(str(t))
    # manifiesto del active: derivado de ejecución -> se resetea
    man = project / ".stickman" / "manifest.json"
    if man.exists():
        man.unlink()
        borrados.append(str(man))
    for b in borrados:
        print(f"clean: removed {b}")
    print(f"clean ok: {len(borrados)} paths")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logger = logx.get_logger()
    # init exige provider: chequeo aquí para que falle con exit 1
    # incluso si argparse no lo captura (p. ej. API programática).
    if args.cmd == "init":
        return _cmd_init(args)
    if args.cmd == "script":
        from stickman.scriptx import schema as schema_mod
        import json as _json
        try:
            doc = _json.loads(
                Path(args.script_json).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"invalid script: {e}", file=sys.stderr)
            return 3
        errs = schema_mod.validate_docu_en_1(doc)
        if errs:
            for e in errs:
                print(f"error: {e}", file=sys.stderr)
            return 3
        print("valid script (docu-en-1)")
        return 0
    logger.info(f"command received: {args.cmd}")
    if args.cmd == "config":
        import json
        if args.config_cmd == "show":
            try: print(json.dumps(config_mod.load_config(Path.cwd()),ensure_ascii=False,indent=2))
            except Exception as e: print(str(e),file=sys.stderr);return 1
            return 0
        result=config_mod.config_set(Path.cwd(),args.clave,args.valor)
        print(result)
        return 0 if result.startswith("ok:") else 1
    if args.cmd == "check":
        return _cmd_check(args)
    if args.cmd == "calibrate":
        return _cmd_calibrate(args)
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "resume":
        return _cmd_resume(args)
    if args.cmd == "thumbnail":
        return _cmd_thumbnail(args)
    if args.cmd == "clean":
        return _cmd_clean(args)
    if args.cmd == "status":
        return _cmd_status(args)
    print("Unsupported command",file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
