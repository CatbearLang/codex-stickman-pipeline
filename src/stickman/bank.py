"""Banco de temas recuperable (plan §4.7 con enmienda del brief ruling 1).

Semántica APROBADA (el brief corrige al plan §4.7/F3):
- `acquire` con lock: si hay active.json válido (o recuperable desde el
  journal) lo devuelve (reanudar, sin consumir tema). Si no, retira la
  primera línea pendiente del banco DESPUÉS de journal+active durables.
- `complete` NUNCA retira del banco: registra historial y borra active.
- `fail` conserva active y banco para reanudar.
- Lock de ejecución completo: toda mutación journal+banco+active bajo
  lock exclusivo multiplataforma (fcntl/msvcrt).
- Crash (SIGKILL real) libera el lock del SO; el siguiente proceso
  reanuda el active sin consumir otro tema.
- Duplicados textuales = ocurrencias separadas con occ_id único durable
  (sha1(topic_normalizado:contador_monotono)[:16]).
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class BankError(Exception):
    pass


class BankEditedError(BankError):
    pass


class BankBusyError(BankError):
    """Otro proceso mantiene el lock de ejecución: no duplicar el activo."""


@dataclass(frozen=True)
class Occurrence:
    occ_id: str
    topic: str
    index: int
    bank_sha256: str
    reserved_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _locked(lock_path: Path, *, blocking: bool):
    """Lock exclusivo con modo no-bloqueante opcional (concurrencia)."""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as fh:
        try:
            import fcntl  # POSIX (macOS)
            flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            try:
                fcntl.flock(fh.fileno(), flags)
            except BlockingIOError:
                yield None
                return
            try:
                yield fh
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            return
        except ImportError:
            pass
        import msvcrt  # Windows
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK if not blocking else msvcrt.LK_LOCK, 1)
        except OSError:
            yield None
            return
        try:
            yield fh
        finally:
            fh.seek(0)
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass


@contextmanager
def lock_bank(lock_path: Path):
    """Lock exclusivo multiplataforma (stdlib: fcntl/msvcrt)."""
    with _locked(lock_path, blocking=True) as fh:
        yield fh


def read_history(state_dir: Path) -> list[dict]:
    hist = Path(state_dir) / "history.jsonl"
    if not hist.exists():
        return []
    out = []
    for line in hist.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


class TopicBank:
    def __init__(self, bank_path: Path, state_dir: Path) -> None:
        self.bank_path = Path(bank_path)
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.state_dir / "bank.journal.jsonl"
        self.active_path = self.state_dir / "active.json"
        self.history_path = self.state_dir / "history.jsonl"
        self.lock_path = self.state_dir / "bank.lock"

    # -- utilidades internas -------------------------------------------
    def _read_lines(self) -> tuple[list[str], str]:
        raw = self.bank_path.read_bytes() if self.bank_path.exists() else b""
        text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        sha = hashlib.sha256(raw).hexdigest()
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        return lines, sha

    def _append_journal(self, entry: dict) -> None:
        with open(self.journal_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _write_active(self, occ: Occurrence) -> None:
        tmp = self.active_path.with_suffix(".json.tmp")
        payload = json.dumps({
            "occ_id": occ.occ_id, "topic": occ.topic, "index": occ.index,
            "bank_sha256": occ.bank_sha256,
            "reserved_at": occ.reserved_at}, ensure_ascii=False)
        tmp.write_bytes(payload.encode("utf-8"))
        with open(tmp, "r+b") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.active_path)
        # fsync del directorio en POSIX (durabilidad del rename); en macOS
        # abrir un directorio con open() falla -> se omite sin error.
        try:
            dfd = os.open(self.state_dir, os.O_RDONLY)
        except OSError:
            dfd = None
        if dfd is not None:
            try:
                os.fsync(dfd)
            except OSError:
                pass
            finally:
                os.close(dfd)

    def _read_active(self) -> dict | None:
        if not self.active_path.exists():
            return None
        try:
            data = json.loads(self.active_path.read_text(encoding="utf-8"))
            if not all(k in data for k in ("occ_id", "topic", "index")):
                return None
            return data
        except (ValueError, OSError):
            return None

    def _journal_entries(self) -> list[dict]:
        if not self.journal_path.exists():
            return []
        out = []
        for line in self.journal_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
        return out

    def _journal_open(self, occ_id: str) -> bool:
        """True si el trabajo sigue abierto: último evento reserve o fail.

        fail conserva el activo para reanudar (brief ruling 1); solo
        complete lo cierra.
        """
        last = None
        for e in self._journal_entries():
            if e.get("occ_id") == occ_id:
                last = e.get("op")
        return last in ("reserve", "fail")

    def _journal_count(self, op: str) -> int:
        return sum(1 for e in self._journal_entries() if e.get("op") == op)

    def _last_reserve(self) -> dict | None:
        last = None
        for e in self._journal_entries():
            if e.get("op") == "reserve":
                last = e
        return last

    def _rewrite_bank_without_index(self, lines: list[str],
                                    index: int) -> None:
        kept = [l for i, l in enumerate(lines) if i != index]
        text = "\n".join(kept) + ("\n" if kept else "")
        tmp = self.bank_path.with_suffix(".txt.tmp")
        tmp.write_bytes(text.encode("utf-8"))
        with open(tmp, "r+b") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.bank_path)

    # -- API pública ----------------------------------------------------
    def acquire(self, *, blocking: bool = True, _fh=None) -> Occurrence | None:
        """Reserva (retira) el primer tema pendiente, o reanuda el activo.

        Banco vacío -> None (el llamador avisa, exit 0, cero proveedor).
        Con blocking=False y otro proceso con el lock, lanza BankBusyError
        en vez de esperar/duplicar: el segundo proceso NUNCA reserva otro
        tema mientras el primero trabaja (brief: lock de ejecución completo).
        _fh: lock YA tomado por el llamador (flow.run_bank lo mantiene
        durante TODA la ejecución); entonces NO se re-bloquea (flock del
        mismo proceso sobre otro fd se bloquearía a sí mismo).
        """
        if _fh is not None:
            return self._acquire_impl()
        with _locked(self.lock_path, blocking=blocking) as fh:
            if fh is None:
                raise BankBusyError(
                    "otro proceso mantiene el banco; reintente cuando termine")
            return self._acquire_impl()

    def _acquire_impl(self) -> Occurrence | None:
        active = self._read_active()
        if active and self._journal_open(active["occ_id"]):
            return Occurrence(
                occ_id=active["occ_id"], topic=active["topic"],
                index=int(active.get("index", 0)),
                bank_sha256=active.get("bank_sha256", ""),
                reserved_at=active.get("reserved_at", ""))
        if active and not self._journal_open(active["occ_id"]):
            # journal manda: trabajo ya cerrado, limpiar active huérfano
            try:
                self.active_path.unlink()
            except OSError:
                pass
            active = None
        if active is None:
            # active corrupto/ausente pero journal con reserve abierto:
            # regenerar active (idempotente por occ_id)
            last = self._last_reserve()
            if last is not None and self._journal_open(last["occ_id"]):
                occ = Occurrence(
                    occ_id=last["occ_id"], topic=last["topic"],
                    index=int(last.get("index", 0)),
                    bank_sha256=last.get("bank_sha256", ""),
                    reserved_at=last.get("at", _now_iso()))
                self._write_active(occ)
                return occ
        lines, sha = self._read_lines()
        pending = [(i, t.strip()) for i, t in enumerate(lines)
                   if t.strip()]
        if not pending:
            return None
        index, topic = pending[0]
        counter = self._journal_count("reserve") + 1
        norm = topic.strip().lower()
        occ_id = hashlib.sha1(
            f"{norm}:{counter}".encode("utf-8")).hexdigest()[:16]
        occ = Occurrence(occ_id=occ_id, topic=topic, index=index,
                         bank_sha256=sha, reserved_at=_now_iso())
        # 1) journal durable, 2) active durable, 3) retirar del banco
        self._append_journal({"op": "reserve", "occ_id": occ.occ_id,
                              "topic": occ.topic, "index": occ.index,
                              "bank_sha256": occ.bank_sha256,
                              "at": occ.reserved_at})
        self._write_active(occ)
        self._rewrite_bank_without_index(lines, index)
        return occ

    def complete(self, occ: Occurrence, mp4: Path, *, _fh=None) -> None:
        """Registra historial y limpia active. NUNCA toca el banco.

        _fh: lock ya tomado por flow.run_bank (lock de ejecución completo).
        """
        if _fh is not None:
            self._complete_impl(occ, mp4)
            return
        with lock_bank(self.lock_path):
            self._complete_impl(occ, mp4)

    def _complete_impl(self, occ: Occurrence, mp4: Path) -> None:
        if self._journal_open(occ.occ_id):
            sha = ""
            try:
                sha = hashlib.sha256(Path(mp4).read_bytes()).hexdigest()
            except OSError:
                pass
            with open(self.history_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "occ_id": occ.occ_id, "topic": occ.topic,
                    "mp4": str(mp4), "sha256": sha,
                    "at": _now_iso()}, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._append_journal({"op": "complete", "occ_id": occ.occ_id,
                                  "topic": occ.topic, "at": _now_iso()})
        try:
            self.active_path.unlink()
        except OSError:
            pass

    def fail(self, occ: Occurrence, error: str, *, _fh=None) -> None:
        """Conserva active y banco para reanudar; solo journal fail.

        _fh: lock ya tomado por flow.run_bank (ejecución completa).
        """
        if _fh is not None:
            self._append_journal({"op": "fail", "occ_id": occ.occ_id,
                                  "topic": occ.topic, "error": str(error),
                                  "at": _now_iso()})
            return
        with lock_bank(self.lock_path):
            self._append_journal({"op": "fail", "occ_id": occ.occ_id,
                                  "topic": occ.topic, "error": str(error),
                                  "at": _now_iso()})
