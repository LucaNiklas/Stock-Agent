"""Trends und Zeitreihen je Kennzahl (SPEC 3.4) über den Rechenweg (HR-06, HR-19).

Für jede Kennzahl aus `config/metrics.yaml` entsteht eine Jahresreihe (eine Rechnung je
Geschäftsjahr über `registry.berechne`). Darauf rechnet dieses Modul je Statistik einen eigenen
Rechenweg, damit eine nicht berechenbare Statistik die anderen nicht mitnimmt:

- `niveau`: Wert im Stichtagsjahr.
- `veraenderung_vj`: Veränderung zum Vorjahr. Bei Beträgen relativ (Vorjahr ungleich null),
  bei Quoten und Punktwerten als Differenz in Punkten, weil eine relative Änderung einer Marge
  von 1 % auf 2 % als +100 % irreführt.
- `cagr_3j`, `cagr_5j`: durchschnittliche jährliche Wachstumsrate, nur bei positivem Anfangs-
  und Endwert definiert (sonst CP-02 und unknown).
- `stdabw`: Stichproben-Standardabweichung über bis zu 10 Jahre. Für die EBIT-Marge ist das die
  Margenstabilität aus SPEC 3.4 Nr. 3, die in Schritt 5 in den Qualitätsscore eingeht.
- `steigung`: Theil-Sen-Schätzer, der Median aller paarweisen Steigungen je Geschäftsjahr,
  unempfindlich gegen einzelne Ausreißer.
- `plausibilitaet`: CP-05, robuster z-Wert des Stichtagswerts gegen die Vorjahre
  (`dq.ausreisser`, Schwelle aus `config/quality.yaml`). Ein Ausreißer ist eine Warnung.

Dazu die vertikale Analyse (SPEC 3.4 Nr. 6): jeder Strom in Prozent vom Umsatz, jeder Stand in
Prozent der Bilanzsumme, für die Detailansicht.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import combinations
from typing import Any

from stockagent.core import dq, registry
from stockagent.core.calc import Eingabe, EingabeFehlt, Ergebnis, Rechenweg, rechne
from stockagent.core.reihen import Reihen

VERSION = "1.0"
STATISTIKEN = (
    "niveau",
    "veraenderung_vj",
    "cagr_3j",
    "cagr_5j",
    "stdabw",
    "steigung",
    "plausibilitaet",
)
# Einheiten, bei denen die Vorjahresveränderung relativ gerechnet wird
_RELATIV = {"monetary", "per_share", "shares"}


@dataclass(frozen=True)
class Punkt:
    stichtag: date
    wert: Decimal
    waehrung: str | None


def jahresreihe(
    definition: Mapping[str, Any], reihen: Reihen, max_jahre: int
) -> dict[date, Ergebnis]:
    """Die Kennzahl für jedes Geschäftsjahr der Reihen, neuestes zuerst."""
    return {t: registry.berechne(definition, reihen, t) for t in reihen.stichtage[:max_jahre]}


def _punkte(jahre: Mapping[date, Ergebnis], waehrung: str | None) -> list[Punkt]:
    """Berechnete Werte, ältestes zuerst. Unknown-Jahre fehlen in der Reihe."""
    return sorted(
        (Punkt(t, e.wert, waehrung) for t, e in jahre.items() if e.wert is not None),
        key=lambda p: p.stichtag,
    )


def _eingabe(metric_id: str, einheit: str, p: Punkt) -> Eingabe:
    return Eingabe(p.wert, f"Kennzahl {metric_id} {p.stichtag}", einheit, p.stichtag, p.waehrung)


def _ab(punkte: Sequence[Punkt], stichtag: date) -> list[Punkt]:
    return [p for p in punkte if p.stichtag <= stichtag]


def _rechenweg(metric_id: str, statistik: str, subjekt: str, stichtag: date) -> Rechenweg:
    return Rechenweg(
        f"trend_{metric_id}_{statistik}",
        VERSION,
        subjekt,
        stichtag.isoformat(),
        pflicht=("CP-01", "CP-02"),
    )


def _cp01(r: Rechenweg, werte: Sequence[Eingabe], mindest: int) -> None:
    if len(werte) < mindest:
        raise EingabeFehlt(
            f"mindestens {mindest} Geschäftsjahre (vorhanden {len(werte)})", r.periode
        )
    r.pruefe_eingaben(*werte, gleiche_periode=False)
    jahre = [w.periode_ende.year for w in werte]
    r.pruefe("CP-01", "jedes Geschäftsjahr nur einmal", len(set(jahre)) == len(jahre))


def niveau(r: Rechenweg, werte: Sequence[Eingabe]) -> Decimal:
    _cp01(r, werte[-1:], 1)
    jetzt = werte[-1]
    r.pruefe("CP-02", "Wert im Stichtagsjahr", jetzt.periode_ende.isoformat() == r.periode)
    return r.schritt("niveau", "x", x=jetzt)


def veraenderung_vj(r: Rechenweg, werte: Sequence[Eingabe]) -> Decimal:
    _cp01(r, werte[-2:], 2)
    vor, jetzt = werte[-2], werte[-1]
    r.pruefe("CP-02", "Wert im Stichtagsjahr", jetzt.periode_ende.isoformat() == r.periode)
    r.pruefe(
        "CP-01",
        "Vorjahr ist das direkt vorangehende Geschäftsjahr",
        jetzt.periode_ende.year - vor.periode_ende.year == 1,
    )
    if jetzt.einheit in _RELATIV:
        r.pruefe("CP-02", "Vorjahreswert ungleich null", vor.wert != 0)
        return r.schritt("veraenderung", "(jetzt - vor) / abs(vor)", jetzt=jetzt, vor=vor)
    return r.schritt("veraenderung_punkte", "jetzt - vor", jetzt=jetzt, vor=vor)


def cagr(r: Rechenweg, werte: Sequence[Eingabe], jahre: int) -> Decimal:
    jetzt = werte[-1]
    anfang = [w for w in werte if w.periode_ende.year == jetzt.periode_ende.year - jahre]
    if not anfang:
        raise EingabeFehlt(f"Wert {jahre} Geschäftsjahre vor", r.periode)
    _cp01(r, [anfang[0], jetzt], 2)
    r.pruefe("CP-02", "Wert im Stichtagsjahr", jetzt.periode_ende.isoformat() == r.periode)
    r.pruefe("CP-02", "Anfangs- und Endwert positiv", anfang[0].wert > 0 and jetzt.wert > 0)
    faktor = r.schritt("faktor", "ende / anfang", ende=jetzt, anfang=anfang[0])
    potenz = r.potenz("faktor_je_jahr", faktor, 1, jahre)
    return r.schritt("cagr", "p - 1", p=potenz)


def stdabw(r: Rechenweg, werte: Sequence[Eingabe], mindest: int) -> Decimal:
    _cp01(r, werte, mindest)
    namen = {f"x{i}": w for i, w in enumerate(werte)}
    mittel = r.schritt("mittelwert", f"({' + '.join(namen)}) / {len(werte)}", **namen)
    quadrate = {
        f"q{i}": r.schritt(f"abweichung_quadrat_{i}", "(x - m) * (x - m)", x=w, m=mittel)
        for i, w in enumerate(werte)
    }
    varianz = r.schritt("varianz", f"({' + '.join(quadrate)}) / {len(werte) - 1}", **quadrate)
    r.pruefe("CP-02", "Varianz nicht negativ", varianz >= 0)
    return r.schritt("stdabw", "wurzel(v)", v=varianz)


def steigung(r: Rechenweg, werte: Sequence[Eingabe], mindest: int) -> Decimal:
    """Theil-Sen: Median der Steigungen aller Paare, x ist das Geschäftsjahr."""
    _cp01(r, werte, mindest)
    paare = list(combinations(werte, 2))
    r.pruefe(
        "CP-02",
        "Jahresabstand jedes Paares positiv",
        all(b.periode_ende.year > a.periode_ende.year for a, b in paare),
    )
    steigungen = [
        r.schritt(
            f"steigung_{a.periode_ende.year}_{b.periode_ende.year}",
            f"(b - a) / {b.periode_ende.year - a.periode_ende.year}",
            a=a,
            b=b,
        )
        for a, b in paare
    ]
    return r.median("theil_sen", steigungen)


def plausibilitaet(
    subjekt: str, metric_id: str, werte: Sequence[Eingabe], schwelle: Decimal, mindest: int
) -> Ergebnis | None:
    """CP-05 für den Stichtagswert gegen die Vorjahre. None bei zu kurzer Historie."""
    if len(werte) - 1 < mindest:
        return None
    return dq.ausreisser(subjekt, metric_id, list(werte[:-1]), werte[-1], schwelle)


def _keine_werte(metric_id: str) -> Callable[[Rechenweg], Decimal]:
    def fn(r: Rechenweg) -> Decimal:
        raise EingabeFehlt(f"{metric_id} in keinem Geschäftsjahr berechenbar", r.periode)

    return fn


def trend(
    definition: Mapping[str, Any],
    subjekt: str,
    jahre: Mapping[date, Ergebnis],
    stichtag: date,
    waehrung: str | None,
    cfg: Mapping[str, Any],
    ausreisser: Mapping[str, Any],
) -> dict[str, Ergebnis]:
    """Alle Statistiken einer Kennzahl zum Stichtag. `cfg` ist `trends` aus metrics.yaml,
    `ausreisser` der gleichnamige Block aus quality.yaml."""
    metric_id, einheit = str(definition["id"]), str(definition["einheit"])
    punkte = _ab(_punkte(jahre, waehrung), stichtag)[-int(cfg["max_jahre"]) :]
    werte = [_eingabe(metric_id, einheit, p) for p in punkte]
    mindest = int(cfg["mindest_jahre"])

    def einzeln(statistik: str, fn: Callable[[Rechenweg], Decimal]) -> Ergebnis:
        r = _rechenweg(metric_id, statistik, subjekt, stichtag)
        return rechne(r, fn if werte else _keine_werte(metric_id))

    out = {
        "niveau": einzeln("niveau", lambda r: niveau(r, werte)),
        "veraenderung_vj": einzeln("veraenderung_vj", lambda r: veraenderung_vj(r, werte)),
        "cagr_3j": einzeln("cagr_3j", lambda r: cagr(r, werte, 3)),
        "cagr_5j": einzeln("cagr_5j", lambda r: cagr(r, werte, 5)),
        "stdabw": einzeln("stdabw", lambda r: stdabw(r, werte, mindest)),
        "steigung": einzeln("steigung", lambda r: steigung(r, werte, mindest)),
    }
    if werte and werte[-1].periode_ende == stichtag:
        z = plausibilitaet(
            subjekt,
            metric_id,
            werte,
            Decimal(str(ausreisser["schwelle"])),
            int(ausreisser["mindest_historie"]),
        )
        if z is not None:
            out["plausibilitaet"] = z
    return out


# ------------------------------------------------------------------ vertikale Analyse


def vertikal(reihen: Reihen, stichtag: date) -> dict[str, Ergebnis]:
    """Jeder Betrag des Jahres in Prozent vom Umsatz (Ströme) oder der Bilanzsumme (Stände)."""
    out: dict[str, Ergebnis] = {}
    for name in sorted(reihen.werte):
        if name in ("revenue", "total_assets") or not reihen.hat(name, stichtag):
            continue
        w = reihen.hole(name, stichtag)
        if w.einheit != "monetary":
            continue
        basis_name = "revenue" if w.periode_start is not None else "total_assets"
        r = Rechenweg(
            f"vertikal_{name}", VERSION, reihen.subjekt, stichtag.isoformat(), ("CP-01", "CP-02")
        )

        def rechnung(r: Rechenweg, w: Eingabe = w, basis_name: str = basis_name) -> Decimal:
            basis = reihen.hole(basis_name, stichtag)
            r.pruefe_eingaben(w, basis, gleiche_periode=w.periode_start is not None)
            if w.periode_start is None:
                r.pruefe("CP-01", "gleicher Stichtag", w.periode_ende == basis.periode_ende)
            r.pruefe("CP-02", f"{basis_name} positiv", basis.wert > 0)
            return r.schritt("anteil", "posten / basis", posten=w, basis=basis)

        out[name] = rechne(r, rechnung)
    return out
