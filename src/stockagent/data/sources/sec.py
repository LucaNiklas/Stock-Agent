"""Anbindung SEC EDGAR (SPEC 7.2, Quellenkarte `config/source_map.yaml`).

Drei feste Adressen der SEC, abgerufen ohne Sprachmodell (Abteilung Recherche, SPEC 8.1):

- `company_tickers_exchange.json`: CIK, Name, Ticker, Börse aller Melder mit Ticker.
- Submissions je CIK: Name, SIC-Code, Geschäftsadresse, Gründungsstaat, Geschäftsjahresende,
  Liste der Einreichungen mit Annahmezeitpunkt.
- Company Facts je CIK: alle XBRL-Werte mit Konzept, Periode, Einheit, Einreichung.

Jede Antwort landet unverändert in `data/raw/` (SPEC 7.6). Höchstens `max_requests_per_s`
Anfragen je Sekunde, User-Agent mit Name und E-Mail aus `SEC_USER_AGENT`. Form 4 (Insider)
kommt in Bauschritt 9 dazu.

`edgartools` wird nicht genutzt (ADR 0002): Für drei JSON-Adressen und eine XBRL-Datei wäre die
Bibliothek mit ihren Abhängigkeiten zu schwer, und ihr eigener Zwischenspeicher liefe an
`data/raw/` vorbei.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from datetime import time as dtime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stockagent.data import rawstore
from stockagent.data.http import fetch
from stockagent.data.store import DocumentRow, FactRow


class SecFormatError(ValueError):
    """Antwort der SEC hat nicht das erwartete Format."""


class MissingUserAgent(RuntimeError):
    pass


# Bundesstaaten und "X1" (United States) aus der Codeliste der SEC
# (https://www.sec.gov/submit-filings/filer-support-resources/edgar-state-country-codes,
# abgerufen am 13.10.2026). Andere Codes sind Länder oder kanadische Provinzen.
US_REGIONS = frozenset(
    [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "X1",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    ]
)

# Präfixe der Taxonomien, deren Werte übernommen werden. Firmeneigene Erweiterungen fehlen in
# den Company Facts ohnehin.
TAXONOMIES = ("us-gaap", "ifrs-full", "dei", "srt")

_NEW_YORK = ZoneInfo("America/New_York")


def user_agent(root: Path, env_name: str = "SEC_USER_AGENT") -> str:
    """User-Agent aus der Umgebung, sonst aus `.env`. Muss eine E-Mail-Adresse enthalten."""
    value = os.environ.get(env_name, "").strip()
    env_file = root / ".env"
    if not value and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, rest = line.partition("=")
            if key.strip() == env_name:
                value = rest.strip().strip('"').strip("'")
    if "@" not in value:
        raise MissingUserAgent(
            f"{env_name} fehlt oder enthält keine E-Mail. Die SEC verlangt Name und E-Mail "
            f'im User-Agent. In .env eintragen: {env_name}="Vorname Nachname mail@beispiel.de"'
        )
    return value


def cik10(cik: int | str) -> str:
    text = str(cik).strip()
    if not text.isdigit() or len(text) > 10:
        raise SecFormatError(f"Ungültige CIK: {cik!r}")
    return text.zfill(10)


def issuer_id(cik: str) -> str:
    return f"sec:{cik10(cik)}"


# ------------------------------------------------------------------ Tickerliste


@dataclass(frozen=True)
class TickerEntry:
    cik: str
    name: str
    ticker: str
    exchange: str | None


def parse_tickers(raw: bytes) -> list[TickerEntry]:
    data = json.loads(raw)
    if data.get("fields") != ["cik", "name", "ticker", "exchange"]:
        raise SecFormatError(f"Tickerliste mit unbekannten Feldern: {data.get('fields')}")
    return [TickerEntry(cik10(c), n, t.upper(), e) for c, n, t, e in data["data"] if t]


# ------------------------------------------------------------------ Submissions


@dataclass(frozen=True)
class Filing:
    accession: str
    form: str
    filing_date: date
    report_date: date | None
    accepted_at: datetime | None
    primary_document: str


@dataclass(frozen=True)
class Submissions:
    cik: str
    name: str
    sic: str | None
    sic_description: str | None
    fiscal_year_end: str | None
    state_of_incorporation: str | None
    entity_type: str | None
    category: str | None
    business_address: str | None
    business_region: str | None
    country: str | None
    tickers: tuple[str, ...]
    former_names: tuple[str, ...]
    filings: dict[str, Filing] = field(default_factory=dict)


def _date(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None


def _accepted(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _address(addr: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    """Adresse als Text, Regionscode der SEC und ISO-Land (nur US sicher ableitbar)."""
    if not addr:
        return None, None, None
    region = addr.get("stateOrCountry")
    name = addr.get("stateOrCountryDescription") or addr.get("country")
    parts = [addr.get("street1"), addr.get("street2"), addr.get("city"), addr.get("zipCode"), name]
    text = ", ".join(p for p in parts if p) or None
    country = "US" if region in US_REGIONS else None
    return text, region or addr.get("countryCode"), country


def parse_submissions(raw: bytes) -> Submissions:
    d = json.loads(raw)
    try:
        recent = d["filings"]["recent"]
        cols = ("accessionNumber", "form", "filingDate", "reportDate", "acceptanceDateTime")
        n = len(recent["accessionNumber"])
        if any(len(recent[c]) != n for c in cols):
            raise SecFormatError("Einreichungsliste mit ungleich langen Spalten")
        filings = {}
        for i in range(n):
            acc = recent["accessionNumber"][i]
            filings[acc] = Filing(
                accession=acc,
                form=recent["form"][i],
                filing_date=date.fromisoformat(recent["filingDate"][i]),
                report_date=_date(recent["reportDate"][i]),
                accepted_at=_accepted(recent["acceptanceDateTime"][i]),
                primary_document=recent.get("primaryDocument", [""] * n)[i],
            )
        address, region, country = _address(d.get("addresses", {}).get("business"))
        return Submissions(
            cik=cik10(d["cik"]),
            name=d["name"],
            sic=d.get("sic") or None,
            sic_description=d.get("sicDescription") or None,
            fiscal_year_end=d.get("fiscalYearEnd") or None,
            state_of_incorporation=d.get("stateOfIncorporation") or None,
            entity_type=d.get("entityType") or None,
            category=d.get("category") or None,
            business_address=address,
            business_region=region,
            country=country,
            tickers=tuple(d.get("tickers") or ()),
            former_names=tuple(f["name"] for f in d.get("formerNames") or ()),
            filings=filings,
        )
    except (KeyError, TypeError) as exc:
        raise SecFormatError(f"Submissions ohne erwartetes Feld: {exc}") from exc


# ------------------------------------------------------------------ Company Facts


def published_at(filed: date, accepted: datetime | None) -> datetime:
    """Veröffentlichung: Annahmezeitpunkt der SEC, sonst Ende des Einreichungstags in New York.

    Das Ende des Tages ist die vorsichtige Wahl (HR-07): Ein Wert gilt nie früher als bekannt,
    als er es war.
    """
    if accepted is not None:
        return accepted
    return datetime.combine(filed, dtime(23, 59, 59), tzinfo=_NEW_YORK).astimezone(UTC)


def classify_unit(unit_raw: str) -> tuple[str, str | None] | None:
    """Einheit laut SEC auf (Einheit, Währung) abbilden. None für Einheiten außerhalb von HR-12."""
    if unit_raw == "shares":
        return "shares", None
    if unit_raw == "pure":
        return "pure", None
    if len(unit_raw) == 3 and unit_raw.isalpha() and unit_raw.isupper():
        return "monetary", unit_raw
    num, sep, den = unit_raw.partition("/")
    if sep and den == "shares" and len(num) == 3 and num.isalpha() and num.isupper():
        return "per_share", num
    return None


@dataclass
class ParsedFacts:
    facts: list[FactRow]
    documents: list[DocumentRow]
    skipped_units: Counter[str]
    standard_counts: Counter[str]
    skipped_forms: Counter[str]


def parse_companyfacts(
    raw: bytes,
    *,
    raw_sha256: str,
    retrieved_at: datetime,
    filings: dict[str, Filing],
    source_url: str,
    report_forms: frozenset[str] | None = None,
) -> ParsedFacts:
    """Werte aus Company Facts. Mit `report_forms` nur Werte aus diesen Formularen."""
    d = json.loads(raw)
    try:
        cik = cik10(d["cik"])
        taxonomies: dict[str, dict[str, Any]] = d["facts"]
    except (KeyError, TypeError) as exc:
        raise SecFormatError(f"Company Facts ohne erwartetes Feld: {exc}") from exc
    iid = issuer_id(cik)
    facts: list[FactRow] = []
    docs: dict[str, DocumentRow] = {}
    skipped: Counter[str] = Counter()
    standards: Counter[str] = Counter()
    skipped_forms: Counter[str] = Counter()
    for tax in TAXONOMIES:
        for concept, body in taxonomies.get(tax, {}).items():
            name = f"{tax}:{concept}"
            for unit_raw, rows in body.get("units", {}).items():
                unit = classify_unit(unit_raw)
                if unit is None:
                    skipped[unit_raw] += len(rows)
                    continue
                for r in rows:
                    if report_forms is not None and r.get("form") not in report_forms:
                        skipped_forms[str(r.get("form"))] += 1
                        continue
                    acc = r["accn"]
                    filed = date.fromisoformat(r["filed"])
                    filing = filings.get(acc)
                    pub = published_at(filed, filing.accepted_at if filing else None)
                    start = _date(r.get("start"))
                    end = date.fromisoformat(r["end"])
                    facts.append(
                        FactRow(
                            issuer_id=iid,
                            concept=name,
                            value=Decimal(str(r["val"])),
                            unit=unit[0],
                            unit_raw=unit_raw,
                            currency=unit[1],
                            period_start=start,
                            period_end=end,
                            fiscal_year=r.get("fy"),
                            fiscal_period=r.get("fp"),
                            form=r.get("form"),
                            accession=acc,
                            published_at=pub,
                            source_type="xbrl",
                            xbrl_context=f"{acc}|{name}|{start or ''}|{end}|{unit_raw}",
                            raw_sha256=raw_sha256,
                            retrieved_at=retrieved_at,
                            doc_id=f"sec:{acc}",
                        )
                    )
                    if tax in ("us-gaap", "ifrs-full"):
                        standards[tax] += 1
                    if acc not in docs:
                        docs[acc] = DocumentRow(
                            doc_id=f"sec:{acc}",
                            issuer_id=iid,
                            doc_type=r.get("form") or "unbekannt",
                            period_end=filing.report_date if filing else None,
                            published_at=pub,
                            retrieved_at=retrieved_at,
                            source_url=source_url,
                        )
    return ParsedFacts(facts, list(docs.values()), skipped, standards, skipped_forms)


def accounting_standard(standards: Counter[str]) -> str | None:
    if not standards:
        return None
    return "IFRS" if standards["ifrs-full"] > standards["us-gaap"] else "US-GAAP"


# ------------------------------------------------------------------ Abruf


Fetcher = Callable[..., bytes]


@dataclass(frozen=True)
class FrameRow:
    """Ein Wert aus der Frames-Schnittstelle der SEC: dieselbe Größe für alle Melder in einem
    Kalenderzeitraum (etwa CY2025). Gebraucht für die Auswahl der Vergleichsgruppe nach Umsatz."""

    cik: str
    name: str
    wert: Decimal
    start: date | None
    ende: date
    accession: str


def parse_frame(raw: bytes) -> list[FrameRow]:
    try:
        body = json.loads(raw)
        data = body["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SecFormatError("Frames-Antwort der SEC ohne Daten") from exc
    return [
        FrameRow(
            cik10(d["cik"]),
            str(d.get("entityName") or ""),
            Decimal(str(d["val"])),
            _date(d.get("start")),
            date.fromisoformat(d["end"]),
            str(d.get("accn") or ""),
        )
        for d in data
    ]


class RateLimiter:
    def __init__(
        self,
        per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 1.0 / per_second
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0

    def wait(self) -> None:
        now = self._clock()
        if now < self._next:
            self._sleep(self._next - now)
            now = self._next
        self._next = now + self._interval


class SecClient:
    """Abruf mit Ratenbegrenzung. Jede Antwort wird roh abgelegt (SPEC 7.6)."""

    def __init__(
        self,
        cfg: dict[str, Any],
        agent: str,
        raw_dir: Path,
        *,
        fetcher: Fetcher = fetch,
        limiter: RateLimiter | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.cfg = cfg
        self.agent = agent
        self.raw_dir = raw_dir
        self.fetcher = fetcher
        self.limiter = limiter or RateLimiter(float(cfg["max_requests_per_s"]))
        self.now = now

    def get(self, url: str) -> tuple[bytes, rawstore.RawRef]:
        self.limiter.wait()
        content = self.fetcher(url, self.agent)
        return content, rawstore.save(self.raw_dir, content, url, self.now())

    def tickers(self) -> tuple[list[TickerEntry], rawstore.RawRef]:
        content, ref = self.get(self.cfg["tickers_url"])
        return parse_tickers(content), ref

    def submissions(self, cik: str) -> tuple[Submissions, rawstore.RawRef]:
        content, ref = self.get(self.cfg["submissions_url"].format(cik=cik10(cik)))
        return parse_submissions(content), ref

    def companyfacts(self, cik: str, filings: dict[str, Filing]) -> ParsedFacts:
        url = self.cfg["companyfacts_url"].format(cik=cik10(cik))
        content, ref = self.get(url)
        return parse_companyfacts(
            content,
            raw_sha256=ref.sha256,
            retrieved_at=ref.retrieved_at,
            filings=filings,
            source_url=url,
            report_forms=frozenset(self.cfg["report_forms"]),
        )

    def frame(self, concept: str, zeitraum: str) -> tuple[list[FrameRow], rawstore.RawRef]:
        """Werte eines Konzepts für alle Melder, etwa ("us-gaap:Revenues", "CY2025")."""
        taxonomie, name = concept.split(":")
        url = self.cfg["frames_url"].format(taxonomie=taxonomie, konzept=name, zeitraum=zeitraum)
        content, ref = self.get(url)
        return parse_frame(content), ref

    def filing_url(self, cik: str, accession: str, name: str | None = None) -> str:
        values = {"cik_int": int(cik10(cik)), "accession_nodash": accession.replace("-", "")}
        if name is None:
            return str(self.cfg["filing_index_url"].format(**values))
        return str(self.cfg["filing_file_url"].format(name=name, **values))

    def filing_files(self, cik: str, accession: str) -> list[str]:
        content, _ = self.get(self.filing_url(cik, accession))
        try:
            return [item["name"] for item in json.loads(content)["directory"]["item"]]
        except (KeyError, TypeError) as exc:
            raise SecFormatError(f"Verzeichnis der Einreichung unlesbar: {exc}") from exc

    def filing_file(self, cik: str, accession: str, name: str) -> tuple[bytes, rawstore.RawRef]:
        return self.get(self.filing_url(cik, accession, name))
