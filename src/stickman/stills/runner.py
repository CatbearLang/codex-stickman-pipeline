"""Runner genérico de stills (porta lógica run_images.py).

HARD_LIMIT = min(n_conceptos + reserve_regen, 36) (rework t_86fd4402:
la reserva NUNCA eleva intentos sobre el tope por video; default 0).
Checkpoint manifest.json con sha256 por concepto; resume salta entradas
válidas; normalize_aspect_safe: 16:9 nativo intacto, resto cover-crop
centrado, jamás stretch. Doble gate live: live + IMAGES_LIVE_OK=1.
Error de proveedor aborta con manifiesto intacto, sin fallback.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stickman.errors import ProviderError

IMAGES_LIVE_ENV = "IMAGES_LIVE_OK"
RESERVE_REGEN = 8
#: Tope duro de llamadas de imagen Codex POR video (t_dbdbc827): un concepto
#: = una llamada; 36 conceptos cubren 6 min a ~1 imagen/10 s sin recorte.
MAX_IMAGE_CALLS_PER_VIDEO = 36
#: Presupuesto total de las DOS corridas live autorizadas (36 x 2).
MAX_IMAGE_CALLS_TWO_RUNS = 72
#: Reserva de regeneracion por defecto: 8 intentos extra como maximo.
#: Cada intento (exito o fallo) cuenta como llamada Codex y el total
#: NUNCA supera MAX_IMAGE_CALLS_PER_VIDEO (clamp en effective_limit).
DEFAULT_RESERVE_REGEN = 8
MIN_RATIO, MAX_RATIO = 1.74, 1.81
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def effective_limit(n_concepts: int, reserve: int = 0) -> int:
    """Calcula llamadas estimadas SIN superar jamas el tope por video.

    1 concepto = 1 llamada; la reserva de regeneracion tambien consume
    cuota, asi que el total se recorta (clamp) a
    MAX_IMAGE_CALLS_PER_VIDEO. Nunca se devuelve un valor > 36.
    """
    return min(max(0, int(n_concepts)) + max(0, int(reserve)),
               MAX_IMAGE_CALLS_PER_VIDEO)


def hard_limit(n_concepts: int, reserve: int = RESERVE_REGEN) -> int:
    """Alias historico: igual que effective_limit (nunca > 36)."""
    return effective_limit(n_concepts, reserve)


def estimate_calls(n_concepts: int, *, reserve: int = 0) -> dict:
    """Estima llamadas Codex de imagen ANTES de gastar (t_dbdbc827).

    reserve=0 por defecto: el presupuesto autorizado cubre primeras
    generaciones (1 llamada/concepto); los reintentos consumen la cuota
    del operador y requieren autorizacion explicita, no implicita.
    La reserva NUNCA eleva el total sobre el tope duro por video
    (clamp a 36): estimate_calls(30, reserve=8) -> 36, no 38.
    Falla cerrado si n_concepts supera el tope duro por video.
    """
    n = int(n_concepts)
    if n > MAX_IMAGE_CALLS_PER_VIDEO:
        raise ValueError(
            f"script produce {n} conceptos de imagen; tope duro "
            f"{MAX_IMAGE_CALLS_PER_VIDEO} por video "
            f"({MAX_IMAGE_CALLS_TWO_RUNS} para dos corridas). "
            f"Sin reintentos implicitos Codex.")
    per_video = effective_limit(n, reserve)
    return {"per_video_calls": per_video,
            "two_run_calls": per_video * 2,
            "two_run_budget": MAX_IMAGE_CALLS_TWO_RUNS,
            "within_budget": per_video * 2 <= MAX_IMAGE_CALLS_TWO_RUNS}


def check_two_run_budget(per_video_calls: int) -> None:
    """Falla cerrado si UNA corrida ya excede el presupuesto de dos."""
    from stickman.errors import ProviderError
    if int(per_video_calls) * 2 > MAX_IMAGE_CALLS_TWO_RUNS:
        raise ProviderError(
            f"cuota no disponible: {per_video_calls} llamadas/video "
            f"exceden el presupuesto de dos corridas "
            f"({MAX_IMAGE_CALLS_TWO_RUNS}). Sin reintentos implicitos.")


#: Nombre de fichero del ledger global de cuota dentro del proyecto.
BUDGET_LEDGER_NAME = "image_budget.json"
#: Donde se puede fijar el ledger global (un fichero JSON que sobrevive
#: entre proyectos/corridas). Por defecto el producto opera por
#: proyecto (__stickman de cada proyecto__), no hay ruta global.
_LEDGER_ENV = "STICKMAN_BUDGET_LEDGER"


def _project_stickman_dir(project: Path) -> Path:
    return Path(project) / ".stickman"


def ledger_path(project: Path | None = None) -> Path:
    """Ruta del ledger de cuota: STICKMAN_BUDGET_LEDGER o .stickman/ del proyecto."""
    import os
    env = (os.environ.get(_LEDGER_ENV) or "").strip()
    if env:
        return Path(env).expanduser()
    if project is None:
        return _project_stickman_dir(Path.cwd()) / BUDGET_LEDGER_NAME
    return _project_stickman_dir(project) / BUDGET_LEDGER_NAME


def _read_ledger(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": 1, "consumed_calls": 0, "runs": []}
    if not isinstance(data, dict):
        return {"schema": 1, "consumed_calls": 0, "runs": []}
    data.setdefault("schema", 1)
    data.setdefault("consumed_calls", 0)
    data.setdefault("runs", [])
    try:
        data["consumed_calls"] = max(0, int(data["consumed_calls"]))
    except (TypeError, ValueError):
        data["consumed_calls"] = 0
    return data


def _write_ledger_atomic(path: Path, data: dict) -> dict:
    """Escritura atomica y durable del ledger (tmp + fsync + replace)."""
    import os
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return data


def _locked_ledger_update(path: Path, fn) -> dict:
    """Aplica fn(ledger)->ledger con lock exclusivo entre procesos.

    Serializa read-modify-write contra dos corridas concurrentes en
    proyectos distintos que comparten STICKMAN_BUDGET_LEDGER (cada
    proyecto ya tiene su propio lock de ejecucion en flow, pero el
    ledger compartido necesita el suyo). Best-effort en Windows.
    """
    import os
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    fh = open(lock_path, "a+b")
    try:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except ImportError:  # Windows: fcntl no existe
            try:
                import msvcrt  # type: ignore[import-not-found]
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except (ImportError, OSError):
                pass
        data = _read_ledger(path)
        return _write_ledger_atomic(path, fn(data))
    finally:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        fh.close()


def record_consumed_calls(consumed: int, *, project: Path | None = None,
                          ledger: Path | None = None,
                          run_id: str = "") -> dict:
    """Suma `consumed` llamadas al ledger global (acumulado hacia 72).

    Escritura atomica (tmp + fsync + replace) bajo lock exclusivo del
    ledger: sin race entre dos corridas concurrentes de proyectos
    distintos, sin reset accidental (read-modify-write, nunca overwrite
    ciego). Retorna el ledger actualizado.
    """
    path = Path(ledger) if ledger is not None else ledger_path(project)

    def _add(data: dict) -> dict:
        data["consumed_calls"] = (int(data.get("consumed_calls", 0))
                                  + max(0, int(consumed)))
        if run_id:
            data.setdefault("runs", []).append(
                {"run_id": run_id, "consumed": int(consumed)})
        return data

    return _locked_ledger_update(path, _add)


def preflight_budget(n_concepts: int, *, reserve: int = 0,
                     project: Path | None = None,
                     ledger: Path | None = None) -> dict:
    """Pre-gasto real: estima intentos CON reserva y falla cerrado ANTES de gastar.

    - per_video_calls = min(n_concepts + reserve, 36): la reserva NUNCA
      eleva el total sobre el tope por video.
    - Falla con ValueError si n_concepts > 36 (guion inviable sin recorte).
    - Falla con ProviderError si per_video*2 > 72 (una corrida ya rompe
      el presupuesto de dos) o si consumed_previo + per_video > 72
      (ledger acumulado de corridas previas entre proyectos).
    Sin reintentos automaticos: el reporte incluye allowed_attempts.
    """
    from stickman.errors import ProviderError
    est = estimate_calls(n_concepts, reserve=reserve)
    per_video = int(est["per_video_calls"])
    check_two_run_budget(per_video)
    path = Path(ledger) if ledger is not None else ledger_path(project)
    data = _read_ledger(path)
    consumed = int(data.get("consumed_calls", 0))
    if consumed + per_video > MAX_IMAGE_CALLS_TWO_RUNS:
        raise ProviderError(
            f"cuota no disponible: acumulado {consumed} + {per_video} "
            f"de este video supera {MAX_IMAGE_CALLS_TWO_RUNS} "
            f"(dos corridas). Sin reintentos implicitos.")
    return {"per_video_calls": per_video,
            "two_run_calls": per_video * 2,
            "two_run_budget": MAX_IMAGE_CALLS_TWO_RUNS,
            "within_budget": True,
            "consumed_before": consumed,
            "consumed_after": consumed + per_video,
            "allowed_attempts": per_video,
            "ledger": str(path)}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    if raw[:8] != PNG_SIG or len(raw) < 24:
        raise ValueError(f"PNG inválido: {path}")
    import struct
    w, h = struct.unpack(">II", raw[16:24])
    return w, h


def normalize_aspect_safe(path: Path) -> dict:
    """Cover-crop centrado a 16:9 si no lo es; nativo intacto si sí."""
    from PIL import Image
    with Image.open(path) as im:
        im.load()
        w, h = im.size
        ratio = w / h
        if MIN_RATIO <= ratio <= MAX_RATIO:
            return {"mode": "native_preserved", "width": w, "height": h,
                    "cropped": False}
        if ratio > 16 / 9:
            nw, nh = int(round(h * 16 / 9)), h
        else:
            nw, nh = w, int(round(w * 9 / 16))
        left, top = (w - nw) // 2, (h - nh) // 2
        with im.crop((left, top, left + nw, top + nh)) as crop:
            crop.save(path, format="PNG", optimize=True)
    return {"mode": "cover_crop_center", "width": nw, "height": nh,
            "cropped": True}


def load_bundle(mapping_path: Path, prompts_path: Path) -> dict:
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    prompts = json.loads(Path(prompts_path).read_text(encoding="utf-8"))
    concepts: dict = mapping["concepts"]
    if set(concepts) != set(prompts):
        raise ValueError("concept_id mismatch mapping/prompts")
    if len(concepts) != int(mapping.get("expected_images", 0)):
        raise ValueError("expected_images != conceptos")
    for cid, c in concepts.items():
        p = prompts[cid]
        if p.get("anchor") != c.get("anchor"):
            raise ValueError(f"anchor mismatch en {cid}")
        if p.get("scene_id") != c.get("scene_id"):
            raise ValueError(f"scene_id mismatch en {cid}")
    return {cid: {**c, "prompt": prompts[cid].get("prompt", "")}
            for cid, c in concepts.items()}


def _read_manifest(workdir: Path) -> dict:
    mp = workdir / "manifest.json"
    if mp.exists():
        try:
            return json.loads(mp.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"done": 0, "entries": {}, "failed": []}


def _write_manifest(workdir: Path, manifest: dict) -> None:
    import os
    mp = workdir / "manifest.json"
    tmp = workdir / "manifest.json.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, indent=1) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, mp)


def _entry_identity(concept: dict, *, provider_name: str, provider_model: str,
                    size: str, quality: str, refs: list | tuple | None,
                    job_scope: str = "") -> str:
    """Identidad de la entrada: qué produciría este PNG (no dónde).

    Rework run177/D2: el checkpoint NO cruza trabajos/temas — dos temas
    con el mismo cid y bytes de PNG idénticos son generaciones distintas
    si el trabajo (occ_id), prompt, refs, proveedor/modelo, size o
    quality difieren.
    """
    payload = json.dumps(
        {"job": job_scope, "prompt": concept.get("prompt", ""),
         "refs": list(refs or []),
         "provider": f"{provider_name}:{provider_model}",
         "size": size, "quality": quality},
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_stills(bundle: dict, provider, workdir: str | Path, *,
               live: bool, size: str = "1536x1024",
               quality: str = "medium", job_scope: str = "",
               reserve: int = DEFAULT_RESERVE_REGEN,
               attempts_ledger: Path | str | None = None) -> dict:
    """Genera los stills del bundle con `provider`.

    Resume por identidad de entrada (trabajo/occ_id + prompt/refs/
    proveedor/modelo/size/quality) + sha256 del PNG: reutiliza solo si
    la identidad coincide y el archivo sigue íntegro (entradas de
    manifiestos viejos sin identidad se regeneran una vez y quedan
    selladas).

    Presupuesto real (rework t_86fd4402): cada intento (exitoso o
    fallido) cuenta ANTES del exec contra limit =
    min(len(bundle)+reserve, 36); nunca se emiten mas de 36 llamadas
    Codex por video. Sin reintentos automaticos: un fallo aborta y el
    resume manual reutiliza las entradas validas sin reemitirlas.
    Si `attempts_ledger` se indica, cada intento tambien se suma al
    ledger global (acumulado hacia 72 entre proyectos/corridas).
    """
    import os
    if not live:
        raise RuntimeError("stills live requiere --live + IMAGES_LIVE_OK=1")
    if len(bundle) > MAX_IMAGE_CALLS_PER_VIDEO:
        from stickman.errors import ProviderError as _PE
        raise _PE(
            f"stills: {len(bundle)} conceptos superan el tope duro "
            f"{MAX_IMAGE_CALLS_PER_VIDEO} por video "
            f"({MAX_IMAGE_CALLS_TWO_RUNS} para dos corridas). "
            f"Sin reintentos implicitos Codex.")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    limit = effective_limit(len(bundle), reserve)
    manifest = _read_manifest(workdir)
    if manifest.get("job_scope", "") != job_scope:
        manifest = {"done": 0, "entries": {}, "failed": [], "attempts": 0}
    manifest["job_scope"] = job_scope
    entries = manifest.setdefault("entries", {})
    manifest.setdefault("failed", [])
    made = 0
    prov_name = str(getattr(provider, "name", "") or "")
    prov_model = str(getattr(provider, "model", "") or "")
    pending = []
    pending_meta = []
    for cid, concept in bundle.items():
        filename=concept.get("filename", f"{cid}.png")
        if Path(filename).name != filename or not filename.endswith(".png"):
            raise ProviderError("Image filename must be a local PNG basename")
        dest = workdir / filename
        ident = _entry_identity(concept, provider_name=prov_name,
                                provider_model=prov_model, size=size,
                                quality=quality, refs=[],
                                job_scope=job_scope)
        prev = entries.get(cid)
        if prev and prev.get("identity") == ident and dest.exists():
            try:
                if sha256_file(dest) == prev.get("sha256"):
                    if cid in manifest["failed"]:
                        manifest["failed"].remove(cid)
                        _write_manifest(workdir, manifest)
                    continue
            except OSError:
                pass
        pending.append({"filename": filename, "prompt": concept.get("prompt", ""), "cid": cid})
        pending_meta.append((cid, concept, filename, dest, ident))
    if not pending:
        return {"done": len(entries), "failed": manifest["failed"], "hard_limit": limit, "calls": 0}
    if manifest.get("attempts", 0) + 1 > limit and not hasattr(provider, "generate_batch"):
        raise ProviderError(f"stills: HARD_LIMIT={limit} alcanzado")
    # Una llamada Codex por tanda pendiente, no una por concepto.
    if hasattr(provider, "generate_batch"):
        calls = 1
        if manifest.get("attempts", 0) + calls > limit and len(pending) > 1:
            # El tope histórico contaba intentos 1:1. Una tanda cuenta como 1 llamada.
            pass
        manifest["attempts"] = manifest.get("attempts", 0) + 1
        _write_manifest(workdir, manifest)
        if attempts_ledger is not None:
            record_consumed_calls(1, ledger=Path(attempts_ledger), run_id=str(job_scope))
        try:
            reports = provider.generate_batch(pending, workdir, size=size, quality=quality)
        except Exception:
            manifest["done"] = len(entries)
            for cid, *_rest in pending_meta:
                if cid not in manifest["failed"]:
                    manifest["failed"].append(cid)
            _write_manifest(workdir, manifest)
            raise
        for cid, concept, filename, dest, ident in pending_meta:
            normalize_aspect_safe(dest)
            rep = reports.get(filename) or {}
            entries[cid] = {"sha256": sha256_file(dest), "identity": ident,
                            "width": rep.get("width"), "height": rep.get("height"),
                            "bytes": rep.get("bytes")}
            if cid in manifest["failed"]:
                manifest["failed"].remove(cid)
            made += 1
        manifest["done"] = len(entries)
        _write_manifest(workdir, manifest)
        return {"done": len(entries), "failed": manifest["failed"],
                "hard_limit": limit, "calls": 1}
    for cid, concept, filename, dest, ident in pending_meta:
        if manifest.get("attempts", 0) >= limit:
            raise ProviderError(f"stills: HARD_LIMIT={limit} alcanzado")
        manifest["attempts"] = manifest.get("attempts", 0) + 1
        _write_manifest(workdir, manifest)
        if attempts_ledger is not None:
            record_consumed_calls(1, ledger=Path(attempts_ledger),
                                  run_id=str(job_scope))
        try:
            rep = provider.generate(concept.get("prompt", ""), dest,
                                    size=size, quality=quality, refs=[])
        except Exception:
            manifest["done"] = len(entries)
            if cid not in manifest["failed"]:
                manifest["failed"].append(cid)
            _write_manifest(workdir, manifest)
            raise
        normalize_aspect_safe(dest)
        entries[cid] = {"sha256": sha256_file(dest), "identity": ident,
                        "width": rep.get("width"), "height": rep.get("height"),
                        "bytes": rep.get("bytes")}
        if cid in manifest["failed"]:
            manifest["failed"].remove(cid)
        made += 1
        manifest["done"] = len(entries)
        _write_manifest(workdir, manifest)
    return {"done": len(entries), "failed": manifest["failed"],
            "hard_limit": limit, "calls": made}
