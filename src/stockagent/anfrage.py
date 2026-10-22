"""Anfrage in eigenen Worten (SPEC 9.7, 9.9, ADR 0014).

Ein Satz wird zu einem festen Filter `request.json` (Pydantic-Modell `Anfrage`). Zuerst versteht
eine feste Wortliste (`config/vokabular.yaml`) den Satz ohne Modell. Nur wenn Wörter übrig
bleiben, fragt `uebersetzen` Claude Code ohne Werkzeuge (`claude -p --json-schema`). Erlaubt sind
in beiden Fällen nur Werte aus den Listen: Länder, Regionen, Branchen aus `config/sectors.yaml`,
Größenklassen, Noten, Kategorien, Stile, Horizonte. Ein unbekanntes Land, eine unbekannte
Branche oder ein Thema ohne Branchencode wird abgelehnt, nicht geraten.

Die Trefferliste entsteht danach deterministisch aus der Datenbank (`titelliste`), nie aus dem
Vorwissen eines Modells (HR-04).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from stockagent.core.identifiers import isin_is_valid
from stockagent.paths import Paths

NOTEN = ("A", "B", "C", "D", "E")
STUFEN = ("1", "2", "3", "4")
ARTIKEL = {"der", "die", "das", "den", "dem", "des"}
TOKEN = re.compile(r"[a-zäöüß0-9&]+")
ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
PROMPT = Path(__file__).parent / "agents" / "prompts" / "uebersetzer.md"


class Anfrage(BaseModel):
    """Inhalt von `runs/<lauf>/request.json` und `state/last_request.yaml` (SPEC 9.7)."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    weg: Literal["wortliste", "modell", "dialog", "optionen", "profil", "ansicht", "dashboard"] = (
        "optionen"
    )
    stufen: list[int] = []
    laender: list[str] = []
    region: str | None = None
    hauptbranchen: list[str] = []
    unterbranchen: list[str] = []
    groessen: list[str] = []
    noten: list[str] = []
    kategorien: list[str] = []
    stile: list[str] = []
    horizont: str | None = None
    handelbarkeit: Literal["alle", "bestaetigt"] = "alle"
    beobachtungsliste: Literal["nein", "nur", "dazu"] = "nein"
    tiefe: Literal["schnell", "standard", "tief"] = "schnell"
    suche: str = ""
    isins: list[str] = []
    bewerten: bool = False

    def hat_auswahl(self) -> bool:
        """Grenzt die Anfrage die Titel überhaupt ein?"""
        return bool(
            self.stufen
            or self.laender
            or self.region
            or self.hauptbranchen
            or self.unterbranchen
            or self.groessen
            or self.noten
            or self.kategorien
            or self.stile
            or self.suche
            or self.isins
            or self.beobachtungsliste != "nein"
            or self.handelbarkeit != "alle"
        )


# ------------------------------------------------------------------ Vokabular


@dataclass(frozen=True)
class Muster:
    woerter: tuple[str, ...]
    stamm: bool  # letztes Wort ist ein Wortanfang
    art: str
    wert: str


