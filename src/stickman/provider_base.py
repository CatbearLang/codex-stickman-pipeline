"""Contratos de proveedores (§4.3): Requirement + base Provider.

Requirement: kind account|key|login|network|cli|model|os; official True =
API/CLI oficial, False = vía no oficial (advertir en docs+check);
verified True solo tras prueba live documentada (todos nacen False
salvo script.local-advanced que es puro local).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Requirement:
    kind: str
    label: str
    env: str | None = None
    official: bool = True
    verified: bool = False


class Provider:
    name = "base"
    verified = False

    def requirements(self) -> list:
        return []

    def check(self) -> dict:
        import os as _os
        reqs = self.requirements()
        missing = [r.label for r in reqs if r.kind == "key" and r.env
                   and not _os.environ.get(r.env)]
        details = [{"kind": r.kind, "label": r.label, "env": r.env,
                    "official": r.official, "verified": r.verified}
                   for r in reqs]
        return {"ok": not missing,
                "details": {"requirements": details,
                            "verified": self.verified},
                "hint": ("falta: " + ", ".join(missing)) if missing
                        else "requisitos presentes (verificación live pendiente)"}
