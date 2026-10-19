"""DCF in drei Szenarien mit Sensitivität (SPEC 3.6, ADR 0006).

Annahmen je Szenario aus vier Größen, jede in drei Stufen aus der eigenen Historie der letzten
bis zu 10 Geschäftsjahre (`niedrig` = 25. Perzentil, `mittel` = Median, `hoch` = 75. Perzentil):

- Umsatzwachstum: rollierende 3-Jahres-Wachstumsraten (CAGR), damit einzelne Boom- oder
  Krisenjahre die Stufen nicht bestimmen
- EBIT-Marge
- Netto-Investitionsquote: (Capex - Abschreibungen) / Umsatz
- Working-Capital-Quote: operatives Nettoumlaufvermögen / Umsatz, operatives Nettoumlaufvermögen
  = Umlaufvermögen - Kasse - kurzfristige Wertpapiere - (kurzfristige Verbindlichkeiten -
  kurzfristige Finanzschulden)

Welche Stufe ein Szenario nutzt, steht in `config/kapitalkosten.yaml` (`szenarien`). Ab Schritt 6
wählt der Bewertungsagent A5 die Stufen mit Begründung, er schreibt nie Zahlen (HR-01). Die
Branche kommt mit der Vergleichsgruppe aus Schritt 5 dazu. Die Szenarien sind Information und
gehen nicht in Note oder Kategorie ein (HR-13), außer als Verschärfung (Kurs über Bull).

Rechnung je Jahr t = 1 bis 10: Wachstum g_t = g bis zum Jahr vor `ausblenden_ab_jahr`, danach
linear bis zum Endwachstum im letzten Jahr. U_t = U_(t-1) * (1 + g_t).
FCFF_t = U_t * (Marge * (1 - Steuersatz) - Investitionsquote) - (U_t - U_(t-1)) * WC-Quote.
Endwert = FCFF_(n+1) / (WACC - g_end) mit U_(n+1) = U_n * (1 + g_end). Brücke vom
Unternehmenswert zum Eigenkapital mit allen Posten aus `enterprise_value` (SPEC 3.6 Nr. 6),
Wert je Aktie mit der verwässerten Aktienzahl. Ist die operative Marge nach Steuern und
Investitionen nicht positiv, ist das Szenario nicht aussagekräftig (Scorecard „Wachstum ohne
Gewinn“ ab Schritt 8).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from stockagent.core import dq
from stockagent.core.calc import EingabeFehlt, NichtDefiniert, Rechenweg, Schritt, Wert, _wert
from stockagent.core.kapitalkosten import Kapitalkosten, kapitalkosten
from stockagent.core.kennzahlen import _opt, ebit_wert, nettoverschuldung
from stockagent.core.marktkennzahlen import _aktien, kurs
from stockagent.core.registry import metric
from stockagent.core.reihen import Reihen

STUFEN = {"niedrig": Decimal("0.25"), "mittel": Decimal("0.5"), "hoch": Decimal("0.75")}
GROESSEN = ("wachstum", "marge", "investition", "working_capital")


def _historie(r: Rechenweg, d: Reihen, t: date) -> dict[str, list[Decimal]]:
    """Werte der vier Größen für bis zu 10 Stichtage bis `t` (fehlende Jahre fallen weg). Das
    3-Jahres-Wachstum zählt nur bei genau drei Jahren Abstand, also nie TTM gegen GJ."""
    jahre = d.stichtage[d.stichtage.index(t) :][:10]
    out: dict[str, list[Decimal]] = {g: [] for g in GROESSEN}
    for i, j in enumerate(jahre):
        tag = f"{j:%Y_%m_%d}"
        if not d.hat("revenue", j) or d.hole("revenue", j).wert <= 0:
            continue
        umsatz = d.hole("revenue", j)
        if i + 3 < len(jahre) and d.hat("revenue", jahre[i + 3]):
            anfang = d.hole("revenue", jahre[i + 3])
            if 1090 <= dq.dauer_tage(jahre[i + 3], j) <= 1110 and anfang.wert > 0:
                faktor = r.schritt(f"faktor_3j_{tag}", "u / u_3j", u=umsatz, u_3j=anfang)
                je_jahr = r.potenz(f"faktor_je_jahr_{tag}", faktor, 1, 3)
                out["wachstum"].append(r.schritt(f"wachstum_3j_{tag}", "f - 1", f=je_jahr))
        with contextlib.suppress(EingabeFehlt):
            out["marge"].append(
                r.schritt(f"marge_{tag}", "ebit / u", ebit=ebit_wert(r, d, j), u=umsatz)
            )
        if d.hat("capex", j) and d.hat("depreciation", j):
            out["investition"].append(
                r.schritt(
                    f"investition_{tag}",
                    "(capex - abschreibungen) / u",
                    capex=d.hole("capex", j),
                    abschreibungen=d.hole("depreciation", j),
                    u=umsatz,
                )
            )
        if d.hat("current_assets", j) and d.hat("current_liabilities", j) and d.hat("cash", j):
            out["working_capital"].append(
                r.schritt(
                    f"working_capital_{tag}",
                    "(ua - kasse - wp - (kv - fk_kurz - kredite - cp)) / u",
                    ua=d.hole("current_assets", j),
                    kasse=d.hole("cash", j),
                    wp=_opt(r, d, "st_investments", j),
                    kv=d.hole("current_liabilities", j),
                    fk_kurz=_opt(r, d, "debt_current", j),
                    kredite=_opt(r, d, "short_term_borrowings", j),
                    cp=_opt(r, d, "commercial_paper", j),
                    u=umsatz,
                )
            )
    return out


def stufen(r: Rechenweg, d: Reihen, t: date) -> dict[str, dict[str, Decimal]]:
    """Je Größe die drei Stufen aus der Historie. Mindestens 3 Werte je Größe."""
    hist = _historie(r, d, t)
    out: dict[str, dict[str, Decimal]] = {}
    for groesse, werte in hist.items():
        if len(werte) < 3:
            raise EingabeFehlt(
                f"{groesse}: mindestens 3 Werte für die Szenario-Stufen ({len(werte)})",
                t.isoformat(),
            )
        out[groesse] = {
            stufe: r.perzentil(f"stufe_{groesse}_{stufe}", werte, anteil)
            for stufe, anteil in STUFEN.items()
        }
    r.pruefe(
        "CP-02",
        "Stufen geordnet (niedrig <= mittel <= hoch)",
        all(s["niedrig"] <= s["mittel"] <= s["hoch"] for s in out.values()),
    )
    return out


@dataclass(frozen=True)
class Szenario:
    unternehmenswert: Decimal
    je_aktie: Decimal
    endwert_anteil: Decimal


def szenario_rechnung(
    r: Rechenweg,
    d: Reihen,
    t: date,
    name: str,
    annahmen: dict[str, Decimal],
    kk: Kapitalkosten,
    wacc: Wert,
    g_end: Wert,
    jahre: int,
    ausblenden_ab: int,
) -> Szenario:
    """Ein Szenario Jahr für Jahr im Rechenweg, mit Brücke zum Wert je Aktie."""
    p = name
    operativ = r.schritt(
        f"{p}_operative_quote",
        "marge * (1 - steuer) - investition",
        marge=annahmen["marge"],
        steuer=kk.steuer,
        investition=annahmen["investition"],
    )
    if operativ <= 0:
        raise NichtDefiniert(
            "Marge nach Steuern und Investitionen nicht positiv: DCF nicht aussagekräftig "
            "(Scorecard Wachstum ohne Gewinn ab Schritt 8)"
        )
    wc, g = annahmen["working_capital"], annahmen["wachstum"]
    u_vor: Wert = d.hole("revenue", t)
    abz: Wert = Decimal(1)
    teile: dict[str, Decimal] = {}
    schritte = jahre - ausblenden_ab + 1
    for j in range(1, jahre + 1):
        if j < ausblenden_ab:
            g_j = r.schritt(f"{p}_g_{j}", "g", g=g)
        else:
            g_j = r.schritt(
                f"{p}_g_{j}",
                f"g - (g - g_end) * {j - ausblenden_ab + 1} / {schritte}",
                g=g,
                g_end=g_end,
            )
        u = r.schritt(f"{p}_umsatz_{j}", "u * (1 + g)", u=u_vor, g=g_j)
        fcff = r.schritt(
            f"{p}_fcff_{j}", "u * op - (u - u_vor) * wc", u=u, op=operativ, u_vor=u_vor, wc=wc
        )
        abz = r.schritt(f"{p}_abzinsung_{j}", "a * (1 + w)", a=abz, w=wacc)
        teile[f"bw_{j}"] = r.schritt(f"{p}_bw_{j}", "fcff / a", fcff=fcff, a=abz)
        u_vor = u
    prognose = r.schritt(f"{p}_prognose", " + ".join(teile), **teile)
    u_end = r.schritt(f"{p}_umsatz_endwert", "u * (1 + g_end)", u=u_vor, g_end=g_end)
    fcff_end = r.schritt(
        f"{p}_fcff_endwert",
        "u * op - (u - u_vor) * wc",
        u=u_end,
        op=operativ,
        u_vor=u_vor,
        wc=wc,
    )
    endwert = r.schritt(f"{p}_endwert", "fcff / (w - g_end)", fcff=fcff_end, w=wacc, g_end=g_end)
    ew_bw = r.schritt(f"{p}_endwert_barwert", "e / a", e=endwert, a=abz)
    ev = r.schritt(f"{p}_unternehmenswert", "p + e", p=prognose, e=ew_bw)
    r.pruefe("CP-02", f"{p}: Unternehmenswert positiv", ev > 0)
    anteil = r.schritt(f"{p}_endwert_anteil", "e / ev", e=ew_bw, ev=ev)

    # Brücke Unternehmenswert -> Eigenkapital (SPEC 3.6 Nr. 6), Posten wie in enterprise_value
    nd = nettoverschuldung(r, d, t)
    ausf = _opt(r, d, "pension_funded_status", t)
    if d.hat("equity_incl_nci", t) and d.hat("equity", t):
        minder: Wert = r.schritt(
            f"{p}_minderheiten",
            "ek_gesamt - ek_aktionaere",
            ek_gesamt=d.hole("equity_incl_nci", t),
            ek_aktionaere=d.hole("equity", t),
        )
    else:
        minder = Decimal(0)
    bet = _opt(r, d, "equity_investments", t)
    ek = r.schritt(
        f"{p}_eigenkapital",
        "ev - nd + ausfinanzierung - minderheiten + beteiligungen",
        ev=ev,
        nd=nd,
        ausfinanzierung=ausf,
        minderheiten=minder,
        beteiligungen=bet,
    )
    zurueck = r.schritt(
        f"{p}_bruecke_zurueck",
        "ek + nd - ausfinanzierung + minderheiten - beteiligungen",
        ek=ek,
        nd=nd,
        ausfinanzierung=ausf,
        minderheiten=minder,
        beteiligungen=bet,
    )
    r.pruefe(
        "CP-03",
        f"{p}: Brücke Eigenkapital -> Unternehmenswert geht auf",
        abs(zurueck - ev) <= abs(ev) * Decimal("1e-20"),
    )
    je_aktie = r.schritt(f"{p}_je_aktie", "ek / aktien", ek=ek, aktien=_aktien(r, d, t))
    return Szenario(ev, je_aktie, anteil)


def _szenario_metric(r: Rechenweg, d: Reihen, t: date, szenario: str) -> Decimal:
    cfg = d.parameter.get("kapitalkosten", {})
    if not cfg or "szenarien" not in cfg:
        raise EingabeFehlt("config/kapitalkosten.yaml szenarien", t.isoformat())
    kk = kapitalkosten(r, d, t)
    end_max = d.hole("endwachstum_max", t)
    g_end = r.schritt("endwachstum", "min(rf, maximum)", rf=kk.rf, maximum=end_max)
    r.pruefe("CP-02", "WACC über dem Endwachstum", kk.wacc > g_end)
    st = stufen(r, d, t)
    wahl = cfg["szenarien"][szenario]
    annahmen = {g: st[g][wahl[g]] for g in GROESSEN}
    jahre, ausblenden = int(cfg["jahre"]), int(cfg["ausblenden_ab_jahr"])
    s = szenario_rechnung(r, d, t, szenario, annahmen, kk, kk.wacc, g_end, jahre, ausblenden)
    if s.endwert_anteil > Decimal(str(cfg["endwert_anteil_hinweis"])):
        r.vermerk(
            f"ENDWERT_ANTEIL_HOCH: {s.endwert_anteil:.0%} des Werts aus dem Endwert, der Wert "
            "hängt fast nur von Annahmen über die ferne Zukunft ab (SPEC 3.6 Nr. 5)"
        )
    if szenario == "base":
        _sensitivitaet(r, d, t, annahmen, kk, g_end, (jahre, ausblenden), cfg, s)
    # Vergleich mit dem Kurs in Berichtswährung, als Schritt für die Anzeige
    r.schritt("kurs_vergleich", "wert / kurs - 1", wert=s.je_aktie, kurs=kurs(r, d, t))
    return s.je_aktie


def _wert_schnell(
    umsatz0: Decimal,
    a: dict[str, Decimal],
    steuer: Decimal,
    wacc: Decimal,
    g_end: Decimal,
    laufzeit: tuple[int, int],
    bruecke: Decimal,
    aktien: Decimal,
) -> Decimal:
    """Dieselbe Rechnung wie `szenario_rechnung` ohne Protokoll, für die Sensitivität.
    `bruecke` = Eigenkapital minus Unternehmenswert (aus dem Base-Szenario)."""
    jahre, ausblenden_ab = laufzeit
    with localcontext() as ctx:
        ctx.prec = 40
        op = a["marge"] * (1 - steuer) - a["investition"]
        g, wc = a["wachstum"], a["working_capital"]
        u_vor, abz, summe = umsatz0, Decimal(1), Decimal(0)
        schritte = jahre - ausblenden_ab + 1
        for j in range(1, jahre + 1):
            g_j = g if j < ausblenden_ab else g - (g - g_end) * (j - ausblenden_ab + 1) / schritte
            u = u_vor * (1 + g_j)
            abz *= 1 + wacc
            summe += (u * op - (u - u_vor) * wc) / abz
            u_vor = u
        u_end = u_vor * (1 + g_end)
        endwert = (u_end * op - (u_end - u_vor) * wc) / (wacc - g_end)
        return (summe + endwert / abz + bruecke) / aktien


def _sensitivitaet(
    r: Rechenweg,
    d: Reihen,
    t: date,
    annahmen: dict[str, Decimal],
    kk: Kapitalkosten,
    g_end: Decimal,
    laufzeit: tuple[int, int],
    cfg: dict[str, object],
    base: Szenario,
) -> None:
    """Wert je Aktie über WACC ±1 Prozentpunkt und Endwachstum ±0,5 Prozentpunkte (SPEC 3.6
    Nr. 4). Je Zelle ein Schritt `sens_wacc_<Δ>_g_<Δ>`. Die Zelle ohne Verschiebung muss das
    Base-Szenario treffen (CP-04)."""
    sens = cfg.get("sensitivitaet", {})
    assert isinstance(sens, dict)
    umsatz0 = d.hole("revenue", t).wert
    steuer = _wert(kk.steuer)
    aktien = _aktien(r, d, t)
    bruecke = r.schritt(
        "sens_bruecke",
        "je_aktie * aktien - ev",
        je_aktie=base.je_aktie,
        aktien=aktien,
        ev=base.unternehmenswert,
    )
    for dw in sens.get("wacc", []):
        for dg in sens.get("endwachstum", []):
            w = kk.wacc + Decimal(str(dw))
            ge = g_end + Decimal(str(dg))
            if w <= ge:
                continue
            wert = _wert_schnell(umsatz0, annahmen, steuer, w, ge, laufzeit, bruecke, aktien)
            r.schritte.append(
                Schritt(
                    name=f"sens_wacc_{dw}_g_{dg}",
                    formel="Base-Szenario mit WACC + Δw und Endwachstum + Δg, Wert je Aktie",
                    eingaben={"wacc": str(w), "g_end": str(ge)},
                    ergebnis=str(wert),
                )
            )
            if Decimal(str(dw)) == 0 and Decimal(str(dg)) == 0:
                r.pruefe(
                    "CP-04",
                    "Sensitivität ohne Verschiebung trifft das Base-Szenario",
                    abs(wert - base.je_aktie) <= abs(base.je_aktie) * Decimal("1e-12"),
                )


@metric("dcf_bear")
def dcf_bear(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _szenario_metric(r, d, t, "bear")


@metric("dcf_base")
def dcf_base(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _szenario_metric(r, d, t, "base")


@metric("dcf_bull")
def dcf_bull(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _szenario_metric(r, d, t, "bull")