@dataclass
class Vokabular:
    laender: dict[str, str]  # ISO -> Name
    regionen: dict[str, tuple[str, list[str]]]  # ID -> (Name, Länder)
    vergleichsregionen: set[str]  # Regionen, die das Dashboard als Spalte `region` kennt
    haupt: dict[str, str]  # ID -> Name
    unter: dict[str, tuple[str, str]]  # ID -> (Name, Hauptbranche)
    groessen: list[str]
    kategorien: list[str]
    stile: dict[str, dict[str, Any]]
    horizonte: dict[str, str]
    tiefen: dict[str, str]
    muster: list[Muster]
    fuellwoerter: set[str]
    ausloeser: dict[str, str]  # Wort -> land | branche
    modell: str  # Modellalias für die Übersetzung

    @classmethod
    def laden(cls, paths: Paths) -> Vokabular:
        def yml(name: str) -> dict[str, Any]:
            data: dict[str, Any] = yaml.safe_load((paths.config / name).read_text("utf-8"))
            return data

        vok, sek, sc = yml("vokabular.yaml"), yml("sectors.yaml"), yml("scoring.yaml")
        lauf, hz, mod = yml("run_profiles.yaml"), yml("horizonte.yaml"), yml("models.yaml")
        regionen_vg = sc["vergleichsgruppe"]["regionen"]
        regionen: dict[str, tuple[str, list[str]]] = {}
        for rid, r in vok["regionen"].items():
            laender = r.get("laender") or regionen_vg.get(rid)
            if not laender:
                raise ValueError(f"Region {rid} ohne Länder (vokabular.yaml oder scoring.yaml)")
            regionen[rid] = (str(r["name"]), [str(x) for x in laender])
        haupt = {hid: str(h["name"]) for hid, h in sek["hauptbranchen"].items()}
        unter = {
            uid: (str(u["name"]), hid)
            for hid, h in sek["hauptbranchen"].items()
            for uid, u in h["unter"].items()
        }
        muster: list[Muster] = []

        def dazu(woerter: Iterable[str], art: str, wert: str) -> None:
            for w in woerter:
                teile = TOKEN.findall(str(w).lower())
                if teile:
                    muster.append(Muster(tuple(teile), str(w).endswith("*"), art, wert))

        for iso, land in vok["laender"].items():
            dazu(land["woerter"], "land", str(iso))
        for rid, r in vok["regionen"].items():
            dazu(r["woerter"], "region", rid)
        for wort, ziel in vok["branchen"].items():
            if ziel not in haupt and ziel not in unter:
                raise ValueError(f"vokabular.yaml: Branche {ziel} fehlt in sectors.yaml")
            dazu([wort], "haupt" if ziel in haupt else "unter", ziel)
        for hid, name in haupt.items():
            dazu([name], "haupt", hid)
        for uid, (name, _) in unter.items():
            dazu([name], "unter", uid)
        for gid, woerter in vok["groessen"].items():
            dazu(woerter, "groesse", gid)
        for kat, woerter in vok["kategorien"].items():
            dazu(woerter, "kategorie", kat)
        for sid, woerter in vok["stile"].items():
            if sid not in lauf["stile"]:
                raise ValueError(f"vokabular.yaml: Stil {sid} fehlt in run_profiles.yaml")
            dazu(woerter, "stil", sid)
        for hid, woerter in vok["horizonte"].items():
            dazu(woerter, "horizont", hid)
        for tid, woerter in vok["tiefe"].items():
            dazu(woerter, "tiefe", tid)
        dazu(vok["handelbar"], "handelbar", "bestaetigt")
        dazu(vok["beobachtungsliste"], "beobachtung", "ja")
        dazu(vok["bewerten"], "bewerten", "ja")
        # Längere Wortfolgen zuerst, dann längere Wörter: „energieversorger“ vor „energie“
        muster.sort(key=lambda m: (len(m.woerter), len("".join(m.woerter))), reverse=True)
        ausloeser = {w: art for art, woerter in vok["ausloeser"].items() for w in woerter}
        klasse = mod["agenten"]["U0_uebersetzer"]
        return cls(
            laender={str(k): str(v["name"]) for k, v in vok["laender"].items()},
            regionen=regionen,
            vergleichsregionen=set(regionen_vg),
            haupt=haupt,
            unter=unter,
            groessen=[str(g) for g in sc["groessenklassen"]],
            kategorien=list(vok["kategorien"]),
            stile=dict(lauf["stile"]),
            horizonte={k: str(v["name"]) for k, v in hz["horizonte"].items()},
            tiefen={k: str(v["name"]) for k, v in lauf["tiefe"].items()},
            muster=muster,
            fuellwoerter={str(w) for w in vok["fuellwoerter"]},
            ausloeser=ausloeser,
            modell=str(mod["klassen"][klasse]),
        )


