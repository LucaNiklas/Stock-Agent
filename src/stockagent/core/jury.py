"""Aggregation der Jury J3 (SPEC 11.2 Ebene 3, 11.3).

Je Kriterium der Median der Punkte und die Spannweite (höchste minus niedrigste Punktzahl) über
den Rechenweg, Prüfpunkt CP-02: jede Punktzahl liegt zwischen 1 und 5. Entscheidungsregel:
`verified`, wenn kein Median unter `mindest_kriterium` liegt, der Median der Gesamtbegründung
mindestens `mindest_gesamt` ist, keine Spannweite über `uneinig_spannweite` liegt und mindestens
`mindest_richter` Richter geurteilt haben. Sonst `escalated` mit Gründen. Schwellen in
`config/models.yaml` (pruefung.jury).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from stockagent.core.calc import Rechenweg, Stufe, rechne

KRITERIEN = (
    "faktentreue",
    "vollstaendigkeit",
    "konsistenz",
    "gegenargumente",
    "bewertungsdisziplin",
    "gesamtbegruendung",
)
GESAMT = "gesamtbegruendung"


@dataclass(frozen=True)
class JuryKonfig:
    mindest_kriterium: Decimal
    mindest_gesamt: Decimal
    uneinig_spannweite: Decimal
    mindest_richter: int

    @classmethod
    def aus(cls, cfg: Mapping[str, Any]) -> JuryKonfig:
        return cls(
            Decimal(str(cfg["mindest_kriterium"])),
            Decimal(str(cfg["mindest_gesamt"])),
            Decimal(str(cfg["uneinig_spannweite"])),
            int(cfg["mindest_richter"]),
        )


@dataclass(frozen=True)
class Kriterium:
    kriterium: str
    punkte: tuple[int, ...]
    median: Decimal | None
    spannweite: Decimal | None
    grund: str | None = None  # gesetzt, wenn die Rechnung gestoppt hat


@dataclass
class JuryUrteil:
    status: str  # verified, escalated
    richter: int
    kriterien: list[Kriterium] = field(default_factory=list)
    gruende: list[str] = field(default_factory=list)


def _kriterium(name: str, punkte: Sequence[int]) -> Kriterium:
    r = Rechenweg(f"j3_{name}", "1.0", "", "", pflicht=("CP-02",))
    namen = {f"p{i}": Decimal(p) for i, p in enumerate(punkte, start=1)}
    liste = ", ".join(namen)

    def rechnung(rw: Rechenweg) -> Decimal:
        im_bereich = all(1 <= p <= 5 for p in punkte)
        rw.pruefe("CP-02", "Punkte je Richter zwischen 1 und 5", im_bereich, Stufe.STOPP)
        rw.median("median", list(namen.values()))
        return rw.schritt("spannweite", f"max({liste}) - min({liste})", **namen)

    spannweite = rechne(r, rechnung)
    if spannweite.unknown:
        return Kriterium(name, tuple(punkte), None, None, spannweite.grund)
    median = Decimal(r.schritte[0].ergebnis)
    return Kriterium(name, tuple(punkte), median, spannweite.wert)


def urteil(punkte: Mapping[str, Sequence[int]], cfg: JuryKonfig) -> JuryUrteil:
    """`punkte`: je Kriterium die Punktzahlen der Richter in fester Reihenfolge."""
    richter = min((len(v) for v in punkte.values()), default=0)
    out = JuryUrteil("verified", richter)
    if richter < cfg.mindest_richter:
        out.status = "escalated"
        out.gruende.append(f"nur {richter} Richter geurteilt, nötig {cfg.mindest_richter}")
        return out
    for name in KRITERIEN:
        k = _kriterium(name, punkte.get(name, ()))
        out.kriterien.append(k)
        if k.median is None or k.spannweite is None:
            out.gruende.append(f"{name}: {k.grund}")
            continue
        if k.spannweite > cfg.uneinig_spannweite:
            out.gruende.append(f"{name}: Jury uneinig (Spannweite {k.spannweite})")
        if k.median < cfg.mindest_kriterium:
            out.gruende.append(f"{name}: Median {k.median} unter {cfg.mindest_kriterium}")
        if name == GESAMT and k.median < cfg.mindest_gesamt:
            out.gruende.append(f"{name}: Median {k.median} unter {cfg.mindest_gesamt}")
    if out.gruende:
        out.status = "escalated"
    return out
