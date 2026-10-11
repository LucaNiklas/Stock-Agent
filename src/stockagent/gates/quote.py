"""Zitat-Gate (HR-03): Jedes Zitat muss wörtlich im gespeicherten Seitentext stehen.

Normalisiert werden nur Darstellungsunterschiede: Unicode-Form (Ligaturen), Anführungszeichen,
Bindestriche, weiche Trennstriche, Silbentrennung am Zeilenende und Leerraum. Groß- und
Kleinschreibung, Wortlaut und Zahlen bleiben unverändert.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from stockagent.gates import GateResult
from stockagent.schemas.base import AgentOutput, Claim, ClaimStatus

PageLookup = Callable[[str, int], str | None]

_QUOTES = str.maketrans({c: '"' for c in "„“”«»‟″"} | {c: "'" for c in "‚‘’‹›′"})
_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—"})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("­", "")
    text = text.translate(_QUOTES).translate(_DASHES)
    text = re.sub(r"(\w)-[ \t]*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def is_verbatim(quote: str, page_text: str) -> bool:
    q = normalize(quote)
    return bool(q) and q in normalize(page_text)


def apply(output: AgentOutput, lookup: PageLookup) -> tuple[AgentOutput, GateResult]:
    result = GateResult("quote")
    claims: list[Claim] = []
    for claim in output.claims:
        bad = False
        for ev in claim.evidence:
            if ev.quote is None:
                continue
            page_text = lookup(ev.doc_hash or "", ev.page or 0)
            if page_text is None:
                result.errors.append(f"{claim.claim_id}: Seite {ev.page} nicht gespeichert")
                bad = True
            elif not is_verbatim(ev.quote, page_text):
                result.errors.append(f"{claim.claim_id}: Zitat nicht wörtlich auf Seite {ev.page}")
                bad = True
        claims.append(claim.model_copy(update={"status": ClaimStatus.REJECTED}) if bad else claim)
    return output.model_copy(update={"claims": claims}), result