# ------------------------------------------------------------------ Prüfen


def pruefen(a: Anfrage, vok: Vokabular) -> list[str]:
    """Werte außerhalb der Listen. Leer heißt: die Anfrage ist gültig."""
    fehler = []

    def nicht_in(art: str, werte: Iterable[Any], erlaubt: Iterable[Any]) -> None:
        erlaubt = set(erlaubt)
        for w in werte:
            if w not in erlaubt:
                fehler.append(f"{art} „{w}“ ist in keiner Liste")

    nicht_in("Stufe", a.stufen, (1, 2, 3, 4))
    nicht_in("Land", a.laender, vok.laender)
    nicht_in("Region", [a.region] if a.region else [], vok.regionen)
    nicht_in("Hauptbranche", a.hauptbranchen, vok.haupt)
    nicht_in("Unterbranche", a.unterbranchen, vok.unter)
    nicht_in("Größenklasse", a.groessen, vok.groessen)
    nicht_in("Note", a.noten, NOTEN)
    nicht_in("Kategorie", a.kategorien, vok.kategorien)
    nicht_in("Stil", a.stile, vok.stile)
    nicht_in("Anlagehorizont", [a.horizont] if a.horizont else [], vok.horizonte)
    for s in a.stile:
        if s in vok.stile and vok.stile[s].get("gebaut") is False:
            grund = vok.stile[s].get("grund", "nicht gebaut")
            fehler.append(f"Stil {vok.stile[s]['name']}: {grund}")
    for isin in a.isins:
        if not isin_is_valid(isin):
            fehler.append(f"ISIN „{isin}“ ist ungültig")
    return fehler


# ------------------------------------------------------------------ Wortliste


@dataclass
class Verstanden:
    anfrage: Anfrage
    abgelehnt: list[str] = field(default_factory=list)
    rest: list[str] = field(default_factory=list)  # nicht verstandene Wörter
    hinweise: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.abgelehnt


def _einmal(werte: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(werte))


def _bereich(a: str, b: str | None, liste: tuple[str, ...], verbinder: str) -> list[str]:
    """„1 bis 3“ -> 1, 2, 3; „A oder B“ -> A, B."""
    if b is None:
        return [a]
    if verbinder == "bis":
        unten, oben = min(a, b), max(a, b)
        return [x for x in liste if unten <= x <= oben]
    return [a, b]


