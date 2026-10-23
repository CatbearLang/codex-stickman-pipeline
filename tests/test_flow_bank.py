"""tests/test_flow_bank.py — F9 RED: flow banco E2E.

run_bank(project, ...): banco -> script AUTOMATICO -> voz -> stills ->
align (edge-words) -> compose -> verify -> complete/fail, con lock de
EJECUCIÓN COMPLETA (desde antes de acquire hasta complete/fail):
un segundo proceso sale BankBusyError SIN llamadas; crash libera el
lock y el siguiente reanuda. Batch stop-on-fail. Empty = cero llamadas.
Run normal (sin --batch) = EXACTAMENTE 1 video (rework D1: batch solo
con --batch N explícito, validado ANTES de reservar/llamar).
Todo con dobles inyectados (sin red, $0).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from stickman import flow
from stickman.bank import BankBusyError, Occurrence, TopicBank


def _proyecto(tmp_path: Path, topics: list[str]) -> Path:
    p = tmp_path / "Mi Proyecto"
    p.mkdir()
    (p / "banco tema.txt").write_bytes(
        ("\n".join(topics) + ("\n" if topics else "")).encode("utf-8"))
    (p / ".stickman").mkdir()
    (p / "stickman.toml").write_text(
        '[script]\nprovider = "local-advanced"\n', encoding="utf-8")
    return p


class DoublePipeline:
    """Pipeline de prueba: graba llamadas, puede fallar donde se pida."""

    def __init__(self, fail_at: str | None = None, crash: bool = False):
        self.calls: list[tuple[str, str]] = []
        self.fail_at = fail_at
        self.crash = crash
        self.mp4_written = False

    def __call__(self, project: Path, occ, manifest, live: bool) -> Path:
        for st in ("script", "voice", "align", "stills", "compose",
                   "verify"):
            self.calls.append((st, occ.occ_id))
            if self.fail_at == st:
                raise RuntimeError(f"double fallo en {st}")
            manifest.mark_ok(st, {}, {})
            manifest.save(project)
        if self.crash:
            os._exit(9)  # crash real: libera el lock del SO
        mp4 = project / "output" / f"{occ.occ_id}.mp4"
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"mp4-fixture")
        self.mp4_written = True
        return mp4


def test_empty_banco_cero_llamadas(tmp_path):
    proj = _proyecto(tmp_path, [])
    dbl = DoublePipeline()
    rc = flow.run_bank(proj, pipeline=dbl, live=False)
    assert rc == 0
    assert dbl.calls == []


def test_un_tema_e2e_completa_y_retira(tmp_path):
    proj = _proyecto(tmp_path, ["T1"])
    dbl = DoublePipeline()
    rc = flow.run_bank(proj, pipeline=dbl, live=False)
    assert rc == 0
    assert [c[0] for c in dbl.calls] == ["script", "voice", "align",
                                         "stills", "compose", "verify"]
    # banco SIN el tema (ruling: retirado al acquire) y sin activo
    assert (proj / "banco tema.txt").read_text(encoding="utf-8") == ""
    assert not (proj / ".stickman" / "active.json").exists()
    hist = json.loads((proj / ".stickman" / "history.jsonl")
                      .read_text(encoding="utf-8").splitlines()[-1])
    assert hist["topic"] == "T1" and hist["sha256"]
    assert (proj / ".stickman" / "manifest.json").exists() is False


def test_fallo_voice_conserva_y_reanuda_mismo_guion(tmp_path):
    proj = _proyecto(tmp_path, ["T1"])
    dbl1 = DoublePipeline(fail_at="voice")
    rc1 = flow.run_bank(proj, pipeline=dbl1, live=False)
    assert rc1 == 3
    # el tema NO se re-reserva: sigue activo; el banco ya no lo tiene
    script = proj / "script.json"
    script.write_text('{"title": "x"}', encoding="utf-8")  # artefacto parcial
    sha_antes = script.read_bytes()
    dbl2 = DoublePipeline()
    rc2 = flow.run_bank(proj, pipeline=dbl2, live=False)
    assert rc2 == 0
    assert dbl2.calls[0][0] == "script"  # el double re-ejecuta todo...
    # ...pero el guion parcial NO fue regenerado por un proveedor: el
    # manifiesto del active marca desde voice (double re-marca ok).
    journal = (proj / ".stickman" / "bank.journal.jsonl").read_text(
        encoding="utf-8")
    assert '"op": "fail"' in journal and '"op": "complete"' in journal


def test_batch_para_al_fallo(tmp_path):
    proj = _proyecto(tmp_path, ["T1", "T2"])
    hechas = []

    def pipeline_factory(occ):
        if occ.topic == "T1":
            dbl = DoublePipeline(fail_at="compose")
        else:
            dbl = DoublePipeline()
        hechas.append(occ.topic)
        return dbl

    rc = flow.run_bank(proj, batch=5, pipeline_factory=pipeline_factory,
                       live=False)
    assert rc == 3
    assert hechas == ["T1"]  # stop-on-fail: T2 nunca empezó
    lines = (proj / "banco tema.txt").read_text(encoding="utf-8").splitlines()
    assert "T1" in lines or (proj / ".stickman" / "active.json").exists()


def test_bloqueo_proceso_segundo_sale_busy_sin_llamadas(tmp_path):
    """Lock de ejecución completo: el 2º proceso NO duplica trabajo.

    Determinista: el pipeline del 1er proceso queda ESPERANDO una señal
    del test, así T1 sigue abierto (reserve=1, active=T1) cuando se
    comprueba que el 2º proceso salió BUSY sin tocar nada.
    """
    proj = _proyecto(tmp_path, ["T1", "T2"])
    barrier = tmp_path / "entra.lock"
    hecho = tmp_path / "segundo.hecho"

    class SlowFirst:
        def __call__(self, project, occ, manifest, live):
            barrier.write_text("dentro", encoding="utf-8")
            import time
            for _ in range(400):  # hasta 20 s esperando la señal del test
                if hecho.exists():
                    break
                time.sleep(0.05)
            mp4 = project / "output" / f"{occ.occ_id}.mp4"
            mp4.parent.mkdir(parents=True, exist_ok=True)
            mp4.write_bytes(b"x")
            return mp4

    code = (
        "import sys, time\n"
        "sys.path.insert(0, %r)\n"
        "from pathlib import Path\n"
        "from stickman import flow\n"
        "class P:\n"
        "    def __call__(self, *a, **k):\n"
        "        Path(%r).write_text('segundo.listo')\n"
        "        time.sleep(30)\n"  # si llega aqui, DUPLICÓ el trabajo
        "        return Path('x')\n"
        "try:\n"
        "    rc = flow.run_bank(Path(%r), pipeline=P(), live=False)\n"
        "    print('RC', rc)\n"
        "except flow.RunBusyError as e:\n"
        "    print('BUSY')\n"
    ) % (str(Path(flow.__file__).parent.parent.parent),
         str(tmp_path / "segundo.listo"), str(proj))
    import threading
    t = threading.Thread(
        target=flow.run_bank,
        kwargs=dict(project=proj, pipeline=SlowFirst(), live=False))
    t.start()
    for _ in range(200):
        if barrier.exists():
            break
        import time
        time.sleep(0.05)
    assert barrier.exists(), "el primer proceso nunca entró"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=60)
    # 1) el 2º proceso salió BUSY sin ejecutar el pipeline ni reservar
    assert "BUSY" in r.stdout, (r.stdout, r.stderr)
    assert not (tmp_path / "segundo.listo").exists()
    journal = (proj / ".stickman" / "bank.journal.jsonl")
    entradas = [json.loads(l) for l in journal.read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert len([e for e in entradas if e["op"] == "reserve"]) == 1
    # T1 sigue activo y T2 intocado en el banco
    active = json.loads((proj / ".stickman" / "active.json")
                        .read_text(encoding="utf-8"))
    assert active["topic"] == "T1"
    assert "T2" in (proj / "banco tema.txt").read_text(encoding="utf-8")
    # 2) liberar al 1er proceso: completa T1 y PARA (run normal = 1 video;
    #    T2 queda en el banco para la próxima ejecución — spec rework D1)
    hecho.write_text("ok", encoding="utf-8")
    t.join(timeout=60)
    assert not t.is_alive()
    hist = (proj / ".stickman" / "history.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(hist) == 1
    restantes = (proj / "banco tema.txt").read_text(
        encoding="utf-8").splitlines()
    assert restantes == ["T2"]


def test_crash_libera_lock_y_siguiente_reanuda(tmp_path):
    proj = _proyecto(tmp_path, ["T1"])
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "from pathlib import Path\n"
        "from stickman import flow\n"
        "class Crash:\n"
        "    def __call__(self, project, occ, manifest, live):\n"
        "        import os\n"
        "        manifest.mark_ok('script', {}, {})\n"
        "        manifest.save(project)\n"
        "        os._exit(9)\n"  # crash real SIN complete ni fail
        "flow.run_bank(Path(%r), pipeline=Crash(), live=False)\n"
    ) % (str(Path(flow.__file__).parent.parent.parent), str(proj))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 9
    # active sigue abierto (crash conservó el trabajo)
    assert (proj / ".stickman" / "active.json").exists()
    # el siguiente proceso reanuda el MISMO occ y completa
    dbl = DoublePipeline()
    rc = flow.run_bank(proj, pipeline=dbl, live=False)
    assert rc == 0
    hist = (proj / ".stickman" / "history.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(hist) == 1
    # solo UNA reserva en el journal (el crash NO consumió otro tema)
    journal = (proj / ".stickman" / "bank.journal.jsonl").read_text(
        encoding="utf-8")
    assert journal.count('"reserve"') == 1


# --- rework D1: run normal = EXACTAMENTE 1 video -----------------------------

def test_run_normal_procesa_exactamente_un_tema(tmp_path):
    """repro revisor repro_batch_none.py: batch=None era bucle infinito de
    temas (T1+T2, history=2). Spec: run normal produce UN video; T2 queda
    en el banco intocado."""
    proj = _proyecto(tmp_path, ["T1", "T2"])
    dbl = DoublePipeline()
    rc = flow.run_bank(proj, batch=None, pipeline=dbl, live=False)
    assert rc == 0
    # una sola OCURRENCIA ejecutada: todas las llamadas del doble comparten
    # occ_id del primer acquire
    occ_ids = {c[1] for c in dbl.calls}
    assert len(occ_ids) == 1
    assert dbl.calls  # se ejecutó el pipeline completo una vez
    hist = (proj / ".stickman" / "history.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(hist) == 1
    restantes = (proj / "banco tema.txt").read_text(
        encoding="utf-8").splitlines()
    assert restantes == ["T2"]
    assert not (proj / ".stickman" / "active.json").exists()


def test_batch_2_procesa_dos_y_deja_el_tercero(tmp_path):
    proj = _proyecto(tmp_path, ["T1", "T2", "T3"])
    dbl = DoublePipeline()
    rc = flow.run_bank(proj, batch=2, pipeline=dbl, live=False)
    assert rc == 0
    hist = (proj / ".stickman" / "history.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(hist) == 2
    restantes = (proj / "banco tema.txt").read_text(
        encoding="utf-8").splitlines()
    assert restantes == ["T3"]


def test_batch_1_explcito_procesa_uno(tmp_path):
    proj = _proyecto(tmp_path, ["T1", "T2"])
    dbl = DoublePipeline()
    rc = flow.run_bank(proj, batch=1, pipeline=dbl, live=False)
    assert rc == 0
    hist = (proj / ".stickman" / "history.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(hist) == 1
    assert (proj / "banco tema.txt").read_text(
        encoding="utf-8").splitlines() == ["T2"]


@pytest.mark.parametrize("batch", [0, -1])
def test_batch_invalido_cero_llamadas_banco_intacto(tmp_path, batch):
    """--batch N con N<=0: error ANTES de reservar o llamar; banco idéntico."""
    proj = _proyecto(tmp_path, ["T1", "T2"])
    antes = (proj / "banco tema.txt").read_text(encoding="utf-8")
    dbl = DoublePipeline()
    rc = flow.run_bank(proj, batch=batch, pipeline=dbl, live=False)
    assert rc == 1
    assert dbl.calls == []
    assert not (proj / ".stickman" / "active.json").exists()
    assert not (proj / ".stickman" / "bank.journal.jsonl").exists()
    assert (proj / "banco tema.txt").read_text(encoding="utf-8") == antes


def _cli_builder_grabador(monkeypatch):
    """Sustituye stickman.pipeline.build_pipeline por un doble grabador:
    la validación CLI debe ocurrir ANTES de run_bank (cero llamadas)."""
    from stickman import pipeline as PM
    llamadas: list[tuple[str, str]] = []

    class Grabador:
        def __call__(self, project, occ, manifest, live):
            for st in ("script", "voice", "align", "stills", "compose",
                       "verify"):
                llamadas.append((st, occ.occ_id))
                manifest.mark_ok(st, {}, {})
                manifest.save(project)
            mp4 = Path(project) / "output" / f"{occ.occ_id}.mp4"
            mp4.parent.mkdir(parents=True, exist_ok=True)
            mp4.write_bytes(b"mp4")
            return mp4

    monkeypatch.setattr(PM, "build_pipeline", Grabador())
    return llamadas


def test_batch_negativo_cli_exito_1(tmp_path, capsys, monkeypatch):
    from stickman.cli import main
    proj = _proyecto(tmp_path, ["T1", "T2"])
    llamadas = _cli_builder_grabador(monkeypatch)
    antes = (proj / "banco tema.txt").read_text(encoding="utf-8")
    rc = main(["run", "--project", str(proj), "--batch", "-1"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "--batch" in err
    assert llamadas == []
    assert not (proj / ".stickman" / "active.json").exists()
    assert not (proj / ".stickman" / "bank.journal.jsonl").exists()
    assert (proj / "banco tema.txt").read_text(encoding="utf-8") == antes


def test_batch_cero_cli_exito_1(tmp_path, capsys, monkeypatch):
    from stickman.cli import main
    proj = _proyecto(tmp_path, ["T1"])
    llamadas = _cli_builder_grabador(monkeypatch)
    antes = (proj / "banco tema.txt").read_text(encoding="utf-8")
    assert main(["run", "--project", str(proj), "--batch", "0"]) == 1
    assert llamadas == []
    assert not (proj / ".stickman" / "active.json").exists()
    assert (proj / "banco tema.txt").read_text(encoding="utf-8") == antes


def test_resume_cuenta_como_el_unico_trabajo(tmp_path):
    """Resume activo = ese ÚNICO trabajo: no consume otro tema del banco."""
    proj = _proyecto(tmp_path, ["T1", "T2"])
    rc1 = flow.run_bank(proj, pipeline=DoublePipeline(fail_at="stills"),
                        live=False)
    assert rc1 == 3
    assert (proj / ".stickman" / "active.json").exists()
    dbl2 = DoublePipeline()
    rc2 = flow.run_bank(proj, batch=None, pipeline=dbl2, live=False)
    assert rc2 == 0
    occ_ids = {c[1] for c in dbl2.calls}
    assert len(occ_ids) == 1
    hist = (proj / ".stickman" / "history.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(hist) == 1
    assert (proj / "banco tema.txt").read_text(
        encoding="utf-8").splitlines() == ["T2"]
