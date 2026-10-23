"""tests/test_topic_singleshot.py — `run --topic` single-shot REAL (plan §4.1).

Contrato exigido por revisión 2 (fase-3-review-1.md) y pendiente de
release del worker: `run --topic T2` procesa EXACTAMENTE el tema T2:
- single-shot SIN tocar el banco (byte-identical, cero journal/reserve);
- sin active.json (no hay reserva que reanudar ni contabilidad del banco);
- conflicto con trabajo activo del banco: rechazo exit 1 SIN descartar
  nada (active intacto, banco intacto, cero llamadas);
- argumento inválido (tema vacío): exit 1 y CERO llamadas;
- --live se conserva (gate LiveGateError -> exit 2);
- recuperación: fallo de proveedor deja manifiesto con etapas ok;
  re-ejecutar el mismo comando reanuda por manifiesto (no regenera);
- éxito: manifiesto limpiado, sin history (no es trabajo del banco).

Todo con dobles del builder (mismo contrato que test_flow_bank): $0,
sin red. render-fixture, no prueba llamadas live.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stickman.cli import main

STAGES = ("script", "voice", "align", "stills", "compose", "verify")


def _proyecto(tmp_path: Path, topics: list[str]) -> Path:
    p = tmp_path / "Mi Proyecto"
    p.mkdir()
    (p / "banco tema.txt").write_bytes(
        ("\n".join(topics) + ("\n" if topics else "")).encode("utf-8"))
    (p / ".stickman").mkdir()
    (p / "stickman.toml").write_text(
        '[script]\nprovider = "local-advanced"\n', encoding="utf-8")
    return p


class Dbl:
    """Builder doble que registra el tema y produce un MP4."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, project, occ, manifest, live):
        self.calls.append(occ.topic)
        mp4 = project / "output" / f"{occ.occ_id}.mp4"
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"mp4")
        return mp4


def _bank_sha(p: Path) -> str:
    return hashlib.sha256((p / "banco tema.txt").read_bytes()).hexdigest()


# --- tema exacto, banco byte-identical ---------------------------------------


def test_topic_procesa_el_tema_exacto(tmp_path, monkeypatch):
    from stickman import pipeline as PM
    proj = _proyecto(tmp_path, ["T1", "T2", "T3"])
    dbl = Dbl()
    monkeypatch.setattr(PM, "build_pipeline", dbl)
    rc = main(["run", "--project", str(proj), "--topic", "T2"])
    assert rc == 0
    assert dbl.calls == ["T2"]  # el tema pedido, NO el primero del banco


def test_topic_banco_byte_identical_y_sin_reserva(tmp_path, monkeypatch):
    from stickman import pipeline as PM
    proj = _proyecto(tmp_path, ["¿Por qué el cerebro borra el día?", "T2"])
    sha_antes = _bank_sha(proj)
    monkeypatch.setattr(PM, "build_pipeline", Dbl())
    rc = main(["run", "--project", str(proj), "--topic", "T2"])
    assert rc == 0
    assert _bank_sha(proj) == sha_antes  # byte-identical (UTF-8 incluido)
    state = proj / ".stickman"
    assert not (state / "active.json").exists()
    assert not (state / "bank.journal.jsonl").exists()
    assert not (state / "history.jsonl").exists()


def test_topic_banco_queda_operativo_despues(tmp_path, monkeypatch):
    """Tras el single-shot, `run` normal procesa T1 del banco intacto."""
    from stickman import pipeline as PM
    proj = _proyecto(tmp_path, ["T1", "T2"])
    monkeypatch.setattr(PM, "build_pipeline", Dbl())
    assert main(["run", "--project", str(proj), "--topic", "T2"]) == 0
    dbl2 = Dbl()
    monkeypatch.setattr(PM, "build_pipeline", dbl2)
    assert main(["run", "--project", str(proj)]) == 0
    assert dbl2.calls == ["T1"]
    assert (proj / "banco tema.txt").read_text(encoding="utf-8") == "T2\n"


# --- conflicto con trabajo activo: rechazo sin descartar ---------------------