def wortliste(text: str, vok: Vokabular) -> Verstanden:
    """Satz über die feste Wortliste verstehen, ohne Modell."""
    roh = text.strip()
    if ISIN.match(roh.upper()) and isin_is_valid(roh.upper()):
        return Verstanden(Anfrage(text=roh, weg="wortliste", suche=roh.upper()))
    tokens = TOKEN.findall(roh.lower())
    verbraucht = [False] * len(tokens)
    funde: list[tuple[str, str]] = []

    # Stufe und Note mit Zahlen- oder Buchstabenbereich
    starts: list[int] = []
    pos = 0
    for t in tokens:
        starts.append(pos)
        pos += len(t)
        pos += 1
    satz = " ".join(tokens)

    def markiere(von: int, bis: int) -> None:
        for i, s in enumerate(starts):
            if von <= s < bis:
                verbraucht[i] = True

    stufen: list[str] = []
    for m in re.finditer(
        r"\b(?:tier|stufe)\s?([1-4])(?:\s(bis|und|oder)\s(?:tier\s|stufe\s)?([1-4]))?\b", satz
    ):
        stufen.extend(_bereich(m.group(1), m.group(3), STUFEN, m.group(2) or ""))
        markiere(m.start(), m.end())
    noten: list[str] = []
    for m in re.finditer(r"\bnoten?\s([a-e])(?:\s(bis|und|oder)\s([a-e]))?\b", satz):
        b = m.group(3).upper() if m.group(3) else None
        noten.extend(_bereich(m.group(1).upper(), b, NOTEN, m.group(2) or ""))
        markiere(m.start(), m.end())

    for mu in vok.muster:
        for i in range(len(tokens)):
            # Wortfolge ab Position i: (Index, Wort im Satz, Wort des Musters, letztes Wort?)
            folge = [
                (k, tokens[k], w, w is mu.woerter[-1])
                for k, w in zip(range(i, len(tokens)), mu.woerter, strict=False)
            ]
            if len(folge) < len(mu.woerter):
                break
            if all(
                not verbraucht[k] and (t.startswith(w) if mu.stamm and letztes else t == w)
                for k, t, w, letztes in folge
            ):
                for k, *_ in folge:
                    verbraucht[k] = True
                funde.append((mu.art, mu.wert))

    abgelehnt: list[str] = []
    for i, t in enumerate(tokens):
        art = vok.ausloeser.get(t)
        if art is None or verbraucht[i]:
            continue
        j = next((k for k in range(i, len(tokens)) if k > i and tokens[k] not in ARTIKEL), None)
        if j is None or verbraucht[j] or tokens[j] in vok.fuellwoerter:
            continue
        if tokens[j].isalpha():
            name = "Land" if art == "land" else "Branche"
            abgelehnt.append(
                f"{name} „{tokens[j]}“ ist in keiner Liste (config/vokabular.yaml). "
                "Ohne passenden Listenwert wird nicht geraten."
            )
            verbraucht[j] = True

    rest = [
        t
        for i, t in enumerate(tokens)
        if not verbraucht[i] and t not in vok.fuellwoerter and len(t) > 1 and not t.isdigit()
    ]

    def werte(art: str) -> list[str]:
        return _einmal(w for a, w in funde if a == art)

    a = Anfrage(
        text=roh,
        weg="wortliste",
        stufen=[int(s) for s in _einmal(stufen)],
        laender=werte("land"),
        region=next(iter(werte("region")), None),
        hauptbranchen=werte("haupt"),
        unterbranchen=werte("unter"),
        groessen=werte("groesse"),
        noten=_einmal(noten),
        kategorien=werte("kategorie"),
        stile=werte("stil"),
        horizont=next(iter(werte("horizont")), None),
        handelbarkeit="bestaetigt" if werte("handelbar") else "alle",
        tiefe=next(iter(werte("tiefe")), "schnell"),
        bewerten=bool(werte("bewerten")),
    )
    if len(werte("region")) > 1:
        abgelehnt.append(f"Mehrere Regionen genannt ({', '.join(werte('region'))}), bitte eine")
    if werte("beobachtung"):
        a.beobachtungsliste = "dazu" if a.hat_auswahl() else "nur"
    if a.tiefe != "schnell":
        a.bewerten = True
    abgelehnt.extend(pruefen(a, vok))
    return Verstanden(a, abgelehnt, rest)


# ------------------------------------------------------------------ Modell (claude -p)


def _liste(werte: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in werte.items())


def modell_prompt(text: str, vok: Vokabular) -> str:
    vorlage = PROMPT.read_text("utf-8").split("\n---\n", 1)[1].strip()
    ersatz = {
        "laender": _liste(vok.laender),
        "regionen": _liste({k: v[0] for k, v in vok.regionen.items()}),
        "hauptbranchen": _liste(vok.haupt),
        "unterbranchen": "; ".join(f"{k}: {n} ({vok.haupt[h]})" for k, (n, h) in vok.unter.items()),
        "groessen": ", ".join(vok.groessen),
        "kategorien": ", ".join(vok.kategorien),
        "stile": _liste({k: str(v["name"]) for k, v in vok.stile.items()}),
        "horizonte": _liste(vok.horizonte),
        # Lucas Text zuletzt, damit geschweifte Klammern darin nichts ersetzen
        "text": text.replace("ANFRAGE ENDE", "ANFRAGE_ENDE"),
    }
    for k, v in ersatz.items():
        vorlage = vorlage.replace("{" + k + "}", v)
    return vorlage


