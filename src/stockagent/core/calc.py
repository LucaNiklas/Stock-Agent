"""Rechenweg mit Prüfpunkten (HR-19, SPEC 12.7).

Jede Berechnung in `core/` ist eine Folge benannter Schritte. Die Formel eines Schritts ist
zugleich ihr Rechentext: `schritt("marge", "ebit / umsatz", ebit=..., umsatz=...)` rechnet genau
den angezeigten Ausdruck, damit Anzeige und Rechnung nie auseinanderlaufen. Erlaubt sind
`+ - * /`, Klammern, Zahlen, die Namen der Eingaben sowie `abs`, `min`, `max` und `runde`.
Den Median einer Liste rechnet `Rechenweg.median` als eigenen Schritt.

Nach jedem Abschnitt kommt ein Prüfpunkt aus dem Katalog CP-01 bis CP-08. Ein verletzter
Prüfpunkt der Stufe `stopp` wirft `PruefpunktVerletzt`, und `rechne` macht daraus ein Ergebnis
`unknown` mit Grund und Ungereimtheit INC-15. Mit verletztem Zwischenergebnis wird nie
weitergerechnet.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from enum import StrEnum
from typing import Any


class Stufe(StrEnum):
    STOPP = "stopp"
    WARNUNG = "warnung"


@dataclass(frozen=True)
class Pruefpunkt:
    cp_id: str
    pruefung: str
    stufe: Stufe


KATALOG: dict[str, Pruefpunkt] = {
    p.cp_id: p
    for p in (
        Pruefpunkt(
            "CP-01",
            "Eingaben vollständig und zusammenpassend (Währung, Einheit, Skalierung, Periode, "
            "Rechnungslegung)",
            Stufe.STOPP,
        ),
        Pruefpunkt("CP-02", "Vorzeichen und Wertebereich des Zwischenergebnisses", Stufe.STOPP),
        Pruefpunkt("CP-03", "Summenprobe: Teile ergeben das Ganze", Stufe.STOPP),
        Pruefpunkt("CP-04", "Gegenrechnung auf einem zweiten, unabhängigen Weg", Stufe.STOPP),
        Pruefpunkt("CP-05", "Plausibilität gegen die eigene Historie", Stufe.WARNUNG),
        Pruefpunkt("CP-06", "Rückrechnung reproduziert den Ausgangswert", Stufe.STOPP),
        Pruefpunkt("CP-07", "Strukturregeln einer Bewertung", Stufe.STOPP),
        Pruefpunkt("CP-08", "Wiederholbarkeit: zweimal gerechnet ergibt dasselbe", Stufe.STOPP),
    )
}

# Genauigkeit der Zwischenschritte. Gerundet wird erst bei der Anzeige (SPEC 12.7).
_PRECISION = 34


class RechenFehler(ValueError):
    """Formel unzulässig oder nicht auswertbar (Programmierfehler oder Division durch null)."""


class PruefpunktVerletzt(Exception):
    def __init__(self, rechenweg: Rechenweg, cp_id: str, text: str) -> None:
        super().__init__(f"{rechenweg.name}: {cp_id} verletzt: {text}")
        self.rechenweg = rechenweg
        self.cp_id = cp_id
        self.text = text


@dataclass(frozen=True)
class Eingabe:
    """Ein Wert mit Herkunft (HR-12): Quelle, Währung, Einheit und Periode."""

    wert: Decimal
    quelle: str
    einheit: str
    periode_ende: date
    waehrung: str | None = None
    periode_start: date | None = None

    def beschreibung(self) -> dict[str, Any]:
        return {
            "wert": str(self.wert),
            "quelle": self.quelle,
            "einheit": self.einheit,
            "waehrung": self.waehrung,
            "periode_start": self.periode_start.isoformat() if self.periode_start else None,
            "periode_ende": self.periode_ende.isoformat(),
        }


Wert = Eingabe | Decimal | int


@dataclass(frozen=True)
class Schritt:
    name: str
    formel: str
    eingaben: dict[str, Any]
    ergebnis: str


@dataclass(frozen=True)
class Pruefung:
    cp_id: str
    text: str
    bestanden: bool
    stufe: Stufe


@dataclass(frozen=True)
class Ergebnis:
    """Endergebnis einer Rechnung. `wert` ist None, wenn ein Prüfpunkt die Rechnung stoppte."""

    name: str
    wert: Decimal | None
    grund: str | None
    ungereimtheit: str | None
    warnungen: tuple[str, ...]
    rechenweg: dict[str, Any]

    @property
    def unknown(self) -> bool:
        return self.wert is None

    def rechenweg_json(self) -> str:
        return json.dumps(self.rechenweg, ensure_ascii=False, sort_keys=True)


def _wert(v: Wert) -> Decimal:
    if isinstance(v, Eingabe):
        return v.wert
    if isinstance(v, bool):
        raise RechenFehler("Wahrheitswert ist keine Zahl")
    return Decimal(v)


_BINOPS: dict[type[ast.operator], Callable[[Decimal, Decimal], Decimal]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}
_FUNCS: dict[str, Callable[..., Decimal]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "runde": lambda x: x.to_integral_value(),  # auf ganze Zahl, kaufmännisch zur geraden Ziffer
}


def _eval(node: ast.AST, names: Mapping[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval(node.body, names)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left, names), _eval(node.right, names))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, names)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        # Zahlen im Formeltext als Text übernehmen, damit 0.005 exakt bleibt
        return Decimal(str(node.value))
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise RechenFehler(f"Unbekannter Name in der Formel: {node.id}")
        return names[node.id]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
        and not node.keywords
    ):
        return Decimal(_FUNCS[node.func.id](*(_eval(a, names) for a in node.args)))
    raise RechenFehler(f"Unzulässiger Ausdruck in der Formel: {ast.dump(node)}")


def berechne(formel: str, **eingaben: Wert) -> Decimal:
    """Wertet eine Formel aus. Nur für Rechenweg und Tests, nie direkt in Fachcode."""
    try:
        tree = ast.parse(formel, mode="eval")
    except SyntaxError as exc:
        raise RechenFehler(f"Formel nicht lesbar: {formel}") from exc
    names = {k: _wert(v) for k, v in eingaben.items()}
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        ctx.traps[DivisionByZero] = True
        ctx.traps[InvalidOperation] = True
        try:
            return _eval(tree, names)
        except (DivisionByZero, InvalidOperation) as exc:
            raise RechenFehler(f"Nicht auswertbar: {formel}") from exc


@dataclass
class Rechenweg:
    """Schrittweise Rechnung mit Prüfpunkten. Beispiel in SPEC 12.7."""

    name: str
    version: str
    subjekt: str
    periode: str
    pflicht: tuple[str, ...] = ()
    schritte: list[Schritt] = field(default_factory=list)
    pruefungen: list[Pruefung] = field(default_factory=list)

    def __post_init__(self) -> None:
        unbekannt = set(self.pflicht) - set(KATALOG)
        if unbekannt:
            raise ValueError(f"Unbekannte Prüfpunkte: {sorted(unbekannt)}")

    def schritt(self, name: str, formel: str, **eingaben: Wert) -> Decimal:
        try:
            ergebnis = berechne(formel, **eingaben)
        except RechenFehler as exc:
            # Division durch null und Ähnliches ist ein verletzter Wertebereich (CP-02)
            self.pruefungen.append(Pruefung("CP-02", str(exc), False, Stufe.STOPP))
            raise PruefpunktVerletzt(self, "CP-02", str(exc)) from exc
        self.schritte.append(
            Schritt(
                name=name,
                formel=formel,
                eingaben={
                    k: v.beschreibung() if isinstance(v, Eingabe) else str(v)
                    for k, v in eingaben.items()
                },
                ergebnis=str(ergebnis),
            )
        )
        return ergebnis

    def median(self, name: str, werte: Sequence[Wert]) -> Decimal:
        """Median als protokollierter Schritt (für CP-05)."""
        try:
            ergebnis = median(_wert(w) for w in werte)
        except RechenFehler as exc:
            self.pruefungen.append(Pruefung("CP-02", str(exc), False, Stufe.STOPP))
            raise PruefpunktVerletzt(self, "CP-02", str(exc)) from exc
        self.schritte.append(
            Schritt(
                name=name,
                formel="median(werte)",
                eingaben={"werte": [str(_wert(w)) for w in werte]},
                ergebnis=str(ergebnis),
            )
        )
        return ergebnis

    def pruefe(self, cp_id: str, text: str, bestanden: bool, stufe: Stufe | None = None) -> None:
        """Prüfpunkt auswerten. `stufe` überschreibt die Stufe aus dem Katalog, wenn die
        Spezifikation für diesen Bereich eigene Schwellen nennt (etwa SPEC 3.2 Nr. 5)."""
        if cp_id not in KATALOG:
            raise ValueError(f"Unbekannter Prüfpunkt: {cp_id}")
        wirkung = stufe or KATALOG[cp_id].stufe
        self.pruefungen.append(Pruefung(cp_id, text, bool(bestanden), wirkung))
        if not bestanden and wirkung is Stufe.STOPP:
            raise PruefpunktVerletzt(self, cp_id, text)

    def pruefe_eingaben(self, *werte: Eingabe, gleiche_periode: bool = True) -> None:
        """CP-01: gleiche Währung und Einheit, auf Wunsch gleiche Periode."""
        waehrungen = {w.waehrung for w in werte}
        einheiten = {w.einheit for w in werte}
        perioden = {(w.periode_start, w.periode_ende) for w in werte}
        self.pruefe("CP-01", f"eine Währung {sorted(map(str, waehrungen))}", len(waehrungen) == 1)
        self.pruefe("CP-01", f"eine Einheit {sorted(einheiten)}", len(einheiten) == 1)
        if gleiche_periode:
            self.pruefe("CP-01", "gleiche Periode", len(perioden) == 1)

    def _protokoll(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "subjekt": self.subjekt,
            "periode": self.periode,
            "schritte": [s.__dict__ for s in self.schritte],
            "pruefungen": [
                {"cp_id": p.cp_id, "text": p.text, "bestanden": p.bestanden, "stufe": p.stufe}
                for p in self.pruefungen
            ],
        }

    def _warnungen(self) -> tuple[str, ...]:
        return tuple(
            f"{p.cp_id}: {p.text}"
            for p in self.pruefungen
            if not p.bestanden and p.stufe is Stufe.WARNUNG
        )

    def ergebnis(self, wert: Decimal) -> Ergebnis:
        fehlend = set(self.pflicht) - {p.cp_id for p in self.pruefungen}
        if fehlend:
            raise RuntimeError(
                f"{self.name}: Pflicht-Prüfpunkte nicht ausgewertet: {sorted(fehlend)}"
            )
        return Ergebnis(self.name, wert, None, None, self._warnungen(), self._protokoll())

    def abbruch(self, exc: PruefpunktVerletzt) -> Ergebnis:
        return Ergebnis(
            self.name,
            None,
            f"{exc.cp_id}: {exc.text}",
            "INC-15",
            self._warnungen(),
            self._protokoll(),
        )


def rechne(rechenweg: Rechenweg, rechnung: Callable[[Rechenweg], Decimal]) -> Ergebnis:
    """Führt eine Rechnung aus. Ein verletzter Stopp-Prüfpunkt ergibt `unknown` mit Grund."""
    try:
        wert = rechnung(rechenweg)
    except PruefpunktVerletzt as exc:
        return rechenweg.abbruch(exc)
    return rechenweg.ergebnis(wert)


def median(werte: Iterable[Decimal]) -> Decimal:
    """Median ohne Rundung. In Fachcode nur über `Rechenweg.median` verwenden."""
    s = sorted(werte)
    if not s:
        raise RechenFehler("Median einer leeren Liste")
    mitte = len(s) // 2
    if len(s) % 2:
        return s[mitte]
    return berechne("(a + b) / 2", a=s[mitte - 1], b=s[mitte])
