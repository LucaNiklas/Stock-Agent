"""Antwortformate der Agenten der Tiefenanalyse (Bauschritt 6, SPEC 8.3 und 8.4).

Ein Agent liefert nur seine Antwort (`*Antwort`). Den Umschlag (`Envelope`: Lauf, Agent, Version,
Prompt-Hash, Modell) setzt Python bei der Annahme (`stockagent accept`), damit der Agent ihn nicht
falsch ausfüllen kann. Freitext nur in `FreeText`-Feldern (HR-01), Zahlen dort nur als Platzhalter
`{{metric_id@periode}}`. Strukturierte Felder sind Aufzählungen, nie Finanzwerte.

Claim-IDs sind je Antwort eindeutig (`c-0001`). Python macht daraus laufweit `<auftrag>:<claim_id>`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from stockagent.schemas.base import FREE_TEXT, Claim, _Strict

KurzText = Annotated[str, Field(max_length=300), FREE_TEXT]
AUFTRAG = r"^[A-Za-z0-9_.:-]+/[A-Za-z0-9_]+$"


class Unbekannt(_Strict):
    """HR-05: was die Daten nicht beantworten, mit Grund."""

    frage: KurzText
    grund: KurzText


class Nachforderung(_Strict):
    """Fehlende Information an die Recherche (SPEC 8.5). Die Auswertung sucht nie selbst."""

    dokumenttyp: Literal[
        "geschaeftsbericht", "quartalsbericht", "verguetungsbericht", "proxy", "ad_hoc", "sonstiges"
    ]
    periode: str = Field(pattern=r"^\d{4}(-\d{2})?$|^letzte_12_monate$")
    grund: KurzText


class AgentAntwort(_Strict):
    """Gemeinsamer Teil jeder Antwort."""

    auftrag: str = Field(pattern=AUFTRAG)  # <run_id>/<auftrag_id> aus der Eingabedatei
    claims: list[Claim] = Field(default_factory=list)
    unbekannt: list[Unbekannt] = Field(default_factory=list)

    @model_validator(mode="after")
    def _eindeutig(self) -> AgentAntwort:
        ids = [c.claim_id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim_id doppelt")
        return self

    def claim_ids(self) -> set[str]:
        return {c.claim_id for c in self.claims}

    def _verweise(self, ids: list[str], wo: str) -> None:
        fehlt = sorted(set(ids).difference(self.claim_ids()))
        if fehlt:
            raise ValueError(f"{wo}: unbekannte claim_id {', '.join(fehlt)}")


# ------------------------------------------------------------------ Recherche


class DokumentFund(_Strict):
    url: str = Field(pattern=r"^https://[^\s]+$", max_length=500)
    dokumenttyp: str = Field(max_length=40)
    periode: str = Field(max_length=20)


class NichtGefunden(_Strict):
    dokumenttyp: str = Field(max_length=40)
    versuchte_quellen: list[str] = Field(default_factory=list, max_length=20)
    grund: KurzText


class A1Antwort(AgentAntwort):
    """A1 Datenbeschaffung: nur Fundstellen, keine Zahlen und keine Claims."""

    dokumente: list[DokumentFund] = Field(default_factory=list, max_length=10)
    nicht_gefunden: list[NichtGefunden] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ohne_claims(self) -> A1Antwort:
        if self.claims:
            raise ValueError("A1 liefert keine Claims, nur Dokumente")
        return self


# ------------------------------------------------------------------ Auswertung


class A3Antwort(AgentAntwort):
    """A3 Fundamentalanalyse."""

    ertragsqualitaet: Literal["hoch", "mittel", "niedrig", "unknown"]
    ertragsqualitaet_claims: list[str] = Field(default_factory=list)
    nachforderungen: list[Nachforderung] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _refs(self) -> A3Antwort:
        self._verweise(self.ertragsqualitaet_claims, "ertragsqualitaet_claims")
        return self


THEMEN = (
    "geschaeftsmodell",
    "wettbewerbsvorteil",
    "segmente",
    "kundenkonzentration",
    "risikofaktoren",
    "management_anreize",
    "kapitalallokation",
    "bilanzpolitik",
    "pruefungsschwerpunkte",
)
Thema = Literal[
    "geschaeftsmodell",
    "wettbewerbsvorteil",
    "segmente",
    "kundenkonzentration",
    "risikofaktoren",
    "management_anreize",
    "kapitalallokation",
    "bilanzpolitik",
    "pruefungsschwerpunkte",
]


class ThemaBefund(_Strict):
    thema: Thema
    einordnung: Literal["positiv", "neutral", "negativ", "unknown"]
    claim_ids: list[str] = Field(default_factory=list)


class A4Antwort(AgentAntwort):
    """A4 Qualitative Analyse: je Thema aus SPEC 3.7 eine Einordnung mit Claims."""

    themen: list[ThemaBefund]
    nachforderungen: list[Nachforderung] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _refs(self) -> A4Antwort:
        for t in self.themen:
            self._verweise(t.claim_ids, f"themen.{t.thema}")
        if len({t.thema for t in self.themen}) != len(self.themen):
            raise ValueError("Thema doppelt")
        return self


Groesse = Literal["wachstum", "marge", "investition", "working_capital"]
Stufe = Literal["niedrig", "mittel", "hoch"]


class Annahme(_Strict):
    szenario: Literal["bear", "base", "bull"]
    groesse: Groesse
    stufe: Stufe
    claim_ids: list[str] = Field(default_factory=list)


class A5Antwort(AgentAntwort):
    """A5 Bewertung: je Szenario und Größe eine Stufe aus der eigenen Historie (SPEC 3.6).
    Die Werte rechnet Python."""

    annahmen: list[Annahme]
    reverse_dcf_claims: list[str] = Field(default_factory=list)
    nachforderungen: list[Nachforderung] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _vollstaendig(self) -> A5Antwort:
        paare = [(a.szenario, a.groesse) for a in self.annahmen]
        if len(paare) != 12 or len(set(paare)) != 12:
            raise ValueError("je Szenario (bear, base, bull) und Größe genau eine Annahme")
        for a in self.annahmen:
            self._verweise(a.claim_ids, f"annahmen.{a.szenario}.{a.groesse}")
        self._verweise(self.reverse_dcf_claims, "reverse_dcf_claims")
        return self


class Risiko(_Strict):
    titel: KurzText
    fruehindikator: KurzText
    claim_ids: list[str] = Field(min_length=1)


class A7Antwort(AgentAntwort):
    """A7 Gegenposition mit Pre-Mortem: die drei realistischsten Wege des Scheiterns."""

    risiken: list[Risiko] = Field(min_length=1, max_length=3)
    pre_mortem: Annotated[str, Field(max_length=1200), FREE_TEXT]

    @model_validator(mode="after")
    def _refs(self) -> A7Antwort:
        for i, r in enumerate(self.risiken, start=1):
            self._verweise(r.claim_ids, f"risiken[{i}]")
        return self


class Erwiderung(_Strict):
    risiko: int = Field(ge=1, le=3)
    offen: bool  # True: das Risiko bleibt offen und steht so im Bericht
    claim_ids: list[str] = Field(default_factory=list)


class ErwiderungAntwort(AgentAntwort):
    """Erwiderung von A3 auf die Gegenposition (eine Runde)."""

    erwiderungen: list[Erwiderung] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def _refs(self) -> ErwiderungAntwort:
        for e in self.erwiderungen:
            self._verweise(e.claim_ids, f"erwiderungen[{e.risiko}]")
        return self


class A9Antwort(AgentAntwort):
    """A9 Synthese: These in höchstens drei Sätzen aus geprüften Claims. Keine neuen Claims."""

    these: Annotated[str, Field(max_length=800), FREE_TEXT]
    these_claims: list[str] = Field(min_length=1)  # laufweite Schlüssel geprüfter Claims

    @model_validator(mode="after")
    def _ohne_neue(self) -> A9Antwort:
        if self.claims:
            raise ValueError("A9 schreibt keine neuen Claims")
        if len([s for s in self.these.replace("!", ".").split(".") if s.strip()]) > 3:
            raise ValueError("These höchstens drei Sätze")
        return self


# ------------------------------------------------------------------ Prüfung


class J1Ergebnis(_Strict):
    ref: str = Field(pattern=r"^[a-z][a-z0-9_]*@[A-Za-z0-9_]+$")
    status: Literal["berechnet", "not_computable"]
    wert: str | None = Field(default=None, pattern=r"^-?\d+(\.\d+)?(E[+-]?\d+)?$")
    grund: KurzText | None = None

    @model_validator(mode="after")
    def _wert(self) -> J1Ergebnis:
        if (self.status == "berechnet") != (self.wert is not None):
            raise ValueError("Wert genau dann, wenn berechnet")
        return self


class J1Antwort(AgentAntwort):
    """J1 Zahlenprüfer: jeden Platzhalter über das Werkzeug nachgerechnet, blind (HR-14)."""

    ergebnisse: list[J1Ergebnis]

    @model_validator(mode="after")
    def _ohne_claims(self) -> J1Antwort:
        if self.claims:
            raise ValueError("J1 schreibt keine Claims")
        return self


class J2Urteil(_Strict):
    claim: str = Field(max_length=60)  # laufweiter Schlüssel
    urteil: Literal["supported", "partially", "not_supported", "contradicted"]
    begruendung: KurzText


class J2Antwort(AgentAntwort):
    """J2 Belegprüfer: deckt die Belegstelle die Aussage?"""

    urteile: list[J2Urteil]

    @model_validator(mode="after")
    def _ohne_claims(self) -> J2Antwort:
        if self.claims:
            raise ValueError("J2 schreibt keine Claims")
        return self


ANTWORTEN: dict[str, type[AgentAntwort]] = {
    "A1": A1Antwort,
    "A3": A3Antwort,
    "A4": A4Antwort,
    "A5": A5Antwort,
    "A7": A7Antwort,
    "A3E": ErwiderungAntwort,
    "A9": A9Antwort,
    "J1": J1Antwort,
    "J2": J2Antwort,
}