def modell_schema(vok: Vokabular) -> dict[str, Any]:
    def liste(werte: Iterable[Any], typ: str = "string") -> dict[str, Any]:
        return {"type": "array", "items": {"type": typ, "enum": list(werte)}}

    def eins(werte: Iterable[Any]) -> dict[str, Any]:
        return {"anyOf": [{"type": "string", "enum": list(werte)}, {"type": "null"}]}

    eigenschaften: dict[str, Any] = {
        "stufen": liste([1, 2, 3, 4], "integer"),
        "laender": liste(vok.laender),
        "region": eins(vok.regionen),
        "hauptbranchen": liste(vok.haupt),
        "unterbranchen": liste(vok.unter),
        "groessen": liste(vok.groessen),
        "noten": liste(NOTEN),
        "kategorien": liste(vok.kategorien),
        "stile": liste(vok.stile),
        "horizont": eins(vok.horizonte),
        "handelbarkeit": {"type": "string", "enum": ["alle", "bestaetigt"]},
        "beobachtungsliste": {"type": "string", "enum": ["nein", "nur", "dazu"]},
        "tiefe": {"type": "string", "enum": list(vok.tiefen)},
        "bewerten": {"type": "boolean"},
        "unbekannt": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "art": {"type": "string", "enum": ["land", "branche", "thema", "sonstiges"]},
                    "wort": {"type": "string"},
                },
                "required": ["art", "wort"],
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": eigenschaften,
        "required": list(eigenschaften),
    }


def aus_modell(text: str, daten: dict[str, Any], vok: Vokabular) -> Verstanden:
    """Antwort des Modells prüfen. Jeder Wert außerhalb der Listen lehnt die Anfrage ab."""
    daten = dict(daten)
    abgelehnt = []
    for u in daten.pop("unbekannt", None) or []:
        art, wort = str(u.get("art", "sonstiges")), str(u.get("wort", ""))
        grund = {
            "land": f"Land „{wort}“ ist in keiner Liste",
            "branche": f"Branche „{wort}“ ist in keiner Liste",
            "thema": f"Thema „{wort}“ hat keinen Branchencode. Die Suche in den "
            "Geschäftsbeschreibungen (Agent A0) ist noch nicht gebaut",
        }.get(art, f"„{wort}“ nicht verstanden")
        abgelehnt.append(grund)
    try:
        a = Anfrage(text=text.strip(), weg="modell", **daten)
    except ValidationError as exc:
        fehler = "; ".join(str(e["msg"]) for e in exc.errors()[:3])
        return Verstanden(
            Anfrage(text=text.strip(), weg="modell"),
            [*abgelehnt, f"Antwort des Modells passt nicht zum Schema: {fehler}"],
        )
    if a.tiefe != "schnell":
        a.bewerten = True
    return Verstanden(a, [*abgelehnt, *pruefen(a, vok)])


Modell = Callable[[str], dict[str, Any]]


def uebersetzen(
    text: str,
    vok: Vokabular,
    *,
    namens_treffer: Callable[[str], int] | None = None,
    modell: Modell | None = None,
) -> Verstanden:
    """Wortliste zuerst. Das Modell nur, wenn Wörter übrig bleiben, die weder Füllwort noch Name
    einer Aktie sind (SPEC 9.9)."""
    v = wortliste(text, vok)
    roh = text.strip()
    if not v.ok or not roh:
        return v
    a = v.anfrage
    nichts_erkannt = not (a.hat_auswahl() or a.horizont or a.bewerten or a.tiefe != "schnell")
    # Nichts erkannt: Name, WKN oder Ticker? Dann ohne Modell zur Aktie (SPEC 13.5)
    if nichts_erkannt and (namens_treffer is None or namens_treffer(roh) > 0):
        return Verstanden(Anfrage(text=roh, weg="wortliste", suche=roh))
    if not v.rest:
        return v
    if modell is None:
        if not v.anfrage.hat_auswahl():
            return Verstanden(
                Anfrage(text=roh, weg="wortliste", suche=roh),
                hinweise=["Kein Name passt, Claude Code steht für die Übersetzung nicht bereit"],
            )
        v.hinweise.append(
            f"Nicht verstanden und nicht berücksichtigt: {', '.join(v.rest)} "
            "(Claude Code steht für die Übersetzung nicht bereit)"
        )
        return v
    try:
        antwort = modell(roh)
    except Exception as exc:  # Modell nicht erreichbar: Wortliste gilt, Rest wird gemeldet
        v.hinweise.append(
            f"Übersetzung über Claude Code fehlgeschlagen ({exc}). Nicht "
            f"berücksichtigt: {', '.join(v.rest)}"
        )
        return v
    return aus_modell(roh, antwort, vok)


