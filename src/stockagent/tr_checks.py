"""Lucas Prüfungen der Handelbarkeit bei Trade Republic (SPEC 7.1, ADR 0001).

Trade Republic bietet keinen automatisierbaren Zugang zu seiner Instrumentenliste. Ob eine Aktie
dort handelbar ist, prüft Luca in der App und hält es hier fest. Ohne Eintrag gilt "ungeprueft".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

import yaml

from stockagent.core.identifiers import isin_is_valid


class TrStatus(StrEnum):
    UNGEPRUEFT = "ungeprueft"
    BESTAETIGT = "bestaetigt"
    NICHT_HANDELBAR = "nicht_handelbar"


@dataclass(frozen=True)
class TrCheck:
    status: TrStatus
    checked_on: date


def load(path: Path) -> dict[str, TrCheck]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    checks = data.get("pruefungen") or {}
    return {
        isin: TrCheck(TrStatus(v["status"]), date.fromisoformat(str(v["datum"])))
        for isin, v in checks.items()
    }


def record(path: Path, isin: str, tradable: bool, on: date) -> TrCheck:
    if not isin_is_valid(isin):
        raise ValueError(f"{isin} ist keine gültige ISIN")
    checks = load(path)
    check = TrCheck(TrStatus.BESTAETIGT if tradable else TrStatus.NICHT_HANDELBAR, on)
    checks[isin] = check
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "pruefungen": {
            k: {"status": v.status.value, "datum": v.checked_on.isoformat()}
            for k, v in sorted(checks.items())
        }
    }
    header = "# Von Luca in der Trade-Republic-App geprüfte Handelbarkeit (stockagent tr-check).\n"
    path.write_text(header + yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    return check
