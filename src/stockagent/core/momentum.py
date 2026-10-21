"""Kursmomentum für die Säule Momentum (ADR 0011, config/horizonte.yaml).

Aus der Tagesreihe in EUR (wie die Risikoeingänge in `core/marktrisiko.py`, also mit dem
Wechselkurseffekt, den ein Anleger in EUR erlebt). Schrittweise über den Rechenweg (HR-19).

- Momentum 12-1: Kurs vor 21 Handelstagen / Kurs vor 252 Handelstagen − 1. Der letzte Monat
  bleibt außen vor, weil kurzfristige Umkehr das Signal stört (Jegadeesh und Titman 1993).
- Momentum 6-1: Kurs vor 21 Handelstagen / Kurs vor 126 Handelstagen − 1.
- Nähe zum 52-Wochen-Hoch: letzter Kurs / höchster Kurs der letzten 252 Handelstage
  (George und Hwang 2004).
- Abstand zur 200-Tage-Linie: letzter Kurs / Mittel der letzten 200 Schlusskurse − 1 (Trend,
  Brock, Lakonishok und LeBaron 1992).
- Kursreaktion auf den letzten Bericht: Kurs am zweiten Handelstag nach der Veröffentlichung /
  letzter Kurs davor − 1, nur wenn der Bericht höchstens `bericht_max_tage` zurückliegt. Nach
  guten Berichten driften Kurse über Wochen weiter (Bernard und Thomas 1989; Chan, Jegadeesh und
  Lakonishok 1996). Ohne Marktindex als Rohrendite, die Vergleichsgruppe ordnet sie ein.

Fehlt ein frischer Kurs (älter als `max_abstand_tage`) oder ein volles Jahr, gibt es kein
Momentum (unknown, kein Schätzen).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from stockagent.core import dq
from stockagent.core.calc import NichtDefiniert, Rechenweg, rechne
from stockagent.core.marktrisiko import HANDELSTAGE_JAHR, Tag

VERSION = "1.0"
MONAT = 21
HALBJAHR = 126
KENNZAHLEN = (
    "momentum_12_1",
    "momentum_6_1",
    "naehe_52w_hoch",
    "abstand_ma200",
    "reaktion_bericht",
)
MA_TAGE = 200


def momentum(
    subjekt: str,
    tage: Sequence[Tag],
    heute: date,
    max_abstand_tage: int,
    bericht: date | None = None,
    bericht_max_tage: int = 120,
) -> tuple[dict[str, Decimal | None], dict[str, object]]:
    """Die Kennzahlen und je Kennzahl der Rechenweg."""
    reihe = sorted(tage, key=lambda t: t.datum)
    out: dict[str, Decimal | None] = dict.fromkeys(KENNZAHLEN)
    wege: dict[str, object] = {}

    def vorbereiten(r: Rechenweg, n: int) -> list[Tag]:
        if not reihe:
            raise NichtDefiniert("keine Kurse")
        if dq.kurs_veraltet(reihe[-1].datum, heute, max_abstand_tage):
            raise NichtDefiniert(f"letzter Kurs vom {reihe[-1].datum} zu alt")
        if len(reihe) <= n:
            raise NichtDefiniert(f"nur {len(reihe)} Handelstage, nötig {n + 1}")
        r.pruefe("CP-02", "Kurse positiv", all(t.kurs_eur > 0 for t in reihe[-(n + 1) :]))
        return reihe

    def rendite(n: int) -> object:
        def rechnung(r: Rechenweg) -> Decimal:
            k = vorbereiten(r, n)
            ende, anfang = k[-1 - MONAT], k[-1 - n]
            return r.schritt(
                "rendite",
                "kurs_ende / kurs_anfang - 1",
                kurs_ende=ende.kurs_eur,
                kurs_anfang=anfang.kurs_eur,
                tag_ende=Decimal(ende.datum.toordinal()),
                tag_anfang=Decimal(anfang.datum.toordinal()),
            )

        return rechnung

    def naehe(r: Rechenweg) -> Decimal:
        k = vorbereiten(r, HANDELSTAGE_JAHR - 1)
        jahr = k[-HANDELSTAGE_JAHR:]
        hoch = max(t.kurs_eur for t in jahr)
        q = r.schritt("naehe_hoch", "kurs / hoch", kurs=k[-1].kurs_eur, hoch=hoch)
        r.pruefe("CP-02", "Kurs höchstens am Hoch", q <= 1)
        return q

    def ma200(r: Rechenweg) -> Decimal:
        k = vorbereiten(r, MA_TAGE - 1)
        namen = {f"k{i}": t.kurs_eur for i, t in enumerate(k[-MA_TAGE:])}
        mittel = r.schritt("ma200", f"({' + '.join(namen)}) / {MA_TAGE}", **namen)
        return r.schritt("abstand_ma200", "kurs / ma200 - 1", kurs=k[-1].kurs_eur, ma200=mittel)

    def reaktion(r: Rechenweg) -> Decimal:
        if bericht is None:
            raise NichtDefiniert("kein Veröffentlichungstag eines Berichts bekannt")
        if dq.kurs_veraltet(bericht, heute, bericht_max_tage):
            raise NichtDefiniert(f"letzter Bericht vom {bericht} älter als {bericht_max_tage} Tage")
        k = vorbereiten(r, 1)
        vor = [t for t in k if t.datum < bericht]
        nach = [t for t in k if t.datum > bericht]
        if not vor or len(nach) < 2:
            raise NichtDefiniert(f"keine Kurse um den Bericht vom {bericht}")
        return r.schritt(
            "reaktion",
            "kurs_nach / kurs_vor - 1",
            kurs_nach=nach[1].kurs_eur,
            kurs_vor=vor[-1].kurs_eur,
            tag_nach=Decimal(nach[1].datum.toordinal()),
            tag_vor=Decimal(vor[-1].datum.toordinal()),
        )

    for name, fn in (
        ("momentum_12_1", rendite(HANDELSTAGE_JAHR)),
        ("momentum_6_1", rendite(HALBJAHR)),
        ("naehe_52w_hoch", naehe),
        ("abstand_ma200", ma200),
        ("reaktion_bericht", reaktion),
    ):
        r = Rechenweg(name, VERSION, subjekt, heute.isoformat(), pflicht=("CP-02",))
        e = rechne(r, fn)  # type: ignore[arg-type]
        out[name] = e.wert
        wege[name] = e.rechenweg if e.wert is not None else {"grund": e.grund}
    return out, wege