def claude_modell(vok: Vokabular) -> Modell | None:
    """Übersetzung über `claude -p`, oder None, wenn Claude Code nicht installiert ist."""
    from stockagent import claude_cli

    if claude_cli.pfad() is None:
        return None

    def frage(text: str) -> dict[str, Any]:
        return claude_cli.strukturiert(modell_prompt(text, vok), modell_schema(vok), vok.modell)

    return frage


# ------------------------------------------------------------------ Dashboard-Filter


def als_filter(a: Anfrage, vok: Vokabular) -> dict[str, str]:
    """Anfrage als Filter der Titelliste (Adresszeile des Dashboards)."""
    f: dict[str, str] = {}
    laender = list(a.laender)
    if a.region and a.region not in vok.vergleichsregionen:
        laender.extend(vok.regionen[a.region][1])
    elif a.region:
        f["region"] = a.region
    if a.stufen:
        f["tier"] = ",".join(str(s) for s in a.stufen)
    if laender:
        f["land"] = ",".join(_einmal(laender))
    if a.hauptbranchen:
        f["branche"] = ",".join(vok.haupt[h] for h in a.hauptbranchen)
    if a.unterbranchen:
        f["unterbranche"] = ",".join(vok.unter[u][0] for u in a.unterbranchen)
    for schluessel, werte in (
        ("groesse", a.groessen),
        ("note", a.noten),
        ("kategorie", a.kategorien),
        ("stil", a.stile),
        ("isin", a.isins),
    ):
        if werte:
            f[schluessel] = ",".join(werte)
    if a.horizont:
        f["horizont"] = a.horizont
    if a.handelbarkeit == "bestaetigt":
        f["tr"] = "bestaetigt"
    if a.beobachtungsliste == "nur":
        f["stern"] = "1"
    elif a.beobachtungsliste == "dazu":
        f["beobachtung"] = "dazu"
    if a.suche:
        f["q"] = a.suche
    return f


def aus_filter(f: dict[str, str], vok: Vokabular, weg: str = "dashboard") -> Anfrage:
    """Filter der Adresszeile zurück in eine Anfrage (für `request.json`)."""

    def teile(k: str) -> list[str]:
        return [x for x in (f.get(k) or "").split(",") if x]

    haupt = {v: k for k, v in vok.haupt.items()}
    unter = {v[0]: k for k, v in vok.unter.items()}
    return Anfrage(
        text=f.get("text", ""),
        weg=weg,
        stufen=[int(s) for s in teile("tier") if s in STUFEN],
        laender=teile("land"),
        region=f.get("region") or None,
        hauptbranchen=[haupt.get(b, b) for b in teile("branche")],
        unterbranchen=[unter.get(b, b) for b in teile("unterbranche")],
        groessen=teile("groesse"),
        noten=teile("note"),
        kategorien=teile("kategorie"),
        stile=teile("stil"),
        horizont=f.get("horizont") or None,
        handelbarkeit="bestaetigt" if f.get("tr") == "bestaetigt" else "alle",
        beobachtungsliste="nur"
        if f.get("stern") == "1"
        else "dazu"
        if f.get("beobachtung") == "dazu"
        else "nein",
        tiefe=f.get("tiefe") if f.get("tiefe") in vok.tiefen else "schnell",
        suche=f.get("q", ""),
        isins=teile("isin"),
    )


