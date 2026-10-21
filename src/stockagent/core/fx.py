"""Währungsumrechnung im Rechenweg (SPEC 5.2, HR-06, HR-19).

Ein Wert in fremder Währung wird nie still umgerechnet. `umrechnen` schreibt einen eigenen
Schritt in den Rechenweg der Kennzahl, mit dem Ausgangswert, beiden Referenzkursen der EZB und
dem Ergebnis, und gibt eine neue `Eingabe` in der Zielwährung zurück. So bleibt die Regel
„eine Rechnung, eine Währung“ (CP-01) erhalten, und die Umrechnung ist nachprüfbar.

Referenzkurse sind Einheiten der Währung je 1 EUR. Ein Betrag in Währung A wird über den Euro in
Währung B umgerechnet: betrag / kurs_A * kurs_B. Unterwährungen (Pence, Cent, Agorot) werden
vorher durch 100 geteilt (SPEC 5.2 Nr. 10).
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

from stockagent.core.calc import (
    Eingabe,
    PruefpunktVerletzt,
    RechenFehler,
    Rechenweg,
    Schritt,
    Wert,
    berechne,
)

# Unterwährung -> (Hauptwährung, Teiler). Fester Zusammenhang, keine Schwelle (SPEC 5.2 Nr. 10).
UNTERWAEHRUNG_TEILER = 100


def hauptwaehrung(waehrung: str, unterwaehrungen: Mapping[str, str]) -> str:
    return unterwaehrungen.get(waehrung, waehrung)


def _beschreibung(e: Eingabe) -> dict[str, object]:
    return e.beschreibung()


def umrechnen(
    r: Rechenweg,
    name: str,
    wert: Eingabe,
    ziel: str,
    kurse: Mapping[str, Eingabe],
    unterwaehrungen: Mapping[str, str],
) -> Eingabe:
    """`wert` in die Währung `ziel` umrechnen. `kurse`: Referenzkurs je Hauptwährung (je EUR).

    Der Schritt wird direkt in den Rechenweg geschrieben, ohne die Währung des Ausgangswerts in
    die Währungsprüfung der Rechnung aufzunehmen: Gerechnet wird danach nur mit dem Ergebnis.
    """
    if wert.waehrung is None:
        r.pruefe("CP-01", f"{name}: Währung des Ausgangswerts bekannt", False)
    quelle_waehrung = str(wert.waehrung)
    haupt = hauptwaehrung(quelle_waehrung, unterwaehrungen)
    teiler = UNTERWAEHRUNG_TEILER if haupt != quelle_waehrung else 1
    eingaben: dict[str, Wert]
    if haupt == ziel:
        formel, eingaben = "betrag / teiler", {"betrag": wert.wert, "teiler": teiler}
        kursangaben: dict[str, object] = {}
    else:
        fehlt = [w for w in (haupt, ziel) if w not in kurse and w != "EUR"]
        r.pruefe("CP-01", f"{name}: Referenzkurse für {haupt} und {ziel} vorhanden", not fehlt)
        k_von = kurse[haupt].wert if haupt != "EUR" else 1
        k_nach = kurse[ziel].wert if ziel != "EUR" else 1
        r.pruefe("CP-02", f"{name}: Referenzkurse positiv", k_von > 0 and k_nach > 0)
        formel = "betrag / teiler / kurs_von * kurs_nach"
        eingaben = {"betrag": wert.wert, "teiler": teiler, "kurs_von": k_von, "kurs_nach": k_nach}
        kursangaben = {w: _beschreibung(kurse[w]) for w in (haupt, ziel) if w != "EUR"}
    try:
        ergebnis = berechne(formel, **eingaben)
    except RechenFehler as exc:
        raise PruefpunktVerletzt(r, "CP-02", f"{name}: {exc}") from exc
    r.schritte.append(
        Schritt(
            name=name,
            formel=f"{formel} ({quelle_waehrung} -> {ziel})",
            eingaben={"wert": _beschreibung(wert), **kursangaben, "teiler": str(teiler)},
            ergebnis=str(ergebnis),
        )
    )
    return replace(
        wert,
        wert=ergebnis,
        waehrung=ziel,
        quelle=f"{wert.quelle}, umgerechnet {quelle_waehrung} -> {ziel} (EZB)",
    )


def referenzkurs_am(daten: Sequence[date], werte: Sequence[Decimal], tag: date) -> Decimal | None:
    """Referenzkurs am Tag oder am letzten Kurstag davor aus einer sortierten Reihe (wie
    `store.fx_on_or_before`, für viele Tage am Stück). None vor dem ersten Kurs."""
    i = bisect.bisect_right(daten, tag)
    return werte[i - 1] if i else None
