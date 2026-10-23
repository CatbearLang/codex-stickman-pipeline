"""F3 RED: banco recuperable (brief ruling 1: retiro EN acquire,
tras journal+active durables; complete solo registra historial y
limpia active, NUNCA retira de nuevo)."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from stickman.bank import BankEditedError, Occurrence, TopicBank, read_history

VENV_PY = str(Path(sys.executable).resolve())


def make_bank(tmp_path, lines):
    bank = tmp_path / "banco tema.txt"
    bank.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    state = tmp_path / ".stickman"
    return bank, state


def test_retiro_en_acquire_no_en_complete(tmp_path):
    bank, state = make_bank(tmp_path, ["A", "A", "B"])
    tb = TopicBank(bank, state)
    occ1 = tb.acquire()
    assert occ1 is not None and occ1.topic == "A"
    # el retiro ocurre en acquire: el banco ya no tiene 3 líneas
    rest = bank.read_text(encoding="utf-8").splitlines()
    assert rest == ["A", "B"], rest
    # active + journal durables
    assert (state / "active.json").exists()
    assert (state / "bank.journal.jsonl").exists()
    # complete NO retira de nuevo: el banco queda igual
    tb.complete(occ1, tmp_path / "video.mp4")
    assert bank.read_text(encoding="utf-8").splitlines() == ["A", "B"]
    assert not (state / "active.json").exists()
    hist = read_history(state)
    assert hist and hist[0]["occ_id"] == occ1.occ_id


def test_crash_real_sigkill_conserva_activo(tmp_path):
    bank, state = make_bank(tmp_path, ["A", "B"])
    child = subprocess.Popen(
        [VENV_PY, "-c",
         "import sys; sys.path.insert(0, 'src');"
         "from pathlib import Path;"
         "from stickman.bank import TopicBank;"
         f"tb = TopicBank(Path({str(bank)!r}), Path({str(state)!r}));"
         "occ = tb.acquire(); print(occ.occ_id, flush=True);"
         "import time; time.sleep(60)"],
        cwd=str(Path.cwd()), stdout=subprocess.PIPE, text=True)
    try:
        occ_id = child.stdout.readline().strip()
        assert occ_id, "el hijo no reservó"
        for _ in range(100):
            if (state / "active.json").exists():
                break
            time.sleep(0.05)
        child.send_signal(getattr(signal, "SIGKILL", signal.SIGTERM))
        child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()
    occ2 = TopicBank(bank, state).acquire()
    assert occ2 is not None and occ2.occ_id == occ_id  # reanuda, no consume B
    assert occ2.topic == "A"


def test_fail_conserva_activo_y_banco(tmp_path):
    bank, state = make_bank(tmp_path, ["A", "B"])
    tb = TopicBank(bank, state)
    occ = tb.acquire()
    tb.fail(occ, "proveedor caído")
    assert (state / "active.json").exists()  # reanudable
    assert bank.read_text(encoding="utf-8").splitlines() == ["B"]
    occ2 = TopicBank(bank, state).acquire()
    assert occ2.occ_id == occ.occ_id  # mismo trabajo, sin consumir B


def test_concurrencia_dos_procesos_lock_excluye_segundo(tmp_path):
    # Lock de ejecución completo (brief ruling 1): el segundo proceso NUNCA
    # reserva otro tema mientras el primero trabaja. Prueba real: el hijo
    # mantiene el lock 15 s; el padre con blocking=False recibe BankBusyError
    # en vez de reservar/duplicar. Usa script en fichero (try/except
    # multilínea no cabe en `python -c` de una línea).
    import textwrap
    pytest.importorskip("fcntl") if os.name != "nt" else None
    bank, state = make_bank(tmp_path, ["A", "B", "C"])
    lock = state / "bank.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        import msvcrt
        def _hold_lock(path):
            fh = open(path, "a+b")
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            print("held", flush=True)
            time.sleep(15)
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            fh.close()
        hold = subprocess.Popen(
            [VENV_PY, "-c",
             "import msvcrt, time;"
             f"fh = open({str(lock)!r}, 'a+b');"
             "fh.seek(0);"
             "msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1);"
             "print('held', flush=True); time.sleep(15)"],
            stdout=subprocess.PIPE, text=True)
    else:
        hold = subprocess.Popen(
            [VENV_PY, "-c",
             "import fcntl, time;"
             f"fh = open({str(lock)!r}, 'a+b');"
             "fcntl.flock(fh.fileno(), fcntl.LOCK_EX);"
             "print('held', flush=True); time.sleep(15)"],
            stdout=subprocess.PIPE, text=True)
    probe = tmp_path / "busy_probe.py"
    probe.write_text(textwrap.dedent(f"""\
        import sys
        sys.path.insert(0, {str(Path.cwd() / 'src')!r})
        from pathlib import Path
        from stickman.bank import TopicBank, BankBusyError
        tb = TopicBank(Path({str(bank)!r}), Path({str(state)!r}))
        try:
            tb.acquire(blocking=False)
            print('RESERVO-MAL')
        except BankBusyError:
            print('BUSY-OK')
        """), encoding="utf-8")
    try:
        assert hold.stdout.readline().strip() == "held"
        r = subprocess.run(
            [VENV_PY, str(probe)],
            cwd=str(Path.cwd()), capture_output=True, text=True, timeout=30)
        assert "BUSY-OK" in r.stdout, r.stdout + r.stderr
    finally:
        hold.kill()
        hold.wait(timeout=10)
    # Dos reservas SECUENCIALES retiran líneas distintas sin duplicar occ
    tb_a = TopicBank(bank, state)
    occ_a = tb_a.acquire()
    tb_a.complete(occ_a, tmp_path / "va.mp4")
    occ_b = TopicBank(bank, state).acquire()
    assert (occ_a.topic, occ_a.occ_id) != (occ_b.topic, occ_b.occ_id)
    rest = bank.read_text(encoding="utf-8").splitlines()
    assert rest == ["C"]  # se retiraron exactamente A y B


def test_banco_vacio_retorna_none_sin_efectos(tmp_path):
    bank, state = make_bank(tmp_path, ["", "   ", ""])
    assert TopicBank(bank, state).acquire() is None
    assert not (state / "active.json").exists()
    journal = state / "bank.journal.jsonl"
    assert not journal.exists() or "reserve" not in journal.read_text()


def test_utf8_duplicados_occ_distinto_y_hash_en_numeral(tmp_path):
    src = Path("fixtures/banco_demo.txt")
    raw = src.read_bytes()
    raw.decode("utf-8")  # fixture es UTF-8 válido
    bank = tmp_path / "banco tema.txt"
    bank.write_bytes(raw)
    state = tmp_path / ".stickman"
    tb = TopicBank(bank, state)
    occ1 = tb.acquire()
    assert occ1.topic == "How does a paper airplane fly?"
    occ_f = tb.fail(occ1, "x")  # noqa
    tb2 = TopicBank(bank, state)
    # tras fail el active se conserva: reanuda el mismo
    assert tb2.acquire().occ_id == occ1.occ_id
    # '#' es tema literal, no comentario
    temas = [l for l in bank.read_text(encoding="utf-8-sig").splitlines()
             if l.strip()]
    assert any(l.startswith("#") for l in temas)


def test_duplicados_generan_occ_distintos(tmp_path):
    bank, state = make_bank(tmp_path, ["A", "A"])
    tb = TopicBank(bank, state)
    occ1 = tb.acquire()
    tb.complete(occ1, tmp_path / "v1.mp4")
    occ2 = TopicBank(bank, state).acquire()
    assert occ1.topic == occ2.topic == "A"
    assert occ1.occ_id != occ2.occ_id


def test_edicion_externa_en_complete_no_borra_nada(tmp_path):
    bank, state = make_bank(tmp_path, ["A", "B"])
    tb = TopicBank(bank, state)
    occ = tb.acquire()  # retira "A" -> banco ["B"]
    # el usuario edita el banco mientras el trabajo está activo
    bank.write_text("B\nA-nuevo-del-usuario\n", encoding="utf-8")
    tb.complete(occ, tmp_path / "v.mp4")  # complete NUNCA toca el banco
    assert bank.read_text(encoding="utf-8").splitlines() == [
        "B", "A-nuevo-del-usuario"]
    assert not (state / "active.json").exists()


def test_history_registra_mp4_y_sha(tmp_path):
    bank, state = make_bank(tmp_path, ["A"])
    tb = TopicBank(bank, state)
    occ = tb.acquire()
    mp4 = tmp_path / "v.mp4"
    mp4.write_bytes(b"fake-mp4-bytes")
    tb.complete(occ, mp4)
    hist = read_history(state)
    assert hist[0]["topic"] == "A" and hist[0]["mp4"].endswith("v.mp4")
    assert len(hist[0]["sha256"]) == 64


def test_active_corrupto_se_recupera_desde_journal(tmp_path):
    bank, state = make_bank(tmp_path, ["A", "B"])
    tb = TopicBank(bank, state)
    occ = tb.acquire()
    (state / "active.json").write_text("{corrupto", encoding="utf-8")
    occ2 = TopicBank(bank, state).acquire()
    assert occ2 is not None and occ2.occ_id == occ.occ_id
    assert isinstance(occ2, Occurrence)


def test_journal_append_es_durable_y_trazable(tmp_path):
    bank, state = make_bank(tmp_path, ["A"])
    tb = TopicBank(bank, state)
    occ = tb.acquire()
    tb.fail(occ, "boom")
    ops = [json.loads(l)["op"] for l in
           (state / "bank.journal.jsonl").read_text(
               encoding="utf-8").splitlines()]
    assert ops == ["reserve", "fail"]
    assert all("at" in json.loads(l) for l in
               (state / "bank.journal.jsonl").read_text(
                   encoding="utf-8").splitlines())
    assert os.path.exists(state / "bank.journal.jsonl")
