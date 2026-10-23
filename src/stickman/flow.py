"""stickman/flow.py — orquestación banco→…→MP4 (plan F9).

LOCK DE EJECUCIÓN COMPLETA (ruling brief 1 + revisión fase 1): el lock
exclusivo del banco se toma ANTES del acquire y se conserva durante
TODAS las llamadas de proveedor/render hasta complete/fail. Un segundo
proceso sale RunBusyError SIN llamadas externas. Un crash (SIGKILL/
os._exit) libera el lock del SO y el siguiente proceso reanuda el
active sin consumir otro tema.

Semántica:
- Banco vacío -> 0, CERO llamadas al pipeline (tests lo imponen).
- run normal (batch=None): UN video; complete al terminar bien.
- batch=N: hasta N temas, stop-on-fail (exit del fallo, no continúa).
- fail de proveedor -> journal fail + active intacto (reanudable),
  exit 3. LiveGateError -> exit 2. RunBusyError -> exit 4 (CLI).
- El pipeline es inyectable (doubles en tests); la CLI lo construye
  desde la config real (proveedores reales).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from stickman.bank import Occurrence
from stickman.errors import LiveGateError


class RunBusyError(RuntimeError):
    """Otro proceso está generando (lock de ejecución completo)."""


class _BusyContext:
    """Contexto del lock de ejecución: UN fd, TODA la corrida."""

    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self.fh = None

    def __enter__(self):
        fh = open(self.lock_path, "a+b")
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:  # Windows: fcntl no existe
            import msvcrt  # type: ignore[import-not-found]
            lock = getattr(msvcrt, "locking", None)
            nblck = getattr(msvcrt, "LK_NBLCK", None)
            if lock is None or nblck is None:  # pragma: no cover
                fh.close()
                raise RunBusyError(
                    "plataforma sin soporte de lock de ejecución")
            fh.seek(0)
            try:
                lock(fh.fileno(), nblck, 1)
            except OSError:
                fh.close()
                raise RunBusyError(
                    "otro proceso está generando este proyecto (bloqueado); "
                    "reintente cuando termine") from None
        except OSError:
            fh.close()
            raise RunBusyError(
                "otro proceso está generando este proyecto (bloqueado); "
                "reintente cuando termine") from None
        self.fh = fh
        return self

    def __exit__(self, *exc):
        fh = self.fh
        if fh is None:
            return False
        self.fh = None
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        fh.close()
        return False


def run_one(project: Path, occ: Occurrence, bank,  # TopicBank | _NoBank
            pipeline, manifest, *, live: bool,
            journal: bool = True) -> tuple[int, Path | None]:
    """Ejecuta todas las etapas del active y completa o falla.

    pipeline(project, occ, manifest, live) -> Path del MP4.
    LiveGateError -> journal fail + exit 2; proveedor/render -> fail
    reanudable (active intacto) + exit 3; éxito -> complete + exit 0.

    journal=False (single-shot `run --topic`): NO toca journal/history
    del banco (no es trabajo del banco); el manifiesto queda durable
    para reanudar con el mismo comando tras un fallo de proveedor.
    """
    try:
        mp4 = pipeline(project, occ, manifest, live)
    except LiveGateError as e:
        if journal:
            bank.fail(occ, str(e), _fh=True)
        print(f"run: falta autorización live: {e}", file=sys.stderr)
        return 2, None
    except Exception as e:  # fallo de proveedor/render: reanudable
        if journal:
            bank.fail(occ, repr(e), _fh=True)
        # el manifiesto queda durable con las etapas ok (resume por sha)
        print(f"run: fallo en {occ.topic!r}: {e}", file=sys.stderr)
        return 3, None
    if journal:
        bank.complete(occ, mp4, _fh=True)
    try:
        (project / ".stickman" / "manifest.json").unlink()
    except OSError:
        pass
    print(f"ok: {occ.topic} -> {mp4}")
    return 0, Path(mp4)


# ------------------------------------------------------------------ single-shot


def run_single_shot(project: str | Path, topic: str, *,
                    live: bool = False, pipeline=None) -> int:
    """`run --topic T`: single-shot del tema EXPLICITO sin tocar el banco.

    Plan §4.1 línea 155 («single-shot sin tocar el banco») y pendiente
    de revisión 2: antes el flag se aceptaba y procesaba el primer tema
    del banco. Ahora:
    - banco byte-identical: SIN reserve ni journal (duplicados y
      contador del banco intactos para la corrida real);
    - rechaza con exit 1 si hay un trabajo activo del banco (sin
      descartar nada: reanudar después con `run` normal);
    - occ_id determinista: sha1("topic:<topic>")[:16]; el manifiesto es
      durable, un fallo de proveedor se reanuda con el MISMO comando;
    - éxito limpia el manifiesto; sin history (no es trabajo del banco).
    """
    from stickman import logx
    import hashlib as _hashlib
    project = Path(project)
    tnorm = topic.strip()
    if not tnorm:
        print("run --topic: el tema no puede estar vacío", file=sys.stderr)
        return 1
    if project.exists() and (project / ".stickman" / "active.json").exists():
        print("run --topic: hay un trabajo activo del banco en este "
              "proyecto; reanúdalo con `stickman run` o `stickman resume` "
              "antes de un single-shot (no se descarta nada)",
              file=sys.stderr)
        return 1
    logx.get_logger().info(
        f"run_single_shot project={project} topic={tnorm!r} live={live}")
    occ_id = _hashlib.sha1(f"topic:{tnorm}".encode("utf-8")).hexdigest()[:16]
    occ = Occurrence(occ_id=occ_id, topic=tnorm, index=-1,
                     bank_sha256="", reserved_at="")
    state=project/".stickman"
    state.mkdir(parents=True,exist_ok=True)
    try:
        with _BusyContext(state/"bank.lock"):
            manifest = _new_topic_manifest(project, occ)
            return run_one(project, occ, _NoBank(), pipeline, manifest, live=live, journal=False)[0]
    except RunBusyError as e:
        print(str(e),file=sys.stderr);return 4


class _NoBank:
    """Sustituto de TopicBank para single-shot: contabilidad NO-op.

    run_one(journal=False) no la invoca; existe como guarda: si el
    flujo intentara journalizar, fallaría ruidosamente en vez de tocar
    el banco.
    """

    def fail(self, *a, **k):  # pragma: no cover - guarda
        raise RuntimeError("single-shot: journal del banco prohibido")

    def complete(self, *a, **k):  # pragma: no cover - guarda
        raise RuntimeError("single-shot: journal del banco prohibido")


def _new_topic_manifest(project: Path, occ: Occurrence):
    """Manifiesto durable del single-shot (reutilizable tras un fallo)."""
    from stickman import manifest as MF
    mpath = project / ".stickman" / "manifest.json"
    if mpath.exists():
        try:
            man = MF.Manifest.load(project)
            if (man.data.get("occ_id") == occ.occ_id
                    and man.data.get("mode") == "topic"):
                return man
        except (ValueError, OSError):
            pass
    cfg_sha = ""
    script_sha = ""
    try:
        cfg_path = project / "stickman.toml"
        if cfg_path.exists():
            cfg_sha = MF.sha256_file(cfg_path)
        sp = project / "script.json"
        if sp.exists():
            script_sha = MF.sha256_file(sp)
    except OSError:
        pass
    man = MF.new_manifest(slug=tnorm_slug(occ.topic), occ_id=occ.occ_id,
                          topic=occ.topic, config_sha256=cfg_sha,
                          script_sha256=script_sha,
                          config_sections_sha=MF.config_sections_sha(project))
    man.data["mode"] = "topic"
    man.save(project)
    return man


def tnorm_slug(topic: str) -> str:
    return topic[:40]


def run_bank(project: str | Path, *, batch: int | None = None,
             stage: str = "all", live: bool = False,
             resume: bool = False, pipeline=None,
             pipeline_factory=None) -> int:
    """Modo banco: 0/1 trabajo, stop-on-fail, lock completo.

    Rework D1 (spec línea 15 + brief ruling 3): UNA corrida produce
    EXACTAMENTE un video (resume incluido: el active es ese único
    trabajo). Solo un --batch N explícito itera hasta N temas.
    batch<=0 -> error ANTES de reservar o llamar (banco intacto), exit 1.

    pipeline           : callable único (tests con double).
    pipeline_factory   : factory(occ) -> callable (tests por tema).
    Sin ninguno        : CLI real (proveedores desde stickman.toml).
    """
    from stickman import logx
    if batch is not None and (not isinstance(batch, int) or batch <= 0):
        print(f"run: --batch debe ser un entero positivo (recibido {batch!r})",
              file=sys.stderr)
        return 1
    project = Path(project)
    from stickman.bank import TopicBank
    bank = TopicBank(project / "banco tema.txt", project / ".stickman")
    logx.get_logger().info(f"run_bank project={project} batch={batch}")
    if resume and not bank.active_path.exists():
        print("No active bank job to resume.")
        return 0
    max_works = batch if batch is not None else 1
    with _BusyContext(bank.lock_path):
        done = 0
        while True:
            occ = bank.acquire(_fh=True)  # lock en mano: sin re-bloqueo
            if occ is None:
                if done == 0:
                    print("banco vacío: 0 videos, 0 llamadas a proveedores")
                return 0
            manifest = _load_manifest(project, occ)
            pipe = (pipeline_factory(occ) if pipeline_factory is not None
                    else pipeline)
            rc, _mp4 = run_one(project, occ, bank, pipe, manifest, live=live)
            if rc != 0:
                return rc  # stop-on-fail / single run
            done += 1
            if done >= max_works:
                return 0


def _load_manifest(project: Path, occ: Occurrence):
    """Manifiesto del active (resume) o nuevo; durable desde ya."""
    from stickman import manifest as MF
    mpath = project / ".stickman" / "manifest.json"
    if mpath.exists():
        try:
            man = MF.Manifest.load(project)
            if man.data.get("occ_id") == occ.occ_id:
                return man
        except (ValueError, OSError):
            pass
    cfg_sha = ""
    script_sha = ""
    try:
        cfg_path = project / "stickman.toml"
        if cfg_path.exists():
            cfg_sha = MF.sha256_file(cfg_path)
        sp = project / "script.json"
        if sp.exists():
            script_sha = MF.sha256_file(sp)
    except OSError:
        pass
    man = MF.new_manifest(slug=occ.topic[:40], occ_id=occ.occ_id,
                          topic=occ.topic, config_sha256=cfg_sha,
                          script_sha256=script_sha,
                          config_sections_sha=MF.config_sections_sha(project))
    man.save(project)
    return man
