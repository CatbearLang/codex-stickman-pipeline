"""stickman/manifest.py — manifiesto por trabajo activo (plan §4.4).

Sustituye mtime por sha256. Invalidación por ÁMBITOS de configuración
(STAGE_CONFIG_SCOPE): un cambio irrelevante NO regenera etapas pagas.

Etapa        secciones stickman.toml que la invalidan
script       script, project
voice        voice, script, project
align        voice, align
stills       images, script
compose      render, voice, images
verify       render
thumbnail    render, images

[project] (language/target_minutes) es entrada efectiva del guion y de
la voz: cambiarla invalida script+voice (y align transitivamente), pero
NUNCA stills/compose/verify (rework D2: sin regeneración paga injustificada).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1

# scopes §4.4: secciones de config que invalidan cada etapa
STAGE_CONFIG_SCOPE: dict[str, tuple[str, ...]] = {
    "script": ("script", "project"),
    "voice": ("voice", "script", "project"),
    "align": ("voice", "align"),
    "stills": ("images", "script"),
    "compose": ("render", "voice", "images"),
    "verify": ("render",),
    "thumbnail": ("render", "images"),
}

STAGES = ("script", "voice", "align", "stills", "compose", "verify",
          "thumbnail")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(p: str | Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def config_sections_sha(project_dir: str | Path) -> dict[str, str]:
    """sha256 POR SECCIÓN de la config efectiva (defaults + stickman.toml).

    Rework D2: conecta el manifiesto con los scopes §4.4. revalidate
    compara estos shas por sección; un cambio irrelevante (p. ej.
    [render].xfade_s) no marca stale etapas pagas. Config ausente o
    inválida -> {} (el llamador no siembra baseline).
    """
    import json as _json
    from stickman import config as _cfgmod
    try:
        cfg = _cfgmod.load_config(project_dir)
    except (_cfgmod.ConfigError, OSError):
        return {}
    return {sec: hashlib.sha256(_json.dumps(
                cfg[sec], sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest() for sec in sorted(cfg)}


def new_manifest(*, slug: str, occ_id: str, topic: str,
                 config_sha256: str, script_sha256: str,
                 config_sections_sha: dict[str, str] | None = None
                 ) -> "Manifest":
    data = {
        "schema": SCHEMA, "slug": slug, "occ_id": occ_id, "topic": topic,
        "config_sha256": config_sha256, "script_sha256": script_sha256,
        "stages": {}}
    if config_sections_sha:
        data["config_sections_sha"] = dict(config_sections_sha)
    return Manifest(data)


class Manifest:
    """Manifiesto durable del trabajo activo (atomic write + fsync)."""

    def __init__(self, data: dict) -> None:
        self.data = data

    @property
    def stages(self) -> dict:
        return self.data.setdefault("stages", {})

    # -- escrituras ------------------------------------------------------
    def mark_ok(self, stage: str, inputs: dict[str, str],
                outputs: dict[str, str], *, tool: str = "stickman",
                note: str = "") -> None:
        self.stages[stage] = {
            "status": "ok", "at": _now_iso(),
            "inputs": dict(inputs), "outputs": dict(outputs),
            "tool": tool, "note": note}

    def mark(self, stage: str, status: str, *, note: str = "") -> None:
        prev = self.stages.get(stage, {})
        self.stages[stage] = {
            "status": status, "at": _now_iso(),
            "inputs": prev.get("inputs", {}),
            "outputs": prev.get("outputs", {}),
            "tool": prev.get("tool", "stickman"), "note": note}

    def save(self, project_dir: str | Path) -> Path:
        d = Path(project_dir)
        d.mkdir(parents=True, exist_ok=True)
        out = d / ".stickman" / "manifest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".json.tmp")
        payload = json.dumps(self.data, ensure_ascii=False, indent=1) + "\n"
        tmp.write_bytes(payload.encode("utf-8"))
        with open(tmp, "r+b") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, out)
        return out

    @classmethod
    def load(cls, project_dir: str | Path) -> "Manifest":
        p = Path(project_dir) / ".stickman" / "manifest.json"
        if not p.exists():
            raise FileNotFoundError(f"sin manifiesto: {p}")
        return cls(json.loads(p.read_text(encoding="utf-8")))

    # -- invalidación ----------------------------------------------------
    def revalidate(self, project_dir: str | Path, *,
                   inputs_sha: dict[str, str] | None = None,
                   script_sha: str | None = None,
                   config_sha: str | None = None,
                   config_sections_sha: dict[str, str] | None = None,
                   ) -> list[str]:
        """Marca stale y devuelve las etapas a re-ejecutar.

        - Etapa ok cuyos outputs faltan o cuyo sha difiere -> stale.
        - Cambio de config_sha256 global -> stale en todas las etapas
          con scope (§4.4); si solo cambia una sección, ver abajo.
        - Cambio en una sección de config dentro del scope de la etapa
          -> stale (solo esas etapas; voz/stills intactos si el cambio
          es irrelevante, p. ej. [render].xfade_s).
        - Cambio de script_sha invalida voice/align/stills/compose/verify
          (scopes transitan: script es input de todos menos thumbnail).
        """
        import json as _json
        project = Path(project_dir)
        stale: list[str] = []
        # 1) outputs: falta o sha difiere -> stale
        for st, info in self.stages.items():
            if info.get("status") != "ok":
                continue
            for rel, want_sha in (info.get("outputs") or {}).items():
                p = project / rel
                if not p.exists() or sha256_file(p) != want_sha:
                    stale.append(st)
                    break
        # 1b) inputs declarados cambiados por el llamador
        if inputs_sha:
            for st, info in self.stages.items():
                if info.get("status") != "ok":
                    continue
                want = info.get("inputs", {})
                if any(want.get(k) != v for k, v in inputs_sha.items()
                       if k in want):
                    stale.append(st)
        # 2) cambio de config global (hash completo)
        if config_sha and config_sha != self.data.get("config_sha256"):
            self.data["config_sha256"] = config_sha
            for st in self.stages:
                if self.stages.get(st, {}).get("status") == "ok":
                    stale.append(st)
        # 3) cambio de script invalida TODO lo downstream (regla de
        #    invalidate(), docstring §4.4: script es input de todas las
        #    etapas). Sin baseline previo (manifiesto sembrado antes de
        #    que existiera script.json): SOLO se siembra el sha, nada
        #    se invalida (no hay cambio medible; los outputs siguen
        #    cubiertos por la regla 1).
        prev_script = self.data.get("script_sha256")
        if script_sha and script_sha != prev_script:
            self.data["script_sha256"] = script_sha
            if prev_script:
                for st in STAGES:
                    if st != "script" and self.stages.get(st, {}).get("status") == "ok":
                        stale.append(st)
        # 4) cambio de config por secciones (scopes §4.4). Sólo se comparan
        #    secciones CON baseline previo (manifiesto viejo sin baseline:
        #    se siembra, nada se invalida). [script]/[project] cambian el
        #    CONTENIDO (como script_sha): invalidan todas menos script.
        if config_sections_sha:
            old = self.data.get("config_sections_sha") or {}
            changed = {sec for sec, sha in config_sections_sha.items()
                       if old.get(sec) and old[sec] != sha}
            if changed & {"script", "project"}:
                # contenido nuevo (otro video): TODO se regenera,
                # incluido script de raíz con la nueva config
                for st in STAGES:
                    if self.stages.get(st, {}).get("status") == "ok":
                        stale.append(st)
            else:
                for sec in changed:
                    for st, scope in STAGE_CONFIG_SCOPE.items():
                        if sec in scope and self.stages.get(st, {}).get(
                                "status") == "ok":
                            stale.append(st)
            self.data["config_sections_sha"] = dict(config_sections_sha)
        deps={"script":("voice","align","stills","compose","verify","thumbnail"),"voice":("align","compose","verify"),"align":("compose","verify"),"stills":("compose","verify","thumbnail"),"compose":("verify",)}
        pending=list(stale)
        while pending:
            for dep in deps.get(pending.pop(),()):
                if dep not in stale:
                    stale.append(dep);pending.append(dep)
        dedup = sorted(set(stale))
        for st in dedup:
            self.mark(st, "stale",
                      note="invalidado por cambio de inputs/config")
        return dedup


def invalidate(stages: dict, old_sections: dict[str, str],
               new_sections: dict[str, str]) -> list[str]:
    """Función pura (RED F9): etapas stale al cambiar secciones de config.

    Regla §4.4: el guion es INPUT de voice/align/stills/compose/verify/
    thumbnail — cambiar [script] invalida todas las etapas menos script
    (que se regenera fresca). Otras secciones solo por scope.
    """
    changed = {s for s in set(old_sections) | set(new_sections)
               if old_sections.get(s) != new_sections.get(s)}
    if "script" in changed:
        return sorted(set(STAGES) - {"script"})
    out: set[str] = set()
    for st, scope in STAGE_CONFIG_SCOPE.items():
        if changed & set(scope):
            out.add(st)
    return sorted(out)