def beschreibung(a: Anfrage, vok: Vokabular) -> list[tuple[str, str]]:
    """Verstandener Filter als (Art, Text) für die Schaltflächen (SPEC 9.9 Nr. 2)."""
    out: list[tuple[str, str]] = []
    if a.stufen:
        out.append(
            (
                "Stufe",
                "Tier " + " bis ".join(str(s) for s in (min(a.stufen), max(a.stufen)))
                if len(a.stufen) > 1
                else f"Tier {a.stufen[0]}",
            )
        )
    if a.laender:
        out.append(("Land", ", ".join(vok.laender.get(x, x) for x in a.laender)))
    if a.region:
        out.append(("Region", vok.regionen[a.region][0] if a.region in vok.regionen else a.region))
    for h in a.hauptbranchen:
        out.append(("Branche", vok.haupt.get(h, h)))
    for u in a.unterbranchen:
        name, h = vok.unter.get(u, (u, ""))
        out.append(("Branche", f"{name} (Unterbranche von {vok.haupt.get(h, h)})"))
    if a.groessen:
        out.append(("Größe", ", ".join(a.groessen)))
    if a.noten:
        out.append(("Note", ", ".join(a.noten)))
    if a.kategorien:
        out.append(("Kategorie", ", ".join(a.kategorien)))
    for s in a.stile:
        out.append(("Stil", str(vok.stile.get(s, {}).get("name", s))))
    if a.horizont:
        out.append(("Horizont", vok.horizonte.get(a.horizont, a.horizont)))
    if a.handelbarkeit == "bestaetigt":
        out.append(("Trade Republic", "nur geprüft handelbar"))
    if a.beobachtungsliste != "nein":
        out.append(("Beobachtungsliste", a.beobachtungsliste))
    if a.tiefe != "schnell":
        out.append(("Tiefe", vok.tiefen[a.tiefe]))
    if a.suche:
        out.append(("Suche", a.suche))
    return out


# ------------------------------------------------------------------ Gespeicherte Ansichten


def _views(paths: Paths) -> Path:
    return paths.root / "state" / "views.yaml"


def ansichten(paths: Paths) -> dict[str, dict[str, Any]]:
    datei = _views(paths)
    if not datei.exists():
        return {}
    data = yaml.safe_load(datei.read_text("utf-8")) or {}
    return dict(data.get("ansichten") or {})


def ansicht(paths: Paths, name: str) -> dict[str, str] | None:
    """Filter einer gespeicherten Ansicht, Name ohne Rücksicht auf Groß- und Kleinschreibung."""
    for n, a in ansichten(paths).items():
        if n.strip().lower() == name.strip().lower():
            return {str(k): str(v) for k, v in (a.get("filter") or {}).items()}
    return None


def ansicht_speichern(paths: Paths, name: str, filter_: dict[str, str] | None) -> None:
    """Ansicht unter Namen ablegen, mit `filter_ = None` löschen (`state/views.yaml`)."""
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Name der Ansicht fehlt oder ist zu lang")
    alle = ansichten(paths)
    if filter_ is None:
        alle.pop(name, None)
    else:
        alle[name] = {
            "filter": {k: v for k, v in filter_.items() if v},
            "gespeichert": datetime.now(UTC).strftime("%Y-%m-%d"),
        }
    datei = _views(paths)
    datei.parent.mkdir(parents=True, exist_ok=True)
    kopf = "# Gespeicherte Ansichten des Dashboards (SPEC 13.5), Name -> Filter\n"
    datei.write_text(
        kopf + yaml.safe_dump({"ansichten": alle}, sort_keys=True, allow_unicode=True), "utf-8"
    )
