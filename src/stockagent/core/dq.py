"""Arithmetik der Datenqualitätsprüfungen (SPEC 3.2) über den Rechenweg (HR-06, HR-19).

Jede Prüfung ist eine kleine Rechnung mit Prüfpunkten. Das Ergebnis ist `unknown`, wenn ein
Stopp-Prüfpunkt verletzt ist, und trägt Warnungen, wenn ein Warn-Prüfpunkt verletzt ist.
`data/quality.py` lädt die Werte, ruft diese Funktionen auf und schreibt die Flags.
Schwellen kommen aus `config/quality.yaml`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stockagent.core.calc import Eingabe, Ergebnis, Rechenweg, Stufe, rechne

VERSION = "1.0"


def _summe_formel(n: int, gewichtet: bool = False) -> str:
    if gewichtet:
        return " + ".join(f"g{i} * t{i}" for i in range(n))
    return " + ".join(f"t{i}" for i in range(n))


def bilanzgleichung(
    subjekt: str, aktiva: Eingabe, passiva_teile: Sequence[Eingabe], toleranz: Decimal
) -> Ergebnis:
    """SPEC 3.2 Nr. 1: Aktiva gleich Passiva. Wert ist die relative Abweichung.

    `passiva_teile` ist entweder [LiabilitiesAndStockholdersEquity] oder die Teile, aus denen
    sich die Passivseite zusammensetzt (Schulden, Eigenkapital einschließlich Minderheiten).
    """
    r = Rechenweg(
        "dq_bilanzgleichung",
        VERSION,
        subjekt,
        aktiva.periode_ende.isoformat(),
        pflicht=("CP-01", "CP-02", "CP-03"),
    )

    def rechnung(r: Rechenweg) -> Decimal:
        r.pruefe("CP-01", "Passivseite vorhanden", len(passiva_teile) > 0)
        r.pruefe_eingaben(aktiva, *passiva_teile)
        r.pruefe("CP-02", "Bilanzsumme positiv", aktiva.wert > 0)
        teile = {f"t{i}": t for i, t in enumerate(passiva_teile)}
        passiva = r.schritt("passiva", _summe_formel(len(teile)), **teile)
        abw = r.schritt(
            "abweichung", "abs(aktiva - passiva) / aktiva", aktiva=aktiva, passiva=passiva
        )
        r.pruefe("CP-03", f"Aktiva gleich Passiva (Toleranz {toleranz})", abw <= toleranz)
        return abw

    return rechne(r, rechnung)


def summenprobe(
    subjekt: str,
    name: str,
    summe: Eingabe,
    teile: Sequence[tuple[Eingabe, Decimal]],
    toleranz_rel: Decimal,
    toleranz_abs: Decimal,
    gleiche_periode: bool = True,
) -> Ergebnis:
    """SPEC 3.2 Nr. 2 und Nr. 4: gewichtete Summe der Teile gleich Summenposition.

    `toleranz_abs` deckt Rundung der berichteten Werte ab (etwa auf Millionen gerundet).
    `gleiche_periode=False` für Teile verschiedener Zeiträume (drei Quartale gegen neun Monate).
    Wert ist die absolute Differenz.
    """
    r = Rechenweg(
        f"dq_summe_{name}",
        VERSION,
        subjekt,
        summe.periode_ende.isoformat(),
        pflicht=("CP-01", "CP-03"),
    )

    def rechnung(r: Rechenweg) -> Decimal:
        r.pruefe("CP-01", "Teile vorhanden", len(teile) > 0)
        r.pruefe_eingaben(summe, *(t for t, _ in teile), gleiche_periode=gleiche_periode)
        werte: dict[str, Eingabe | Decimal] = {}
        for i, (t, g) in enumerate(teile):
            werte[f"t{i}"] = t
            werte[f"g{i}"] = g
        teilsumme = r.schritt("teilsumme", _summe_formel(len(teile), gewichtet=True), **werte)
        diff = r.schritt("differenz", "abs(summe - teilsumme)", summe=summe, teilsumme=teilsumme)
        grenze = r.schritt(
            "grenze",
            "max(toleranz_abs, abs(summe) * toleranz_rel)",
            summe=summe,
            toleranz_abs=toleranz_abs,
            toleranz_rel=toleranz_rel,
        )
        r.pruefe("CP-03", f"Teile ergeben {name}", diff <= grenze)
        return diff

    return rechne(r, rechnung)


def abgleich(
    subjekt: str, name: str, wert_a: Eingabe, wert_b: Eingabe, warnung: Decimal, stopp: Decimal
) -> Ergebnis:
    """SPEC 3.2 Nr. 5: zwei unabhängige Wege. Über `warnung` Warnung, über `stopp` Stopp.

    Wert ist die relative Abweichung bezogen auf `wert_a`.
    """
    r = Rechenweg(
        f"dq_abgleich_{name}",
        VERSION,
        subjekt,
        wert_a.periode_ende.isoformat(),
        pflicht=("CP-01", "CP-04"),
    )

    def rechnung(r: Rechenweg) -> Decimal:
        r.pruefe_eingaben(wert_a, wert_b)
        if wert_a.wert == 0:
            abw = r.schritt("abweichung", "abs(b)", b=wert_b)
        else:
            abw = r.schritt("abweichung", "abs(a - b) / abs(a)", a=wert_a, b=wert_b)
        r.pruefe("CP-04", f"Abweichung höchstens {stopp}", abw <= stopp)
        r.pruefe("CP-04", f"Abweichung höchstens {warnung}", abw <= warnung, Stufe.WARNUNG)
        return abw

    return rechne(r, rechnung)


def ausreisser(
    subjekt: str, name: str, historie: Sequence[Eingabe], wert: Eingabe, schwelle: Decimal
) -> Ergebnis | None:
    """SPEC 3.2 Nr. 6: robuster z-Wert über Median und MAD gegen die eigene Historie.

    None, wenn die Historie zu kurz ist (unter 4 Werten). Hat die Historie keine Streuung
    (MAD null), ist der z-Wert nicht definiert: Ergebnis 0 mit Vermerk im Rechenweg.
    Wert ist der z-Wert. Ein Ausreißer ist eine Warnung, kein Fehler.
    """
    if len(historie) < 4:
        return None
    r = Rechenweg(
        f"dq_ausreisser_{name}",
        VERSION,
        subjekt,
        wert.periode_ende.isoformat(),
        pflicht=("CP-01", "CP-05"),
    )

    def rechnung(r: Rechenweg) -> Decimal:
        r.pruefe_eingaben(wert, *historie, gleiche_periode=False)
        med = r.median("median", historie)
        abst = [r.schritt(f"abstand_{i}", "abs(x - m)", x=h, m=med) for i, h in enumerate(historie)]
        mad = r.median("mad", abst)
        if mad == 0:
            r.pruefe("CP-05", "Historie ohne Streuung, z-Wert nicht definiert", True)
            return Decimal(0)
        z = r.schritt("z_wert", "0.6745 * (x - median) / mad", x=wert, median=med, mad=mad)
        r.pruefe("CP-05", f"|z| höchstens {schwelle}", abs(z) <= schwelle)
        return z

    return rechne(r, rechnung)


@dataclass(frozen=True)
class SplitVerdacht:
    ergebnis: Ergebnis
    faktor: Decimal | None  # 4 bei 4:1-Split, 0.1 bei 1:10-Zusammenlegung, None ohne Verdacht
    verhaeltnis: str | None = None  # "4:1" oder "1:10"


def split_verdacht(
    subjekt: str, vorher: Eingabe, nachher: Eingabe, toleranz: Decimal
) -> SplitVerdacht:
    """SPEC 3.2 Nr. 8: Sprung der Aktienzahl um einen ganzzahligen Faktor deutet auf einen Split.

    Bereinigt wird erst bei den Kennzahlen (Bauschritt 3). Hier nur erkennen und melden.
    """
    r = Rechenweg(
        "dq_split",
        VERSION,
        subjekt,
        nachher.periode_ende.isoformat(),
        pflicht=("CP-01", "CP-02"),
    )
    faktor: list[Decimal] = []
    text: list[str] = []

    def rechnung(r: Rechenweg) -> Decimal:
        r.pruefe_eingaben(vorher, nachher, gleiche_periode=False)
        r.pruefe("CP-02", "Aktienzahlen positiv", vorher.wert > 0 and nachher.wert > 0)
        verh = r.schritt("verhaeltnis", "nachher / vorher", nachher=nachher, vorher=vorher)
        groesser = verh if verh >= 1 else r.schritt("kehrwert", "1 / v", v=verh)
        k = r.schritt("ganzzahl", "runde(g)", g=groesser)
        if k >= 2:
            abstand = r.schritt("abstand", "abs(g - k) / k", g=groesser, k=k)
            if abstand <= toleranz:
                faktor.append(k if verh >= 1 else r.schritt("faktor", "1 / k", k=k))
                text.append(f"{k}:1" if verh >= 1 else f"1:{k}")
        return verh

    erg = rechne(r, rechnung)
    return SplitVerdacht(erg, faktor[0] if faktor else None, text[0] if text else None)


def dauer_tage(start: date, ende: date) -> int:
    """Länge einer Periode in Tagen einschließlich beider Stichtage."""
    return (ende - start).days + 1


def periode_passt(start: date | None, ende: date, art: str) -> bool:
    """SPEC 3.2 Nr. 4: Geschäftsjahr 52 oder 53 Wochen bis 12 Monate, Quartal etwa 13 Wochen.

    `art` ist `FY` (Jahr) oder `Q` (ein Quartal). Stichtagswerte (ohne Start) passen immer.
    """
    if start is None:
        return True
    tage = dauer_tage(start, ende)
    if art == "FY":
        return 357 <= tage <= 373
    if art == "Q":
        return 84 <= tage <= 98
    raise ValueError(f"Unbekannte Periodenart: {art}")


def ist_neunmonatig(start: date | None, ende: date) -> bool:
    """Neun-Monats-Wert seit Geschäftsjahresbeginn (Q3 im 10-Q), 39 Wochen bis 9 Monate."""
    return start is not None and 266 <= dauer_tage(start, ende) <= 280


def stichtag_passt(ende: date, mmdd: str, tage: int = 7) -> bool:
    """SPEC 3.2 Nr. 4: Liegt ein Jahresstichtag beim Geschäftsjahresende laut SEC (MMDD)?

    52/53-Wochen-Jahre enden wenige Tage vor oder nach dem Kalenderdatum.
    """
    monat, tag = int(mmdd[:2]), int(mmdd[2:])
    for jahr in (ende.year - 1, ende.year, ende.year + 1):
        try:
            ziel = date(jahr, monat, tag)
        except ValueError:  # 29.02. außerhalb von Schaltjahren
            ziel = date(jahr, monat, 28)
        if abs((ende - ziel).days) <= tage:
            return True
    return False


def rundungstoleranz(decimals: Sequence[int | None]) -> Decimal:
    """Summe der Rundungseinheiten 10^-decimals der beteiligten Werte (XBRL-Attribut decimals).

    Ein auf Millionen gerundeter Wert (decimals = -6) darf um bis zu eine Million abweichen.
    Unbekannte Genauigkeit zählt als exakt.
    """
    return sum((Decimal(1).scaleb(-d) for d in decimals if d is not None), Decimal(0))
