"""Insider-Signal (SPEC 3.8, Bauschritt 9, ADR 0012). Reine Rechnung ohne I/O.

Regeln (Schwellen und Gewichte in `config/insider_thresholds.yaml`):

1. Nur Geschäfte am offenen Markt (Form 4 Code P und S). Zuteilungen, Ausübungen,
   Steuereinbehalte und Schenkungen zählen nicht.
2. Einordnung je Person nach Cohen, Malloy und Pomorski (2012): Wer in jedem der drei Vorjahre
   am offenen Markt gehandelt hat, ist routinemäßig, wenn er in jedem dieser Jahre auch im
   selben Kalendermonat gehandelt hat, sonst opportunistisch. Weniger als drei Jahre Historie:
   unklar mit halbem Gewicht. Geschäfte unter einem Handelsplan (Rule 10b5-1) sind routinemäßig.
3. Beitrag eines Kaufs = Klassengewicht * Rollengewicht * Größenfaktor * Abklingen, im Cluster
   (mindestens 3 Personen mit nicht routinemäßigen Käufen in 60 Tagen) doppelt.
4. Verkäufe zählen nur, wenn mindestens 3 Personen in 60 Tagen opportunistisch verkaufen, mit
   eigenem, kleinerem Faktor und negativem Vorzeichen.
5. Abklingen 0,5 ^ (Alter in Tagen / 90).
6. Säule Insider = neutral + je_einheit * Summe der Beiträge, begrenzt auf 0 bis 100. Ohne
   Geschäft am offenen Markt im Fenster gibt es kein Signal (Säule fehlt, ihr Gewicht geht auf
   die anderen Säulen).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from stockagent.core.calc import NichtDefiniert, Rechenweg, rechne

VERSION = "1.0"
KENNZAHL = ("insider_signal", "wert")


class Geschaeft(Protocol):
    """Lesesicht auf ein Geschäft (`form4.InsiderTx` oder `store.InsiderRow`)."""

    @property
    def tx_id(self) -> str: ...

    @property
    def person_id(self) -> str: ...

    @property
    def person_name(self) -> str: ...

    @property
    def rolle(self) -> str: ...

    @property
    def art(self) -> str: ...

    @property
    def offener_markt(self) -> bool: ...

    @property
    def plan_10b5_1(self) -> bool: ...

    @property
    def stueck(self) -> Decimal: ...

    @property
    def bestand_danach(self) -> Decimal | None: ...

    @property
    def handelstag(self) -> date: ...


@dataclass(frozen=True)
class Bewertet:
    tx_id: str
    person: str
    rolle: str
    art: str
    handelstag: date
    klasse: str
    cluster: bool
    beitrag: Decimal


@dataclass
class InsiderSignal:
    saeule: Decimal | None
    summe: Decimal | None
    grund: str | None
    geschaefte: list[Bewertet] = field(default_factory=list)
    rechenweg: dict[str, Any] = field(default_factory=dict)


def _monate(rows: Sequence[Geschaeft]) -> dict[str, set[tuple[int, int]]]:
    out: dict[str, set[tuple[int, int]]] = {}
    for x in rows:
        out.setdefault(x.person_id, set()).add((x.handelstag.year, x.handelstag.month))
    return out


def klasse(x: Geschaeft, monate: Mapping[str, set[tuple[int, int]]], jahre: int) -> str:
    """routine, opportunistisch oder unklar (Cohen, Malloy, Pomorski 2012)."""
    if x.plan_10b5_1:
        return "routine"
    eigene = monate.get(x.person_id, set())
    vorjahre = [x.handelstag.year - k for k in range(1, jahre + 1)]
    if not all(any(j == y for j, _ in eigene) for y in vorjahre):
        return "unklar"
    if all((y, x.handelstag.month) in eigene for y in vorjahre):
        return "routine"
    return "opportunistisch"


def _im_cluster(x: Geschaeft, kandidaten: Sequence[Geschaeft], personen: int, tage: int) -> bool:
    """Gibt es ein Zeitfenster von `tage` Tagen mit x, in dem mindestens `personen` Personen
    handeln?"""
    for start in (k.handelstag for k in kandidaten):
        if not (0 <= (x.handelstag - start).days <= tage):
            continue
        im_fenster = {k.person_id for k in kandidaten if 0 <= (k.handelstag - start).days <= tage}
        if len(im_fenster) >= personen:
            return True
    return False


def signal(
    subjekt: str, rows: Sequence[Geschaeft], stichtag: date, cfg: Mapping[str, Any]
) -> InsiderSignal:
    s = cfg["signal"]
    offen = [x for x in rows if x.offener_markt and x.art in ("buy", "sell")]
    fenster = [x for x in offen if 0 <= (stichtag - x.handelstag).days <= int(s["fenster_tage"])]
    out = InsiderSignal(None, None, None)
    if not fenster:
        out.grund = (
            f"keine Käufe oder Verkäufe am offenen Markt in den letzten {s['fenster_tage']} Tagen"
        )
        return out
    monate = _monate(offen)
    jahre = int(s["historie_jahre"])
    klassen = {x.tx_id: klasse(x, monate, jahre) for x in fenster}
    kaeufe = [x for x in fenster if x.art == "buy" and klassen[x.tx_id] != "routine"]
    verkaeufe = [x for x in fenster if x.art == "sell" and klassen[x.tx_id] == "opportunistisch"]
    r = Rechenweg("insider_signal", VERSION, subjekt, stichtag.isoformat(), pflicht=("CP-02",))

    def rechnung(r: Rechenweg) -> Decimal:
        summe = r.schritt("start", "0")
        for x in fenster:
            k = klassen[x.tx_id]
            alter = (stichtag - x.handelstag).days
            abklingen = r.potenz(
                f"abklingen_{x.tx_id}", Decimal("0.5"), alter, int(s["halbwertszeit_tage"])
            )
            rolle = Decimal(str(s["rollen"].get(x.rolle, s["rollen"]["other"])))
            cluster = False
            if x.art == "buy":
                if k == "routine":
                    beitrag = Decimal(0)
                else:
                    c = s["cluster"]
                    cluster = _im_cluster(x, kaeufe, int(c["personen"]), int(c["tage"]))
                    g = s["groesse"]
                    if x.bestand_danach is not None and x.bestand_danach > x.stueck:
                        anteil = r.schritt(
                            f"aufstockung_{x.tx_id}",
                            "stueck / (bestand_danach - stueck)",
                            stueck=x.stueck,
                            bestand_danach=x.bestand_danach,
                        )
                        groesse = r.schritt(
                            f"groesse_{x.tx_id}",
                            "max(mindest, min(1, anteil / voll_ab))",
                            mindest=Decimal(str(g["mindestfaktor"])),
                            anteil=anteil,
                            voll_ab=Decimal(str(g["voll_ab"])),
                        )
                    else:
                        r.vermerk(
                            "BESTAND_UNBEKANNT: Eigenbestand vor dem Kauf unbekannt, volles Gewicht"
                        )
                        groesse = Decimal(1)
                    beitrag = r.schritt(
                        f"beitrag_{x.tx_id}",
                        "klasse * rolle * groesse * abklingen * cluster",
                        klasse=Decimal(str(s["klassen"][k])),
                        rolle=rolle,
                        groesse=groesse,
                        abklingen=abklingen,
                        cluster=Decimal(str(c["faktor"])) if cluster else Decimal(1),
                    )
            else:
                v = s["verkauf"]
                cluster = k == "opportunistisch" and _im_cluster(
                    x, verkaeufe, int(v["personen"]), int(v["tage"])
                )
                beitrag = (
                    r.schritt(
                        f"beitrag_{x.tx_id}",
                        "0 - faktor * rolle * abklingen",
                        faktor=Decimal(str(v["faktor"])),
                        rolle=rolle,
                        abklingen=abklingen,
                    )
                    if cluster
                    else Decimal(0)
                )
            out.geschaefte.append(
                Bewertet(x.tx_id, x.person_name, x.rolle, x.art, x.handelstag, k, cluster, beitrag)
            )
            summe = r.schritt(f"summe_nach_{x.tx_id}", "s + b", s=summe, b=beitrag)
        out.summe = summe
        q = s["saeule"]
        saeule = r.schritt(
            "saeule_insider",
            "max(0, min(100, neutral + je_einheit * summe))",
            neutral=Decimal(str(q["neutral"])),
            je_einheit=Decimal(str(q["je_einheit"])),
            summe=summe,
        )
        r.pruefe("CP-02", "Säule Insider zwischen 0 und 100", 0 <= saeule <= 100)
        if not any(g.beitrag != 0 for g in out.geschaefte):
            raise NichtDefiniert(
                "nur routinemäßige Geschäfte oder einzelne Verkäufe, kein Signal (SPEC 3.8)"
            )
        return saeule

    e = rechne(r, rechnung)
    out.saeule, out.grund, out.rechenweg = e.wert, e.grund, e.rechenweg
    return out