def test_topic_rechaza_con_activo_del_banco_sin_descartar(tmp_path,
                                                          monkeypatch):
    from stickman import pipeline as PM
    from stickman.bank import TopicBank
    proj = _proyecto(tmp_path, ["T1", "T2"])
    bank = TopicBank(proj / "banco tema.txt", proj / ".stickman")
    occ = bank.acquire()  # reserva T1 (active durable)
    assert occ.topic == "T1"
    sha_antes = _bank_sha(proj)
    dbl = Dbl()
    monkeypatch.setattr(PM, "build_pipeline", dbl)
    rc = main(["run", "--project", str(proj), "--topic", "T2"])
    assert rc == 1
    assert dbl.calls == []  # CERO llamadas
    active = json.loads((proj / ".stickman" / "active.json")
                        .read_text(encoding="utf-8"))
    assert active["occ_id"] == occ.occ_id  # active intacto
    assert _bank_sha(proj) == sha_antes  # banco intacto
    # y el banco sigue reanudable:
    monkeypatch.setattr(PM, "build_pipeline", Dbl())
    assert main(["run", "--project", str(proj)]) == 0  # procesa T1


# --- argumentos inválidos: exit 1, cero llamadas ------------------------------


def test_topic_vacio_rechazado_sin_llamadas(tmp_path, monkeypatch):
    from stickman import pipeline as PM
    proj = _proyecto(tmp_path, ["T1"])
    sha_antes = _bank_sha(proj)
    dbl = Dbl()
    monkeypatch.setattr(PM, "build_pipeline", dbl)
    rc = main(["run", "--project", str(proj), "--topic", "   "])
    assert rc == 1
    assert dbl.calls == []
    assert _bank_sha(proj) == sha_antes
    assert not (proj / ".stickman" / "active.json").exists()


# --- gates live y fallos -------------------------------------------------------


def test_topic_conserva_gate_live(tmp_path, monkeypatch):
    from stickman import pipeline as PM
    from stickman.errors import LiveGateError
    proj = _proyecto(tmp_path, [])

    def sube_gate(project, occ, manifest, live):
        assert live is True  # --live llegó al builder
        raise LiveGateError("IMAGES_LIVE_OK=1 requerido")

    monkeypatch.setattr(PM, "build_pipeline", sube_gate)
    assert main(["run", "--project", str(proj), "--topic", "Solo",
                 "--live"]) == 2
    assert not (proj / ".stickman" / "active.json").exists()


def test_topic_fallo_proveedor_deja_manifiesto_y_reanuda(tmp_path,
                                                         monkeypatch):
    from stickman import pipeline as PM
    proj = _proyecto(tmp_path, [])

    estado_visto: dict = {}

    class DblFalla:
        def __call__(self, project, occ, manifest, live):
            estado_visto.setdefault("occ", occ.occ_id)
            manifest.mark_ok("script", {}, {})
            manifest.save(project)
            raise RuntimeError("fallo inyectado del proveedor")

    monkeypatch.setattr(PM, "build_pipeline", DblFalla())
    rc1 = main(["run", "--project", str(proj), "--topic", "Tema X"])
    assert rc1 == 3
    man = json.loads((proj / ".stickman" / "manifest.json")
                     .read_text(encoding="utf-8"))
    assert man["stages"]["script"]["status"] == "ok"  # recuperable

    # reanudación: mismo comando; el manifiesto con etapas ok se REUTILIZA
    # (occ_id determinista por tema; el doble solo marca las restantes)
    class DblReanuda:
        def __call__(self, project, occ, manifest, live):
            assert occ.occ_id == estado_visto["occ"]
            assert manifest.stages["script"]["status"] == "ok"
            for st in STAGES[1:]:
                manifest.mark_ok(st, {}, {})
                manifest.save(project)
            mp4 = project / "output" / "final.mp4"
            mp4.parent.mkdir(parents=True, exist_ok=True)
            mp4.write_bytes(b"mp4")
            return mp4

    monkeypatch.setattr(PM, "build_pipeline", DblReanuda())
    rc2 = main(["run", "--project", str(proj), "--topic", "Tema X"])
    assert rc2 == 0
    assert (proj / "output" / "final.mp4").exists()
    assert not (proj / ".stickman" / "manifest.json").exists()  # limpio


def test_topic_exito_limpia_manifiesto(tmp_path, monkeypatch):
    from stickman import pipeline as PM
    proj = _proyecto(tmp_path, [])
    monkeypatch.setattr(PM, "build_pipeline", Dbl())
    assert main(["run", "--project", str(proj), "--topic", "Solo"]) == 0
    assert (proj / "output").exists()
    assert not (proj / ".stickman" / "manifest.json").exists()
    # sin rastro en la contabilidad del banco:
    from stickman.bank import read_history
    assert read_history(proj / ".stickman") == []
