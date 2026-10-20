"""EU-Abschlussdaten aus ESEF-Berichten über filings.xbrl.org (SPEC 7.2, Bauschritt 7, ADR 0009).

filings.xbrl.org sammelt die Inline-XBRL-Jahresberichte aus den nationalen Registern der EU und
stellt je Einreichung eine xBRL-JSON-Datei bereit (Format OIM, https://xbrl.org/2021/xbrl-json).
Gesucht wird über die LEI aus der GLEIF. Abdeckung ab Geschäftsjahr 2020. Deutsche Berichte fehlen
dort (Stand 20.10.2026: 0 Einreichungen mit Land DE), weil das Unternehmensregister nicht
angebunden ist.

Perioden im xBRL-JSON sind halboffen: „2025-01-01T00:00:00/2026-01-01T00:00:00“ ist das Jahr bis
31.12.2025, ein Stand „2026-01-01T00:00:00“ ist der Stand am 31.12.2025. Werte mit weiteren
Dimensionen (Segmente, Achsen) bleiben außen vor, wie beim zweiten Weg der SEC. Firmeneigene
Konzepte (etwa `asml:NetSystemSales`) bleiben gespeichert, die Zuordnung nutzt nur
Standardkonzepte. Veröffentlichung = Tag der Aufnahme bei filings.xbrl.org (der tatsächliche
Tag der Veröffentlichung liegt davor, so bleibt Point-in-Time auf der sicheren Seite).
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from stockagent.data import rawstore
from stockagent.data.http import fetch
from stockagent.data.store import DocumentRow, FactRow

STANDARD = ("ifrs-full:",)


class EsefFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Einreichung:
    fxo_id: str  # etwa 724500Y6DUVHQD6OXN27-2025-12-31-ESEF-NL-0
    lei: str
    period_end: date
    land: str
    json_url: str
    report_url: str
    aufgenommen: datetime
    fehler: int


def issuer_id(lei: str) -> str:
    return f"lei:{lei.upper()}"


def parse_filings(raw: bytes, lei: str) -> list[Einreichung]:
    try:
        data = json.loads(raw)["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise EsefFormatError("Antwort von filings.xbrl.org ohne Daten") from exc
    out = []
    for x in data:
        a = x.get("attributes", {})
        if not a.get("json_url"):
            continue
        out.append(
            Einreichung(
                fxo_id=str(a["fxo_id"]),
                lei=lei,
                period_end=date.fromisoformat(a["period_end"]),
                land=str(a.get("country") or ""),
                json_url=str(a["json_url"]),
                report_url=str(a.get("report_url") or ""),
                aufgenommen=datetime.fromisoformat(str(a["date_added"])).replace(tzinfo=UTC),
                fehler=int(a.get("error_count") or 0),
            )
        )
    return sorted(out, key=lambda e: (e.period_end, e.fxo_id))


def _zeitpunkt(text: str) -> date:
    """Halboffenes Ende: Mitternacht des Folgetags -> Vortag."""
    dt = datetime.fromisoformat(text)
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        return dt.date() - timedelta(days=1)
    return dt.date()


def _periode(text: str) -> tuple[date | None, date]:
    if "/" in text:
        a, b = text.split("/", 1)
        return datetime.fromisoformat(a).date(), _zeitpunkt(b)
    return None, _zeitpunkt(text)


def _einheit(unit: str | None) -> tuple[str, str | None, str] | None:
    """(Einheit, Währung, Einheit laut Quelle) oder None außerhalb von HR-12."""
    if unit is None:
        return "pure", None, "pure"
    if unit.startswith("iso4217:") and "/" not in unit:
        w = unit.split(":", 1)[1]
        return "monetary", w, w
    if unit == "xbrli:shares":
        return "shares", None, "shares"
    if unit == "xbrli:pure":
        return "pure", None, "pure"
    zaehler, _, nenner = unit.partition("/")
    if zaehler.startswith("iso4217:") and nenner == "xbrli:shares":
        w = zaehler.split(":", 1)[1]
        return "per_share", w, f"{w}/shares"
    return None


def parse_xbrl_json(
    raw: bytes,
    e: Einreichung,
    *,
    raw_sha256: str,
    retrieved_at: datetime,
    source_url: str,
) -> tuple[list[FactRow], DocumentRow, Counter[str]]:
    """Werte einer Einreichung. Zurück auch die Zahl übersprungener Werte je Grund."""
    try:
        body = json.loads(raw)
        facts: dict[str, Any] = body["facts"]
    except (ValueError, KeyError, TypeError) as exc:
        raise EsefFormatError("xBRL-JSON ohne facts") from exc
    iid = issuer_id(e.lei)
    out: list[FactRow] = []
    uebersprungen: Counter[str] = Counter()

    def skip(grund: str) -> None:
        uebersprungen[grund] += 1

    gesehen: set[tuple[str, date | None, date, str]] = set()
    for fid, f in facts.items():
        dims = dict(f.get("dimensions", {}))
        konzept = str(dims.pop("concept", ""))
        dims.pop("entity", None)
        periode = dims.pop("period", None)
        unit = dims.pop("unit", None)
        dims.pop("language", None)
        if dims:
            skip("Dimension")
            continue
        if not konzept or periode is None:
            skip("ohne Konzept oder Periode")
            continue
        einheit = _einheit(unit)
        if einheit is None:
            skip(f"Einheit {unit}")
            continue
        try:
            wert = Decimal(str(f["value"]))
        except (InvalidOperation, KeyError, TypeError):
            skip("kein Zahlenwert")
            continue
        start, ende = _periode(str(periode))
        schluessel = (konzept, start, ende, einheit[2])
        if schluessel in gesehen:
            skip("doppelt")
            continue
        gesehen.add(schluessel)
        out.append(
            FactRow(
                issuer_id=iid,
                concept=konzept,
                value=wert,
                unit=einheit[0],
                unit_raw=einheit[2],
                currency=einheit[1],
                period_start=start,
                period_end=ende,
                fiscal_year=e.period_end.year,
                fiscal_period="FY",
                form="ESEF",
                accession=e.fxo_id,
                published_at=e.aufgenommen,
                source_type="xbrl",
                xbrl_context=f"{e.fxo_id}|{fid}|{konzept}|{start or ''}|{ende}|{einheit[2]}",
                raw_sha256=raw_sha256,
                retrieved_at=retrieved_at,
                doc_id=f"esef:{e.fxo_id}",
            )
        )
    doc = DocumentRow(
        doc_id=f"esef:{e.fxo_id}",
        issuer_id=iid,
        doc_type="ESEF",
        period_end=e.period_end,
        published_at=e.aufgenommen,
        retrieved_at=retrieved_at,
        source_url=source_url,
    )
    return out, doc, uebersprungen


class EsefClient:
    def __init__(
        self,
        cfg: dict[str, Any],
        user_agent: str,
        raw_dir: Path,
        *,
        fetcher: Callable[..., bytes] = fetch,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.cfg = cfg
        self.agent = user_agent
        self.raw_dir = raw_dir
        self.fetcher = fetcher
        self.sleep = sleep
        self.now = now

    def get(self, url: str) -> tuple[bytes, rawstore.RawRef]:
        content = self.fetcher(url, self.agent, timeout=float(self.cfg.get("timeout_s", 120)))
        self.sleep(float(self.cfg["pause_s"]))
        return content, rawstore.save(self.raw_dir, content, url, self.now())

    def einreichungen(self, lei: str) -> list[Einreichung]:
        raw, _ = self.get(str(self.cfg["filings_url"]).format(lei=lei))
        return parse_filings(raw, lei)

    def url(self, pfad: str) -> str:
        return f"{str(self.cfg['base_url']).rstrip('/')}{pfad}"
