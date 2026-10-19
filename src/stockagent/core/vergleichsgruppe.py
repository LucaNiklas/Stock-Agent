"""Vergleichsgruppe nach Umsatznähe und Multiples-Abschlag (SPEC 3.6, 6.2, ADR 0005).

- Ähnlichster Umsatz: Abstand |ln(Umsatz Kandidat / Umsatz Firma)|, also gleich weit für die
  halbe wie für die doppelte Größe. Bei Gleichstand entscheidet die Kennung, damit die Auswahl
  wiederholbar ist (CP-08).
- Multiples-Abschlag: Je Multiple (EV/EBIT, KGV, FCF-Rendite) der Kurs, den der Median der
  Vergleichsgruppe ergäbe, relativ zum Kurs. Abschlag = 1 - 1 / Median dieser Verhältnisse.
  Positiv heißt, der Kurs liegt unter dem, was die Gruppe zahlt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext

from stockagent.core.calc import Rechenweg


def naechste(eigen_umsatz: Decimal, kandidaten: Mapping[str, Decimal], anzahl: int) -> list[str]:
    """Die `anzahl` Kandidaten mit dem ähnlichsten Umsatz (nur positive Umsätze)."""
    if eigen_umsatz <= 0:
        return sorted(kandidaten)[:anzahl]
    with localcontext() as ctx:
        ctx.prec = 28
        abstand = {k: abs((u / eigen_umsatz).ln()) for k, u in kandidaten.items() if u > 0}
    return [k for k, _ in sorted(abstand.items(), key=lambda x: (x[1], x[0]))][:anzahl]


def multiples_abschlag(
    r: Rechenweg,
    eigen: Mapping[str, Decimal | None],
    gruppe: Sequence[Mapping[str, Decimal | None]],
) -> Decimal | None:
    """Abschlag des Kurses gegenüber dem Median der Multiples der Gruppe. `eigen` und
    `gruppe` mit den Schlüsseln ev_ebit, pe, fcf_yield (aktuell)."""
    verhaeltnisse: dict[str, Decimal] = {}
    for name, hoeher_teurer in (("ev_ebit", True), ("pe", True), ("fcf_yield", False)):
        e = eigen.get(name)
        werte = [v for g in gruppe if (v := g.get(name)) is not None and v > 0]
        if e is None or e <= 0 or len(werte) < 5:
            continue
        median = r.median(f"median_{name}", werte)
        verhaeltnisse[name] = r.schritt(
            f"kurs_relativ_{name}",
            "median / eigen" if hoeher_teurer else "eigen / median",
            median=median,
            eigen=e,
        )
    if not verhaeltnisse:
        return None
    mitte = r.median("kurs_relativ_median", list(verhaeltnisse.values()))
    return r.schritt("multiples_abschlag", "1 - 1 / m", m=mitte)
