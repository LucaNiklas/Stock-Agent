"""Prüfung von Wertpapierkennungen und Stammdaten (reine Funktionen, SPEC 7.1)."""

from __future__ import annotations

import re
import unicodedata

_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

# Rechtsformen und Wertpapierzusätze, die in Börsennamen und LEI-Namen vorkommen,
# aber nichts über die Identität des Unternehmens sagen.
_NOISE = {
    "AG",
    "SE",
    "KGAA",
    "GMBH",
    "INC",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "LTD",
    "LIMITED",
    "PLC",
    "SA",
    "SAS",
    "SPA",
    "NV",
    "BV",
    "AB",
    "ASA",
    "OYJ",
    "AS",
    "HOLDING",
    "HOLDINGS",
    "HLDGS",
    "GROUP",
    "GRP",
    "THE",
    "AND",
    "NAMENS",
    "INHABER",
    "ADR",
    "ADS",
    "GDR",
    "SP",
    "SPON",
    "UNSP",
    "REGS",
    "CDR",
    "CDI",
    "CLA",
    "CLB",
    "CL",
    "DL",
    "EO",
    "LS",
    "SF",
    "ON",
    "NA",
    "VZ",
    "STK",
    "SHS",
    "UNITS",
    "AKTIENGESELLSCHAFT",
    "SOCIETE",
    "ANONYME",
}


def isin_is_valid(isin: str) -> bool:
    """ISIN nach ISO 6166: Format und Prüfziffer (Luhn über die in Ziffern umgesetzten Zeichen)."""
    if not _ISIN.match(isin):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10 == int(isin[-1])


def change_exceeds(previous: int, current: int, max_pct: float) -> bool:
    """True, wenn sich eine Anzahl gegenüber dem Vorstand um mehr als max_pct Prozent ändert."""
    if previous == 0:
        return False
    return abs(current - previous) * 100 > max_pct * previous


_TRANSLIT = str.maketrans(
    {
        "Ø": "OE",
        "ø": "oe",
        "Æ": "AE",
        "æ": "ae",
        "Œ": "OE",
        "œ": "oe",
        "ß": "ss",
        "Ł": "L",
        "ł": "l",
        "Đ": "D",
        "đ": "d",
    }
)


_UMLAUT = str.maketrans({"Ä": "AE", "ä": "ae", "Ö": "OE", "ö": "oe", "Ü": "UE", "ü": "ue"})


def name_tokens(name: str) -> list[str]:
    """Bedeutungstragende Wörter eines Firmennamens in Großbuchstaben ohne Akzente.

    Reine Zahlen fallen weg, Wörter mit Buchstaben und Ziffern (8X8, 3I) bleiben.
    """
    latin = unicodedata.normalize("NFKD", name.translate(_TRANSLIT))
    words = re.split(r"[^A-Z0-9]+", latin.encode("ascii", "ignore").decode().upper())
    return [w for w in words if len(w) >= 2 and w not in _NOISE and not w.isdigit()]


def names_plausibly_match(listing_name: str, legal_name: str) -> bool:
    """Passt der (oft abgekürzte) Börsenname zum rechtlichen Namen aus der LEI?

    Eines der ersten drei Wörter des Börsennamens muss einem Wort im rechtlichen Namen gleichen,
    Präfix davon sein oder umgekehrt (mindestens drei Zeichen), oder es entspricht den
    Anfangsbuchstaben des rechtlichen Namens (etwa IBM). Im Zweifel False: Dann wird die LEI
    nicht für Stammdaten genutzt.
    """
    left = name_tokens(listing_name)[:3]
    # Umlaute zusätzlich in deutscher Schreibweise (Ströer -> STROEER)
    right = name_tokens(legal_name) + name_tokens(legal_name.translate(_UMLAUT))
    if not left or not right:
        return False
    initials = "".join(w[0] for w in name_tokens(legal_name))
    for a in left:
        if len(a) >= 3 and a == initials:
            return True
        for b in right:
            if a == b or (min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a))):
                return True
    return False


_RECEIPT = re.compile(
    r"(ADRS?|ADS|GDRS?|CDRS?|CDIS?|SDRS?|ARD)(\b|/|\d|\)|REGS|RC)|\bAD/\d|\bDRC?\b|SP\.?\s?ADR"
    r"|SPADR|UADR|ADRO\b|\bUNSP\b|\bNY\b|\bNY\s*\d|\bNYRS?\b|DEP\.?\s?REC|DR\s?\d/"
)


def is_depositary_receipt(name: str) -> bool:
    """Hinterlegungsschein (ADR, GDR, CDR, CDI, SDR, NY-Registered Share) laut Börsenname.

    Heuristik über die Namenskürzel der Deutschen Börse. Bei solchen Papieren sagt das ISIN-Land
    nichts über das Unternehmen (ADRs haben immer eine US-ISIN).
    """
    return bool(_RECEIPT.search(name.upper()))


def choose_country(
    isin_country: str,
    legal_country: str | None,
    hq_country: str | None,
    lei_plausible: bool,
    receipt: bool,
) -> tuple[str, str]:
    """Angezeigtes Land (Hauptsitz) und seine Herkunft: gleif, isin oder konflikt.

    - gleif: LEI passt zum Namen, Land ist der Hauptsitz laut GLEIF.
    - isin: keine verwertbare LEI, nur das Länderkürzel der ISIN (bei ADRs immer US, unsicher).
    - konflikt: normale Aktie, deren ISIN-Land nicht zum rechtlichen Sitz der LEI passt. Typisch
      für Zuordnungen auf Vorgänger- oder Tochtergesellschaften (ADR 0001). Gezeigt wird das
      ISIN-Land, weil die nationale Stelle des Gründungslands die ISIN vergibt.
    """
    if not (hq_country and lei_plausible):
        return isin_country, "isin"
    if not receipt and legal_country and legal_country != isin_country:
        return isin_country, "konflikt"
    return hq_country, "gleif"
