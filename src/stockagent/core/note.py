"""Note, Konfidenz, Risiko und Kategorie (SPEC 6, ADR 0007).

Alles deterministisch (HR-13) und über den Rechenweg mit Prüfpunkten (CP-07 Strukturregeln einer
Bewertung). Die Eingaben kommen fertig gerechnet aus der Tabelle `metrics` (eigene Firma und
Vergleichsgruppe), Schwellen und Gewichte aus `config/scoring.yaml` und `config/scorecards.yaml`.

Note:
1. Je Kennzahl das Perzentil der Firma in der Vergleichsgruppe (Rang, Gleichstände zur Hälfte):
   (Anzahl kleiner + 0,5 * Anzahl gleich) / Anzahl * 100, bei „niedriger ist besser“ 100 minus das.
   Die Firma zählt zur Gruppe. Fehlt ihr Wert, fehlt die Kennzahl (HR-05, kein Schätzen).
2. Säulenwert = Mittel der vorhandenen Kennzahl-Perzentile der Säule.
3. Gesamtwert = gewichtetes Mittel der Säulen mit Wert, Gewichte auf diese Säulen verteilt
   (ohne Insider-Daten geht deren Gewicht auf die anderen Säulen).
4. Kappung nach SPEC 6.2 Nr. 6, dann Note nach den Schwellen.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from stockagent.core.calc import NichtDefiniert, Rechenweg, rechne

VERSION = "1.0"
Schluessel = tuple[str, str]  # (Kennzahl, Statistik)


@dataclass(frozen=True)
class Kennzahlrang:
    kennzahl: str
    statistik: str
    saeule: str
    wert: Decimal | None
    perzentil: Decimal | None
    gruppe_n: int


@dataclass
class NotenErgebnis:
    gesamt: Decimal | None
    note: str
    saeulen: dict[str, Decimal | None] = field(default_factory=dict)
    abdeckung: Decimal = Decimal(0)
    kappungen: list[str] = field(default_factory=list)
    raenge: list[Kennzahlrang] = field(default_factory=list)
    grund: str | None = None
    rechenweg: dict[str, Any] = field(default_factory=dict)


def _perzentil(
    r: Rechenweg, name: str, wert: Decimal, gruppe: Sequence[Decimal], richtung: str
) -> Decimal:
    if richtung == "absolut":
        # Fester Wert 0 bis 100 ohne Rang in der Gruppe (Säule Insider, SPEC 3.8, ADR 0012)
        p = r.schritt(f"wert_{name}", "x", x=wert)
        r.pruefe("CP-07", f"{name}: Wert zwischen 0 und 100", 0 <= p <= 100)
        return p
    kleiner = sum(1 for g in gruppe if g < wert)
    gleich = sum(1 for g in gruppe if g == wert)
    p = r.schritt(
        f"perzentil_{name}",
        "(kleiner + 0.5 * gleich) / n * 100",
        kleiner=kleiner,
        gleich=gleich,
        n=len(gruppe),
    )
    if richtung == "niedrig":
        p = r.schritt(f"perzentil_{name}_umgekehrt", "100 - p", p=p)
    r.pruefe("CP-07", f"{name}: Perzentil zwischen 0 und 100", 0 <= p <= 100)
    return p


def note(
    subjekt: str,
    stichtag: str,
    eigene: Mapping[Schluessel, Decimal | None],
    gruppe: Sequence[Mapping[Schluessel, Decimal | None]],
    scorecard: Mapping[str, Any],
    scoring: Mapping[str, Any],
    kappungen: Sequence[str],
) -> NotenErgebnis:
    """Note der Firma gegen ihre Vergleichsgruppe. `gruppe` enthält die Firma selbst nicht,
    sie wird hinzugefügt. `kappungen` sind die Bedingungen aus SPEC 6.2 Nr. 6, die zutreffen."""
    out = NotenErgebnis(None, "N")
    r = Rechenweg("note", VERSION, subjekt, stichtag, pflicht=("CP-07",))

    def rechnung(r: Rechenweg) -> Decimal:
        gewichte = {k: Decimal(str(v)) for k, v in scoring["saeulen_gewichte"].items()}
        r.pruefe("CP-07", "Säulengewichte ergeben 1", sum(gewichte.values()) == 1)
        if "insider_max_weight" in scoring:
            # SPEC 3.8 Nr. 10: das Insider-Signal kann eine schwache Aktie nicht hochziehen
            r.pruefe(
                "CP-07",
                "Gewicht Insider höchstens insider_max_weight",
                gewichte.get("insider", Decimal(0)) <= Decimal(str(scoring["insider_max_weight"])),
            )
        saeulen: dict[str, Decimal | None] = {}
        definiert = vorhanden = Decimal(0)
        for saeule, kennzahlen in scorecard["saeulen"].items():
            perz: dict[str, Decimal] = {}
            for k in kennzahlen:
                key = (str(k["kennzahl"]), str(k["statistik"]))
                eigen = eigene.get(key)
                werte: list[Decimal] = [v for g in gruppe if (v := g.get(key)) is not None]
                name = f"{saeule}_{key[0]}_{key[1]}"
                if eigen is None:
                    out.raenge.append(Kennzahlrang(key[0], key[1], saeule, None, None, len(werte)))
                    continue
                p = _perzentil(r, name, eigen, [*werte, eigen], str(k["richtung"]))
                perz[name] = p
                out.raenge.append(Kennzahlrang(key[0], key[1], saeule, eigen, p, len(werte) + 1))
            # Säule nur aus festen Werten (Insider) ohne Wert: kein Mangel an Daten, sondern kein
            # Signal. Sie zählt dann nicht zur Abdeckung, ihr Gewicht geht auf die anderen Säulen
            nur_signal = all(str(k["richtung"]) == "absolut" for k in kennzahlen)
            if kennzahlen and not (nur_signal and not perz):
                g = gewichte[saeule]
                definiert = r.schritt(f"definiert_{saeule}", "d + g", d=definiert, g=g)
                vorhanden = r.schritt(
                    f"vorhanden_{saeule}",
                    f"v + g * {len(perz)} / {len(kennzahlen)}",
                    v=vorhanden,
                    g=g,
                )
            saeulen[saeule] = (
                r.schritt(f"saeule_{saeule}", f"({' + '.join(perz)}) / {len(perz)}", **perz)
                if perz
                else None
            )
        out.saeulen = saeulen
        out.abdeckung = (
            r.schritt("abdeckung", "v / d", v=vorhanden, d=definiert) if definiert else Decimal(0)
        )
        mit_wert = {s: v for s, v in saeulen.items() if v is not None}
        if not mit_wert:
            raise NichtDefiniert("keine Kennzahl der Scorecard vorhanden")
        summe_gewichte = r.schritt(
            "gewichte_mit_wert",
            " + ".join(f"g_{s}" for s in mit_wert),
            **{f"g_{s}": gewichte[s] for s in mit_wert},
        )
        gesamt = r.schritt(
            "gesamt_ungekappt",
            f"({' + '.join(f'g_{s} * w_{s}' for s in mit_wert)}) / summe",
            summe=summe_gewichte,
            **{f"g_{s}": gewichte[s] for s in mit_wert},
            **{f"w_{s}": v for s, v in mit_wert.items()},
        )
        alle_kappungen = list(kappungen)
        if out.abdeckung < Decimal(str(scoring["abdeckung_mindest"])):
            alle_kappungen.append("abdeckung_gering")
        for kappung in alle_kappungen:
            grenze = Decimal(str(scoring["kappung"][kappung]))
            if gesamt > grenze:
                gesamt = r.schritt(f"kappung_{kappung}", "min(g, grenze)", g=gesamt, grenze=grenze)
            out.kappungen.append(kappung)
        r.pruefe("CP-07", "Gesamtwert zwischen 0 und 100", 0 <= gesamt <= 100)
        return gesamt

    erg = rechne(r, rechnung) if gruppe is not None else None
    if erg is None or erg.wert is None:
        out.grund = erg.grund if erg else "keine Vergleichsgruppe"
        if erg is not None:
            out.rechenweg = erg.rechenweg
        return out
    out.gesamt = erg.wert
    out.rechenweg = erg.rechenweg
    out.note = next(
        n
        for n, grenze in sorted(scoring["noten"].items(), key=lambda x: -int(x[1]))
        if erg.wert >= int(grenze)
    )
    return out


def gewichte_horizont(gewichte: Mapping[str, Any], momentum_anteil: Decimal) -> dict[str, Decimal]:
    """Säulengewichte für einen Anlagehorizont (ADR 0011): Momentum bekommt `momentum_anteil`,
    die übrigen Säulen behalten ihr Verhältnis und teilen sich den Rest."""
    if not 0 <= momentum_anteil <= 1:
        raise ValueError(f"Momentum-Anteil außerhalb 0 bis 1: {momentum_anteil}")
    rest = 1 - momentum_anteil
    out = {k: Decimal(str(v)) * rest for k, v in gewichte.items() if k != "momentum"}
    out["momentum"] = momentum_anteil
    return out


# ------------------------------------------------------------------ Konfidenz


GROESSEN = ("nano", "micro", "small", "mid", "large", "mega")


def groessenklasse(boersenwert_eur: Decimal | None, cfg: Mapping[str, Any]) -> str | None:
    if boersenwert_eur is None:
        return None
    for klasse in reversed(GROESSEN):
        if boersenwert_eur >= Decimal(str(cfg[klasse])):
            return klasse
    return "nano"


def konfidenz(
    jahre: int,
    abdeckung: Decimal,
    groesse: str | None,
    quellenabgleich_ok: bool,
    standard_ok: bool,
    cfg: Mapping[str, Any],
) -> tuple[str, list[str]]:
    """K1 bis K4 nach SPEC 6.3. Zurück die Stufe und warum keine höhere erreicht ist."""
    gruende: list[str] = []
    for stufe in ("K1", "K2", "K3"):
        b = cfg[stufe]
        fehlt = []
        if jahre < int(b["jahre"]):
            fehlt.append(f"Historie {jahre} Jahre, nötig {b['jahre']}")
        if abdeckung < Decimal(str(b["abdeckung"])):
            fehlt.append(f"Abdeckung {abdeckung:.0%}, nötig {Decimal(str(b['abdeckung'])):.0%}")
        if "groesse_mindestens" in b and (
            groesse is None
            or GROESSEN.index(groesse) < GROESSEN.index(str(b["groesse_mindestens"]))
        ):
            fehlt.append(f"Größenklasse {groesse or 'unbekannt'}")
        if stufe in ("K1", "K2") and not quellenabgleich_ok:
            fehlt.append("Quellenabgleich nicht bestanden")
        if stufe in ("K1", "K2") and not standard_ok:
            fehlt.append("weder IFRS noch US-GAAP")
        if not fehlt:
            return stufe, gruende
        gruende.append(f"nicht {stufe}: {'; '.join(fehlt)}")
    return "K4", gruende


def konfidenz_abschlag(stufe: str, stufen: int, grund: str) -> tuple[str, str | None]:
    """Konfidenz um `stufen` Stufen senken, höchstens bis K4 (SPEC 3.11: G-Score als Hilfsmaß)."""
    if stufen <= 0:
        return stufe, None
    reihe = ("K1", "K2", "K3", "K4")
    neu = reihe[min(reihe.index(stufe) + stufen, len(reihe) - 1)]
    return neu, f"Abschlag {stufe} -> {neu}: {grund}"


# ------------------------------------------------------------------ Risiko


def risiko(
    eingaben: Mapping[str, Decimal | str | None], cfg: Mapping[str, Any]
) -> tuple[str | None, dict[str, int]]:
    """R1 bis R5 nach SPEC 6.4: je Eingang Stufe 1 bis 5 nach den Schwellen in
    `config/scoring.yaml` (bis zum Lauf über das Universum statt Quintilen), Mittel gerundet."""
    stufen: dict[str, int] = {}
    for name, wert in eingaben.items():
        if wert is None:
            continue
        if name == "groesse":
            stufen[name] = int(cfg["groesse"][str(wert)])
            continue
        grenzen = [Decimal(str(x)) for x in cfg[name]]
        stufen[name] = 1 + sum(1 for g in grenzen if Decimal(str(wert)) > g)
    if len(stufen) < 3:
        return None, stufen
    r = Rechenweg("risiko", VERSION, "", "", pflicht=())
    mittel = r.schritt(
        "mittel",
        f"runde(({' + '.join(stufen)}) / {len(stufen)})",
        **{k: v for k, v in stufen.items()},
    )
    return f"R{int(mittel)}", stufen


# ------------------------------------------------------------------ Kategorie


def kategorie(
    note_: str,
    konfidenz_: str,
    stopp: bool,
    bewertung_erfuellt: bool | None,
    vorige_noten: Sequence[str],
    aufwaertstrend: bool,
    hysterese_laeufe: int,
) -> tuple[str, str]:
    """Kategorie nach SPEC 6.5 mit Hysterese aus 9.5. Zurück Kategorie und Begründung."""
    if note_ == "N":
        return "Nicht bewertbar", "Status N"
    if note_ in ("D", "E"):
        return "Unattraktiv", f"Note {note_}"
    if note_ in ("A", "B"):
        gruende = []
        if konfidenz_ not in ("K1", "K2"):
            gruende.append(f"Konfidenz {konfidenz_}")
        if stopp:
            gruende.append("Stopp-Flag")
        if bewertung_erfuellt is not True:
            gruende.append("Bewertungsbedingung nicht erfüllt")
        letzte = [*vorige_noten[-(hysterese_laeufe - 1) :]] if hysterese_laeufe > 1 else []
        if hysterese_laeufe > 1 and (
            len(letzte) < hysterese_laeufe - 1 or any(n not in ("A", "B") for n in letzte)
        ):
            gruende.append(f"noch nicht in {hysterese_laeufe} Läufen nacheinander A oder B")
        if not gruende:
            return "Attraktiv", f"Note {note_}, {konfidenz_}, Bewertungsbedingung erfüllt"
        return "Beobachten", f"Note {note_}, aber " + ", ".join(gruende)
    if note_ == "C" and aufwaertstrend:
        return "Beobachten", "Note C mit Aufwärtstrend"
    return "Neutral", f"Note {note_}"
