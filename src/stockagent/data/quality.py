"""Datenqualitätsprüfungen (SPEC 3.2) für einen Emittenten.

Ablauf und Auswahl der Werte. Gerechnet wird ausschließlich in `core/dq.py` über den Rechenweg
(HR-06, HR-19). Ergebnis sind `dq_flags`: je Prüfung eine Zeile `ok` mit dem Umfang des
Geprüften (HR-08: die ausgeführten Prüfungen werden genannt) und je Befund eine Zeile `info`,
`warnung` oder `stopp`. Schwellen aus `config/quality.yaml`, Konzepte aus
`config/concept_map.yaml`.

| Prüfung | SPEC 3.2 |
|---|---|
| DQ-01 Bilanzgleichung | Nr. 1 |
| DQ-02 Summenstruktur des Originalberichts | Nr. 2 |
| DQ-03 Einheiten und Währung | Nr. 3 |
| DQ-04 Periodenlogik (Stichtag, Quartale gegen Neun-Monats-Wert) | Nr. 4 |
| DQ-05 Abgleich Company Facts gegen Originalbericht | Nr. 5 |
| DQ-06 Ausreißer gegen die eigene Historie | Nr. 6 |
| DQ-07 Restatements | Nr. 7 |
| DQ-08 Aktienanzahl: Split-Verdacht | Nr. 8 |
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Any

from stockagent.core import dq
from stockagent.core.calc import Eingabe, Ergebnis
from stockagent.data import concepts
from stockagent.data.sources.sec_xbrl import InstanceFact, Summation
from stockagent.data.store import DqFlag, StoredFact

ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "10-KT", "ESEF")


@dataclass(frozen=True)
class Originalbericht:
    """XBRL des letzten Jahresberichts, gelesen aus der Einreichung selbst (zweiter Weg)."""

    accession: str
    form: str
    stichtag: date  # Ende des Geschäftsjahres laut Einreichung (reportDate)
    instance: list[InstanceFact]
    calculation: list[Summation]
    url: str


@dataclass
class Kontext:
    issuer_id: str
    as_of: datetime
    facts: list[StoredFact]
    restatements: list[tuple[StoredFact, StoredFact]]
    fiscal_year_end: str | None
    skipped_units: Counter[str] = field(default_factory=Counter)
    skipped_forms: Counter[str] = field(default_factory=Counter)
    bericht: Originalbericht | None = None
    # Company Facts genau aus der Einreichung des Originalberichts (pit_query, einreichung)
    bericht_facts: list[StoredFact] = field(default_factory=list)
    # Aktienanzahl je Stichtag, wie damals gemeldet (pit_query, erste)
    aktien_erstmeldung: list[StoredFact] = field(default_factory=list)


def _zahl(v: Decimal) -> str:
    """Anzeige ohne überflüssige Nachkommastellen, deutsches Format."""
    text = f"{v.normalize():,f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _eingabe(f: StoredFact) -> Eingabe:
    return Eingabe(f.value, f.quelle, f.unit, f.period_end, f.currency, f.period_start)


def _instanz_eingabe(f: InstanceFact, url: str) -> Eingabe:
    unit = "shares" if f.unit_raw == "shares" else "monetary"
    currency = None if unit == "shares" else f.unit_raw
    start = f"{f.period_start}.." if f.period_start else ""
    return Eingabe(
        f.value,
        f"{f.concept}@{start}{f.period_end} ({url})",
        unit,
        f.period_end,
        currency,
        f.period_start,
    )


def _flag(
    ctx: Kontext,
    check: str,
    severity: str,
    detail: str,
    *,
    period_end: date | None = None,
    concept: str | None = None,
    erg: Ergebnis | None = None,
) -> DqFlag:
    return DqFlag(
        ctx.issuer_id,
        check,
        severity,
        period_end,
        concept,
        detail,
        erg.rechenweg_json() if erg else None,
    )


def _ergebnis_flags(
    ctx: Kontext, check: str, erg: Ergebnis, stopp: str, period_end: date, concept: str | None
) -> list[DqFlag]:
    if erg.unknown:
        return [
            _flag(
                ctx, check, stopp, erg.grund or "", period_end=period_end, concept=concept, erg=erg
            )
        ]
    return [
        _flag(ctx, check, "warnung", w, period_end=period_end, concept=concept, erg=erg)
        for w in erg.warnungen
    ]


def jahresstichtage(facts: Sequence[StoredFact], kern: Collection[str] | None = None) -> list[date]:
    """Stichtage der Geschäftsjahre: Enden von Jahreswerten (Dauer 52 bis 53 Wochen oder
    12 Monate) aus Jahresberichten, absteigend. Mit `kern` nur Enden, für die eines dieser
    Konzepte einen Jahreswert hat. Sonst zählt auch ein Planwert für das kommende Jahr im
    Anhang (Diageo: erwartete Pensionsbeiträge bis 30.06.2026 im Bericht für 2025)."""
    ends = {
        f.period_end
        for f in facts
        if f.form in ANNUAL_FORMS
        and dq.periode_passt(f.period_start, f.period_end, "FY")
        and f.period_start is not None
        and (kern is None or f.concept in kern)
    }
    return sorted(ends, reverse=True)


def _jahreswerte(
    facts: Sequence[StoredFact], cmap: dict[str, Any], metric: str, stichtage: list[date]
) -> dict[date, StoredFact]:
    """Jahreswerte einer Größe je Stichtag (Dauerwerte über ein Geschäftsjahr oder Stände)."""
    resolved = concepts.resolve(facts, cmap["us-gaap"][metric])
    out: dict[date, StoredFact] = {}
    for (start, end), f in resolved.items():
        if end not in stichtage:
            continue
        if start is None or dq.periode_passt(start, end, "FY"):
            out[end] = f
    return out


def _index(facts: Sequence[StoredFact]) -> dict[tuple[str, date | None, date], StoredFact]:
    return {(f.concept, f.period_start, f.period_end): f for f in facts}


# ------------------------------------------------------------------ DQ-01


def kern_konzepte(cmap: dict[str, Any]) -> set[str]:
    """Konzepte, deren Jahreswert ein Geschäftsjahr belegt: Umsatz, Bruttoergebnis, Ergebnis."""
    return {c for m in ("revenue", "gross_profit", "net_income") for c in cmap["us-gaap"][m]}


def _aktiva(cmap: dict[str, Any]) -> list[str]:
    """Konzepte der Bilanzsumme (US-GAAP und IFRS, Bauschritt 7)."""
    a = cmap["bilanz"]["aktiva"]
    return [a] if isinstance(a, str) else list(a)


def bilanzgleichung(
    ctx: Kontext, cmap: dict[str, Any], cfg: dict[str, Any], stichtage: list[date]
) -> list[DqFlag]:
    idx = _index(ctx.facts)
    tol = Decimal(cfg["bilanzgleichung"]["toleranz"])
    flags: list[DqFlag] = []
    geprueft = 0
    for stichtag in stichtage:
        aktiva = next(
            (a for c in _aktiva(cmap) if (a := idx.get((c, None, stichtag))) is not None), None
        )
        if aktiva is None:
            continue
        for variante in cmap["bilanz"]["passiva"]:
            teile = [idx.get((c, None, stichtag)) for c in variante]
            if all(t is not None for t in teile):
                break
        else:
            flags.append(
                _flag(
                    ctx,
                    "DQ-01",
                    "warnung",
                    "Passivseite nicht vollständig gemeldet",
                    period_end=stichtag,
                )
            )
            continue
        erg = dq.bilanzgleichung(
            ctx.issuer_id, _eingabe(aktiva), [_eingabe(t) for t in teile if t], tol
        )
        geprueft += 1
        flags += _ergebnis_flags(ctx, "DQ-01", erg, "stopp", stichtag, aktiva.concept)
    flags.insert(0, _flag(ctx, "DQ-01", "ok", f"{geprueft} Jahresstichtage geprüft"))
    return flags


# ------------------------------------------------------------------ DQ-02


def summenstruktur(ctx: Kontext, cmap: dict[str, Any], cfg: dict[str, Any]) -> list[DqFlag]:
    if ctx.bericht is None:
        return [_flag(ctx, "DQ-02", "info", "Kein Originalbericht geladen, nicht geprüft")]
    if not ctx.bericht.calculation:
        return [_flag(ctx, "DQ-02", "info", "Originalbericht ohne Berechnungsstruktur")]
    kern = {c for m in cmap["kernwerte"] for c in cmap["us-gaap"][m]}
    werte: dict[tuple[str, date | None, date], list[InstanceFact]] = defaultdict(list)
    for f in ctx.bericht.instance:
        werte[(f.concept, f.period_start, f.period_end)].append(f)
    perioden = {(f.period_start, f.period_end) for f in ctx.bericht.instance}
    tol_rel = Decimal(cfg["summenstruktur"]["toleranz_rel"])
    flags: list[DqFlag] = []
    geprueft = 0
    gesehen: set[tuple[str, tuple[tuple[str, Decimal], ...], date | None, date]] = set()
    for summe in ctx.bericht.calculation:
        for start, end in sorted(perioden, key=lambda p: (p[1], p[0] or p[1])):
            key = (summe.parent, summe.children, start, end)
            eltern = werte.get((summe.parent, start, end), [])
            kinder = [werte.get((c, start, end), []) for c, _ in summe.children]
            # Nur eindeutige Werte und nur, wenn alle Teile gemeldet sind
            if key in gesehen or len(eltern) != 1 or any(len(k) != 1 for k in kinder):
                continue
            gesehen.add(key)
            teile = [
                (_instanz_eingabe(k[0], ctx.bericht.url), g)
                for k, (_, g) in zip(kinder, summe.children, strict=True)
            ]
            tol_abs = dq.rundungstoleranz([eltern[0].decimals, *(k[0].decimals for k in kinder)])
            erg = dq.summenprobe(
                ctx.issuer_id,
                summe.parent.split(":")[-1],
                _instanz_eingabe(eltern[0], ctx.bericht.url),
                teile,
                tol_rel,
                tol_abs,
            )
            geprueft += 1
            stufe = "stopp" if summe.parent in kern else "warnung"
            flags += _ergebnis_flags(ctx, "DQ-02", erg, stufe, end, summe.parent)
    flags.insert(
        0,
        _flag(
            ctx,
            "DQ-02",
            "ok",
            f"{geprueft} Summen im {ctx.bericht.form} {ctx.bericht.accession} geprüft",
        ),
    )
    return flags


# ------------------------------------------------------------------ DQ-03


def einheiten(ctx: Kontext, cmap: dict[str, Any]) -> list[DqFlag]:
    waehrungen = Counter(f.currency for f in ctx.facts if f.unit == "monetary")
    flags = [
        _flag(
            ctx,
            "DQ-03",
            "ok",
            "Währungen: "
            + ", ".join(f"{w} ({n})" for w, n in waehrungen.most_common())
            + ". Werte der SEC sind unskaliert (Faktor 1).",
        )
    ]
    # Fremdwährungen im Anhang (Anleihen in EUR) sind normal. Kernwerte müssen in der
    # Währung der Bilanz stehen.
    bilanz = Counter(f.currency for f in ctx.facts if f.concept in _aktiva(cmap))
    if bilanz:
        haupt = bilanz.most_common(1)[0][0]
        kern = {c for m in cmap["kernwerte"] for c in cmap["us-gaap"][m]}
        fremd = sorted(
            {
                f"{f.concept} {f.currency}"
                for f in ctx.facts
                if f.concept in kern and f.unit == "monetary" and f.currency != haupt
            }
        )
        if fremd:
            flags.append(
                _flag(
                    ctx,
                    "DQ-03",
                    "warnung",
                    f"Kernwerte nicht in der Bilanzwährung {haupt}: {', '.join(fremd[:5])}",
                )
            )
    if ctx.skipped_units:
        flags.append(
            _flag(
                ctx,
                "DQ-03",
                "info",
                "Nicht übernommen (Einheit ohne Geld, Aktie oder Verhältnis): "
                + ", ".join(f"{u} ({n})" for u, n in ctx.skipped_units.most_common()),
            )
        )
    if ctx.skipped_forms:
        flags.append(
            _flag(
                ctx,
                "DQ-03",
                "info",
                "Nicht übernommen (kein Abschlussbericht): "
                + ", ".join(f"{u} ({n})" for u, n in ctx.skipped_forms.most_common()),
            )
        )
    return flags


# ------------------------------------------------------------------ DQ-04


def perioden(
    ctx: Kontext, cmap: dict[str, Any], cfg: dict[str, Any], stichtage: list[date]
) -> list[DqFlag]:
    flags: list[DqFlag] = []
    if ctx.fiscal_year_end:
        abweichend = [s for s in stichtage if not dq.stichtag_passt(s, ctx.fiscal_year_end)]
        for s in abweichend:
            flags.append(
                _flag(
                    ctx,
                    "DQ-04",
                    "warnung",
                    f"Jahresstichtag passt nicht zum Geschäftsjahresende {ctx.fiscal_year_end} "
                    "laut SEC (Umstellung des Geschäftsjahres?)",
                    period_end=s,
                )
            )
    # Drei Quartale gegen den Neun-Monats-Wert desselben Geschäftsjahres (ohne Doppelzählung)
    umsatz = concepts.resolve(ctx.facts, cmap["us-gaap"]["revenue"])
    quartale = sorted(
        (f for (s, e), f in umsatz.items() if dq.periode_passt(s, e, "Q")),
        key=lambda f: f.period_end,
    )
    tol = Decimal(cfg["summenstruktur"]["toleranz_rel"])
    geprueft = 0
    neun = [f for (s, e), f in umsatz.items() if dq.ist_neunmonatig(s, e)]
    for ytd in sorted(neun, key=lambda f: f.period_end, reverse=True)[:3]:
        drin = [
            q
            for q in quartale
            if q.period_start is not None
            and ytd.period_start is not None
            and q.period_start >= ytd.period_start
            and q.period_end <= ytd.period_end
        ]
        if len(drin) != 3:
            continue
        erg = dq.summenprobe(
            ctx.issuer_id,
            "quartale_umsatz",
            _eingabe(ytd),
            [(_eingabe(q), Decimal(1)) for q in drin],
            tol,
            Decimal(0),
            gleiche_periode=False,
        )
        geprueft += 1
        flags += _ergebnis_flags(ctx, "DQ-04", erg, "warnung", ytd.period_end, ytd.concept)
    flags.insert(
        0,
        _flag(
            ctx,
            "DQ-04",
            "ok",
            f"{len(stichtage)} Jahresstichtage gegen Geschäftsjahresende "
            f"{ctx.fiscal_year_end or 'unbekannt'}, {geprueft} Neun-Monats-Umsätze gegen "
            "drei Quartale geprüft",
        ),
    )
    return flags


# ------------------------------------------------------------------ DQ-05


def zweiter_weg(ctx: Kontext, cmap: dict[str, Any], cfg: dict[str, Any]) -> list[DqFlag]:
    if ctx.bericht is None:
        return [_flag(ctx, "DQ-05", "warnung", "Kein Originalbericht geladen, zweiter Weg fehlt")]
    warn = Decimal(cfg["abgleich_zweiter_weg"]["warnung"])
    stopp = Decimal(cfg["abgleich_zweiter_weg"]["stopp"])
    # Company Facts aus genau dieser Einreichung, damit derselbe Berichtsstand verglichen wird
    cf = _index(ctx.bericht_facts)
    inst: dict[tuple[str, date | None, date], list[InstanceFact]] = defaultdict(list)
    for f in ctx.bericht.instance:
        inst[(f.concept, f.period_start, f.period_end)].append(f)
    stichtag = ctx.bericht.stichtag
    flags: list[DqFlag] = []
    verglichen = []
    fehlt = []
    for metric in cmap["kernwerte"]:
        treffer = None
        for concept in cmap["us-gaap"][metric]:
            kandidaten = [
                (k, v[0])
                for k, v in inst.items()
                if k[0] == concept
                and k[2] == stichtag
                and len(v) == 1
                and (k[1] is None or dq.periode_passt(k[1], k[2], "FY"))
                and k in cf
            ]
            if len(kandidaten) == 1:
                treffer = kandidaten[0]
                break
        if treffer is None:
            fehlt.append(metric)
            continue
        key, instanz = treffer
        erg = dq.abgleich(
            ctx.issuer_id,
            metric,
            _eingabe(cf[key]),
            _instanz_eingabe(instanz, ctx.bericht.url),
            warn,
            stopp,
        )
        verglichen.append(metric)
        flags += _ergebnis_flags(ctx, "DQ-05", erg, "stopp", key[2], key[0])
    detail = (
        f"{len(verglichen)} Kernwerte gegen {ctx.bericht.form} {ctx.bericht.accession} "
        f"abgeglichen: {', '.join(verglichen) or 'keine'}"
    )
    if fehlt:
        detail += f". Nicht in beiden Quellen: {', '.join(fehlt)}"
    flags.insert(0, _flag(ctx, "DQ-05", "ok", detail, period_end=stichtag))
    return flags


# ------------------------------------------------------------------ DQ-06


def ausreisser(
    ctx: Kontext, cmap: dict[str, Any], cfg: dict[str, Any], stichtage: list[date]
) -> list[DqFlag]:
    schwelle = Decimal(cfg["ausreisser"]["schwelle"])
    mindest = int(cfg["ausreisser"]["mindest_historie"])
    flags: list[DqFlag] = []
    geprueft = []
    for metric in cmap["ausreisser"]:
        reihe = _jahreswerte(ctx.facts, cmap, metric, stichtage)
        werte = [reihe[s] for s in sorted(reihe)]
        if len(werte) < mindest + 1:
            continue
        einheiten_ = {(w.unit, w.currency) for w in werte}
        if len(einheiten_) != 1:
            continue
        *historie, letzter = werte[-11:]
        erg = dq.ausreisser(
            ctx.issuer_id,
            metric,
            [_eingabe(h) for h in historie],
            _eingabe(letzter),
            schwelle,
            Decimal(str(cfg["ausreisser"]["streuung_untergrenze"])),
        )
        if erg is None:
            continue
        geprueft.append(metric)
        for w in erg.warnungen:
            flags.append(
                _flag(
                    ctx,
                    "DQ-06",
                    "warnung",
                    f"{metric}: {w}. Ein Ausreißer ist kein Fehler, braucht aber eine "
                    "Begründung aus dem Bericht (etwa eine Übernahme)",
                    period_end=letzter.period_end,
                    concept=letzter.concept,
                    erg=erg,
                )
            )
        if erg.unknown:
            flags.append(
                _flag(
                    ctx,
                    "DQ-06",
                    "info",
                    f"{metric}: {erg.grund}",
                    period_end=letzter.period_end,
                    erg=erg,
                )
            )
    flags.insert(
        0, _flag(ctx, "DQ-06", "ok", f"Letzter Jahreswert gegen Historie: {', '.join(geprueft)}")
    )
    return flags


# ------------------------------------------------------------------ DQ-07


def restatements(ctx: Kontext, cmap: dict[str, Any], stichtage: list[date]) -> list[DqFlag]:
    kern = {c for m in cmap["kernwerte"] for c in cmap["us-gaap"][m]}
    juengste = set(stichtage[:3])
    flags = [_flag(ctx, "DQ-07", "ok", f"{len(ctx.restatements)} geänderte Fassungen gespeichert")]
    for alt, neu in ctx.restatements:
        if alt.concept in kern and alt.period_end in juengste:
            flags.append(
                _flag(
                    ctx,
                    "DQ-07",
                    "warnung",
                    f"Geändert von {_zahl(alt.value)} ({alt.form} {alt.accession}) auf "
                    f"{_zahl(neu.value)} "
                    f"({neu.form} {neu.accession}). Beide Fassungen bleiben gespeichert.",
                    period_end=alt.period_end,
                    concept=alt.concept,
                )
            )
    return flags


# ------------------------------------------------------------------ DQ-08


def splits(ctx: Kontext, cmap: dict[str, Any], cfg: dict[str, Any]) -> list[DqFlag]:
    tol = Decimal(cfg["split"]["toleranz"])
    # Nur das Deckblatt-Konzept, und je Stichtag die damalige Meldung: Spätere Berichte rechnen
    # alte Aktienzahlen auf den Split um und würden den Sprung verdecken.
    reihe = sorted(
        (f for f in ctx.aktien_erstmeldung if f.period_start is None and f.unit == "shares"),
        key=lambda f: f.period_end,
    )
    flags = [_flag(ctx, "DQ-08", "ok", f"{len(reihe)} Stände der Aktienanzahl geprüft")]
    for vorher, nachher in pairwise(reihe):
        v = dq.split_verdacht(ctx.issuer_id, _eingabe(vorher), _eingabe(nachher), tol)
        if v.faktor is not None:
            flags.append(
                _flag(
                    ctx,
                    "DQ-08",
                    "info",
                    f"Aktienanzahl springt im Verhältnis {v.verhaeltnis} zwischen "
                    f"{vorher.period_end} und {nachher.period_end}: Split oder "
                    "Zusammenlegung. Bereinigung in Bauschritt 3.",
                    period_end=nachher.period_end,
                    concept=nachher.concept,
                    erg=v.ergebnis,
                )
            )
    return flags


def run(ctx: Kontext, cmap: dict[str, Any], cfg: dict[str, Any]) -> list[DqFlag]:
    """Alle Prüfungen aus SPEC 3.2 für einen Emittenten."""
    stichtage = jahresstichtage(ctx.facts, kern_konzepte(cmap))[:10]
    return [
        *bilanzgleichung(ctx, cmap, cfg, stichtage),
        *summenstruktur(ctx, cmap, cfg),
        *einheiten(ctx, cmap),
        *perioden(ctx, cmap, cfg, stichtage),
        *zweiter_weg(ctx, cmap, cfg),
        *ausreisser(ctx, cmap, cfg, stichtage),
        *restatements(ctx, cmap, stichtage),
        *splits(ctx, cmap, cfg),
    ]
