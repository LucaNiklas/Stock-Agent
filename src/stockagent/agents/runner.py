"""Annahme von Agentenausgaben (SPEC 12.6, 15.1).

Jede Antwort durchläuft die Schranken in fester Reihenfolge:

1. Schema (Pydantic, `schemas/agents.py`) und Auftragskennung
2. Zahlen (HR-01): Ziffern in Freitext nur als Platzhalter, Kennzahl-ID, Seite oder Jahr
3. Beleg (HR-02): Claims ohne Beleg werden entfernt und vermerkt
4. Zitat (HR-03): jedes Zitat wörtlich auf der gespeicherten Seite, sonst Claim abgelehnt
5. Formulierung (HR-15): keine Kursziele, Empfehlungen oder Versprechen
6. Konsistenz: jeder Platzhalter und jede Kennzahl-Referenz hat einen gespeicherten Wert

Fehler der Stufen 1, 2, 5 und 6 sind hart: die Antwort geht mit Fehlermeldung zurück. Fehler der
Stufen 3 und 4 betreffen einzelne Claims: Solange Wiederholungen übrig sind, geht die Antwort
ebenfalls zurück, damit der Agent Zitate berichtigen kann. Beim letzten Versuch wird sie ohne die
betroffenen Claims angenommen (INC-14).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from stockagent.gates import number, schema, wording
from stockagent.gates.quote import is_verbatim
from stockagent.platzhalter import REF, Werte, refs_im_text
from stockagent.schemas.agents import ANTWORTEN, AgentAntwort
from stockagent.schemas.base import Claim, ClaimStatus, RemovedClaim

PageLookup = Callable[[str, int], str | None]


@dataclass
class Pruefung:
    antwort: AgentAntwort | None
    hart: list[str] = field(default_factory=list)
    weich: list[str] = field(default_factory=list)
    entfernt: list[RemovedClaim] = field(default_factory=list)
    abgelehnt: dict[str, str] = field(default_factory=dict)  # claim_id -> Grund

    @property
    def ok(self) -> bool:
        return self.antwort is not None and not self.hart and not self.weich


def json_aus_text(text: str) -> str:
    """JSON aus der letzten Nachricht eines Agenten: Codeblock oder äußerstes Objekt."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        return m.group(1)
    a, b = text.find("{"), text.rfind("}")
    return text[a : b + 1] if a >= 0 and b > a else text


def auftrag_aus_text(text: str) -> str | None:
    """Auftragskennung `<run_id>/<auftrag_id>` aus einer Antwort, auch wenn sie ungültig ist."""
    try:
        data = json.loads(json_aus_text(text))
    except ValueError:
        m = re.search(r'"auftrag"\s*:\s*"([^"]+)"', text)
        return m.group(1) if m else None
    wert = data.get("auftrag") if isinstance(data, dict) else None
    return str(wert) if wert else None


def _refs(c: Claim) -> list[str]:
    out = [*refs_im_text(c.text), *c.metric_refs]
    out += [e.metric_ref for e in c.evidence if e.metric_ref]
    return out


def _bereich(ref: str) -> list[str]:
    """`ebit_margin@2021..2025` -> einzelne Jahre, sonst unverändert."""
    m = re.match(r"^([a-z][a-z0-9_]*)@(\d{4})\.\.(\d{4})$", ref)
    if not m:
        return [ref]
    a, b = int(m.group(2)), int(m.group(3))
    return [f"{m.group(1)}@{j}" for j in range(a, b + 1)] if a <= b <= a + 15 else [ref]


def pruefe(
    text: str,
    agent: str,
    auftrag: str,
    werte: Werte,
    seite: PageLookup,
    zusatz: Callable[[AgentAntwort], list[str]] | None = None,
) -> Pruefung:
    modell = ANTWORTEN[agent]
    antwort, res = schema.check(json_aus_text(text), modell)
    if antwort is None:
        return Pruefung(None, [f"Schema: {e}" for e in res.errors])
    p = Pruefung(antwort)
    if antwort.auftrag != auftrag:
        p.hart.append(f"Schema: auftrag ist {antwort.auftrag}, erwartet {auftrag}")
    p.hart += [f"Zahlen: {e}" for e in number.check(antwort).errors]
    p.hart += [f"Formulierung: {e}" for e in wording.check(antwort).errors]

    for c in antwort.claims:
        if not c.evidence:
            p.entfernt.append(RemovedClaim(claim=c, reason="kein Beleg (HR-02)"))
            p.weich.append(f"Beleg: {c.claim_id} ohne Beleg")
            continue
        if c.type == "quantitative" and not _refs(c):
            p.hart.append(f"Konsistenz: {c.claim_id} quantitativ ohne Kennzahl-Referenz")
        for ev in c.evidence:
            if ev.doc_hash is None or ev.page is None:
                continue
            seitentext = seite(ev.doc_hash, ev.page)
            if seitentext is None:
                p.abgelehnt[c.claim_id] = f"Seite {ev.page} von {ev.doc_hash[:19]} nicht geladen"
            elif ev.quote is None:
                p.abgelehnt[c.claim_id] = "Dokumentbeleg ohne wörtliches Zitat"
            elif not is_verbatim(ev.quote, seitentext):
                p.abgelehnt[c.claim_id] = f"Zitat nicht wörtlich auf Seite {ev.page}"
    p.weich += [f"Zitat: {cid}: {grund}" for cid, grund in p.abgelehnt.items()]

    refs = [r for c in antwort.claims for x in _refs(c) for r in _bereich(x)]
    refs += [r for _, t in number.free_text_fields(antwort) for r in refs_im_text(t)]
    falsch = sorted({r for r in refs if not REF.match(r)})
    p.hart += [f"Konsistenz: Referenz {r} hat nicht die Form metric_id@periode" for r in falsch]
    p.hart += [
        f"Konsistenz: kein gespeicherter Wert für {r}"
        for r in werte.fehlend(r for r in refs if REF.match(r))
    ]
    if zusatz is not None:
        p.hart.extend(zusatz(antwort))
    return p


def bereinigt(p: Pruefung) -> AgentAntwort:
    """Antwort ohne entfernte und mit abgelehnten Claims (Status `rejected`)."""
    assert p.antwort is not None
    entfernt = {r.claim.claim_id for r in p.entfernt}
    claims = [
        c.model_copy(update={"status": ClaimStatus.REJECTED}) if c.claim_id in p.abgelehnt else c
        for c in p.antwort.claims
        if c.claim_id not in entfernt
    ]
    return p.antwort.model_copy(update={"claims": claims})


def meldung(p: Pruefung, versuch: int, uebrig: int) -> str:
    """Fehlermeldung an den Agenten (Exit-Code 2 des Hooks oder Hauptsitzung)."""
    zeilen = [f"Antwort abgelehnt (Versuch {versuch}, noch {uebrig} Wiederholung(en)):"]
    zeilen += [f"- {e}" for e in [*p.hart, *p.weich][:40]]
    zeilen.append(
        "Berichtige nur diese Punkte und antworte erneut ausschließlich mit dem vollständigen JSON."
    )
    return "\n".join(zeilen)


def als_dict(obj: BaseModel) -> dict[str, object]:
    data: dict[str, object] = json.loads(obj.model_dump_json())
    return data
