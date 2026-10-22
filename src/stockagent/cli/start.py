"""Befehle `stockagent run` und `stockagent anfrage` (Bauschritt 11, SPEC 9.6, 9.7, 9.9).

`run` fragt ohne Optionen im Terminal dieselben zwei Runden wie der Skill `/stockagent`
(Bibliothek `questionary`), zeigt den Laufplan und startet erst nach Bestätigung. Mit Optionen
oder `--profile` läuft er ohne Rückfragen, mit `--yes` auch ohne Bestätigung.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Annotated, Any, Protocol

import typer
from rich.table import Table

from stockagent import anfrage as anf
from stockagent import lauf
from stockagent.cli.common import app, connect, console
from stockagent.paths import Paths
from stockagent.titelliste import Daten, passt

TIEFE_ALIAS = {"quick": "schnell", "fast": "schnell", "deep": "tief"}
GROESSEN_ALIAS = {"large": ["large", "mega"], "micro": ["micro", "nano"]}


class Fragen(Protocol):
    """Die vier Fragearten des Dialogs. Im Terminal `questionary`, in Tests eine Attrappe."""

    def auswahl(self, frage: str, optionen: list[str]) -> str: ...
    def mehrfach(self, frage: str, optionen: list[str]) -> list[str]: ...
    def text(self, frage: str) -> str: ...
    def ja(self, frage: str, standard: bool = True) -> bool: ...


class Questionary:
    def _antwort(self, frage: Any) -> Any:
        antwort = frage.ask()
        if antwort is None:  # Strg+C
            raise typer.Exit(code=1)
        return antwort

    def auswahl(self, frage: str, optionen: list[str]) -> str:
        import questionary

        return str(self._antwort(questionary.select(frage, choices=optionen)))

    def mehrfach(self, frage: str, optionen: list[str]) -> list[str]:
        import questionary

        return list(self._antwort(questionary.checkbox(frage, choices=optionen)))

    def text(self, frage: str) -> str:
        import questionary

        return str(self._antwort(questionary.text(frage)))

    def ja(self, frage: str, standard: bool = True) -> bool:
        import questionary

        return bool(self._antwort(questionary.confirm(frage, default=standard)))


# ------------------------------------------------------------------ Dialog (SPEC 9.7)


WAS = ("Branche", "Region oder Land", "Anlagestil", "Gesamtmarkt (beste Noten)", "Freitext")
GROESSEN = {
    "Large und Mega": ["large", "mega"],
    "Mid": ["mid"],
    "Small": ["small"],
    "Micro und Nano": ["micro", "nano"],
}
REGIONEN = {
    "Deutschland": ("land", "DE"),
    "DACH": ("region", "dach"),
    "Europa": ("region", "europa"),
    "Nordamerika": ("region", "nordamerika"),
    "Asien-Pazifik": ("region", "asien_pazifik"),
    "Schwellenländer": ("region", "schwellenlaender"),
    "Einzelnes Land (Freitext)": ("frei", ""),
}


def _nummern(text: str) -> list[int]:
    return [int(x) for x in text.replace(",", " ").split() if x.isdigit()]


def dialog(
    paths: Paths,
    vok: anf.Vokabular,
    daten: Daten,
    fragen: Fragen,
    modell: anf.Modell | None = None,
) -> anf.Anfrage:
    """Zwei Runden wie in SPEC 9.7. Zurück die Anfrage mit `weg = dialog`."""
    letzte = lauf.letzte_anfrage(paths)
    if letzte and fragen.ja(
        "Letzte Anfrage wiederholen? ("
        + (", ".join(t for _, t in anf.beschreibung(letzte, vok)) or "ganzes Universum")
        + ")",
        standard=False,
    ):
        return letzte.model_copy(update={"weg": "dialog"})

    a = anf.Anfrage(weg="dialog")
    # Runde 1
    was = fragen.auswahl("Was soll ich bewerten?", list(WAS))
    groessen = fragen.mehrfach("Welche Größenklassen? (keine Auswahl = alle)", list(GROESSEN))
    tiefe_namen = {v: k for k, v in vok.tiefen.items()}
    tiefe = fragen.auswahl("Wie tief?", list(tiefe_namen))
    tr = fragen.auswahl(
        "Handelbarkeit bei Trade Republic?",
        ["Alle (empfohlen)", "Nur von mir als handelbar geprüfte"],
    )
    a.groessen = [g for name in groessen for g in GROESSEN[name]]
    a.tiefe = tiefe_namen[tiefe]  # type: ignore[assignment]
    a.handelbarkeit = "alle" if tr.startswith("Alle") else "bestaetigt"

    # Runde 2
    if was == "Branche":
        nummern: list[tuple[str, str]] = []
        console.print("Branchen (Hauptbranche, darunter die Unterbranchen):")
        for hid, name in vok.haupt.items():
            nummern.append(("haupt", hid))
            console.print(f"{len(nummern):>3}  {name}")
            for uid, (uname, h) in vok.unter.items():
                if h == hid:
                    nummern.append(("unter", uid))
                    console.print(f"{len(nummern):>7}  {uname}")
        gewaehlt = _nummern(fragen.text("Nummern der Branchen, etwa „2, 5“:"))
        je_nummer = dict(enumerate(nummern, start=1))
        for n in gewaehlt:
            if n not in je_nummer:
                raise typer.BadParameter(f"Keine Branche mit Nummer {n}")
            art, bid = je_nummer[n]
            (a.hauptbranchen if art == "haupt" else a.unterbranchen).append(bid)
    elif was == "Region oder Land":
        wahl = fragen.auswahl("Welche Region?", list(REGIONEN))
        art, wert = REGIONEN[wahl]
        if art == "land":
            a.laender = [wert]
        elif art == "region":
            a.region = wert
        else:
            v = anf.wortliste(fragen.text("Welches Land?"), vok)
            if not v.anfrage.laender or not v.ok:
                raise typer.BadParameter("; ".join(v.abgelehnt) or "Land nicht erkannt")
            a.laender = v.anfrage.laender
    elif was == "Anlagestil":
        stile = {str(s["name"]): k for k, s in vok.stile.items() if s.get("gebaut", True)}
        a.stile = [stile[fragen.auswahl("Welcher Stil?", list(stile))]]
    elif was == "Freitext":
        satz = fragen.text("Thema, Satz oder Einzeltitel (Name, ISIN):")

        def namens_treffer(q: str) -> int:
            return sum(1 for z in daten.zeilen if passt(z, {"q": q}, daten.stile))

        v = anf.uebersetzen(satz, vok, namens_treffer=namens_treffer, modell=modell)
        if not v.ok:
            raise typer.BadParameter("; ".join(v.abgelehnt))
        for h in v.hinweise:
            console.print(f"[yellow]{h}[/yellow]")
        frei = v.anfrage
        if frei.suche:
            kandidaten = [z for z in daten.zeilen if passt(z, {"q": frei.suche}, daten.stile)]
            if not kandidaten:
                raise typer.BadParameter(f"Kein Titel passt zu „{frei.suche}“")
            if len(kandidaten) == 1:
                wahl_isin = kandidaten[0].isin
            else:
                optionen = [f"{z.name} ({z.isin}, {z.land})" for z in kandidaten[:20]]
                wahl = fragen.auswahl("Mehrere Treffer, welcher Titel?", optionen)
                wahl_isin = kandidaten[optionen.index(wahl)].isin
            a.isins = [wahl_isin]
        else:
            felder = [k for k in frei.model_fields_set if k not in ("text", "weg")]
            a = a.model_copy(update={k: getattr(frei, k) for k in felder})
        a.text = satz
    frage_liste = "Beobachtungsliste zusätzlich in die Tiefenanalyse nehmen?"
    if _beobachtung_moeglich(paths) and fragen.ja(frage_liste, standard=False):
        a.beobachtungsliste = "dazu"
    a.bewerten = True
    return a


def _beobachtung_moeglich(paths: Paths) -> bool:
    from stockagent.titelliste import Merkliste

    return bool(Merkliste(paths.root).sterne())


# ------------------------------------------------------------------ Optionen


def _kategorie(wert: str, vok: anf.Vokabular) -> dict[str, Any]:
    """`--category` aus SPEC 9.6: sector:<Branche>, region:<Region>, land:<ISO>, stil:<Stil>,
    titel:<ISIN>, markt. Branche und Region auch mit englischen Namen (health_care, europe)."""
    art, _, inhalt = wert.partition(":")
    art = art.strip().lower()
    inhalt = inhalt.replace("_", " ").strip()
    if art == "markt" or art == "market":
        return {}
    if art in ("titel", "isin"):
        return {"isins": [inhalt.upper()]}
    if art in ("land", "country"):
        return {"laender": [inhalt.upper()]}
    v = anf.wortliste(inhalt, vok)
    a = v.anfrage
    if art in ("sector", "branche"):
        ids = {inhalt.replace(" ", "_")} & (set(vok.haupt) | set(vok.unter))
        if ids:
            bid = ids.pop()
            return {"hauptbranchen": [bid]} if bid in vok.haupt else {"unterbranchen": [bid]}
        if a.hauptbranchen or a.unterbranchen:
            return {"hauptbranchen": a.hauptbranchen, "unterbranchen": a.unterbranchen}
    elif art == "region":
        if inhalt.replace(" ", "_") in vok.regionen:
            return {"region": inhalt.replace(" ", "_")}
        if a.region or a.laender:
            return {"region": a.region, "laender": a.laender}
    elif art in ("stil", "style"):
        if inhalt in vok.stile:
            return {"stile": [inhalt]}
        if a.stile:
            return {"stile": a.stile}
    raise typer.BadParameter(f"Kategorie „{wert}“ nicht in den Listen (config/vokabular.yaml)")


def _liste(x: str | None) -> list[str]:
    return [s.strip() for s in (x or "").split(",") if s.strip()]


def zeige_plan(plan: lauf.Plan) -> None:
    t = Table(title=f"Laufplan {plan.lauf_id}", show_header=False)
    t.add_row("Anfrage", "; ".join(f"{a}: {b}" for a, b in plan.beschreibung) or "ganzes Universum")
    t.add_row("Auswahl", f"{plan.auswahl} Titel, davon {plan.aktuell_bewertet} mit aktueller Note")
    t.add_row(
        "Bewerten (ohne Modell)",
        f"{len(plan.zu_bewerten)} Titel"
        + (
            f" von {plan.zu_bewerten_gesamt}"
            if plan.zu_bewerten_gesamt > len(plan.zu_bewerten)
            else ""
        ),
    )
    t.add_row(
        "Tiefenanalysen",
        f"{plan.tief_anzahl} (Tiefe sieht {plan.tief_vorgesehen} vor, Grenze {plan.tief_grenze})",
    )
    if plan.tief_vorschau:
        t.add_row("Derzeit beste", ", ".join(plan.tief_vorschau))
    t.add_row("Geschätzte Dauer", f"{plan.dauer_minuten or '?'} Minuten")
    t.add_row("Claude Code", "gefunden" if plan.claude else "nicht gefunden")
    console.print(t)
    for h in plan.hinweise:
        console.print(f"- {h}")


@app.command()
def run(
    text: Annotated[
        str | None, typer.Option("--text", "-t", help="Anfrage in eigenen Worten.")
    ] = None,
    category: Annotated[
        str | None,
        typer.Option(
            "--category",
            help="sector:<Branche>, region:<Region>, land:<ISO>, "
            "stil:<Stil>, titel:<ISIN> oder markt.",
        ),
    ] = None,
    branche: Annotated[
        str | None,
        typer.Option("--branche", help="Haupt- oder Unterbranchen (IDs), etwa gesundheit,pharma."),
    ] = None,
    region: Annotated[str | None, typer.Option("--region", help="Region, etwa europa.")] = None,
    land: Annotated[str | None, typer.Option("--land", help="Länder (ISO), etwa DE,AT.")] = None,
    size: Annotated[
        str | None, typer.Option("--size", help="Größenklassen, etwa small,mid.")
    ] = None,
    tier: Annotated[str | None, typer.Option("--tier", help="Indexstufen, etwa 1,2.")] = None,
    note: Annotated[str | None, typer.Option("--note", help="Noten, etwa A,B.")] = None,
    stil: Annotated[str | None, typer.Option("--stil", help="Anlagestil, etwa qualitaet.")] = None,
    horizont: Annotated[
        str | None, typer.Option("--horizont", help="Anlagehorizont kurz, mittel oder lang.")
    ] = None,
    depth: Annotated[
        str | None, typer.Option("--depth", "--tiefe", help="schnell, standard oder tief.")
    ] = None,
    nur_handelbar: Annotated[
        bool, typer.Option("--nur-handelbar", help="Nur von Luca als handelbar geprüfte.")
    ] = False,
    beobachtungsliste: Annotated[
        str | None, typer.Option("--beobachtungsliste", help="nein, nur oder dazu.")
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Profil aus config/run_profiles.yaml.")
    ] = None,
    ansicht: Annotated[
        str | None, typer.Option("--ansicht", help="Gespeicherte Ansicht aus state/views.yaml.")
    ] = None,
    budget_eur: Annotated[
        float | None,
        typer.Option("--budget-eur", help="Kostengrenze, nur im API-Betrieb (Bauschritt 12)."),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Ohne Bestätigung starten.")] = False,
    nur_plan: Annotated[
        bool, typer.Option("--nur-plan", help="Nur den Laufplan zeigen, nichts starten.")
    ] = False,
    tiefenanalyse: Annotated[
        str,
        typer.Option(
            "--tiefenanalyse",
            help="nacheinander (wartet auf jede), warteschlange (Dashboard arbeitet ab) oder "
            "liste (nur nennen, etwa für /stockagent).",
        ),
    ] = "nacheinander",
    als_json: Annotated[bool, typer.Option("--json", help="Plan und Ergebnis als JSON.")] = False,
) -> None:
    """Lauf über eine Kategorie: Laufplan, Noten für alle Treffer, Tiefenanalyse der besten."""
    paths = Paths.default()
    connect(paths).close()
    vok = anf.Vokabular.laden(paths)
    daten = Daten(paths)
    if tiefenanalyse not in ("nacheinander", "warteschlange", "liste"):
        raise typer.BadParameter("--tiefenanalyse: nacheinander, warteschlange oder liste")

    optionen: dict[str, Any] = {}
    weg = "optionen"
    if profile:
        p = lauf.konfig(paths)["profile"].get(profile)
        if p is None:
            raise typer.BadParameter(f"Profil {profile} fehlt in config/run_profiles.yaml")
        if p.get("aktiv") is False:
            raise typer.BadParameter(f"Profil {profile} ist aus ({p.get('beschreibung')})")
        if p.get("zeitplan"):
            # Lauf nach Zeitplan: keine Rückfragen, eigener Ablauf (Bauschritt 12, ADR 0015)
            from stockagent import zeitplan

            try:
                zerg = zeitplan.ausfuehren(paths, melde=typer.echo)
            except zeitplan.ZeitplanFehler as exc:
                typer.echo(str(exc))
                raise typer.Exit(code=1) from exc
            typer.echo(
                f"Fertig: {zerg.bewertet} bewertet, {len(zerg.ereignisse)} Ereignisse. "
                f"Laufübersicht: runs/_laeufe/{zerg.lauf_id}/report.md"
            )
            return
        optionen.update({k: v for k, v in p.items() if k not in ("beschreibung", "aktiv")})
        weg = "profil"
    if ansicht:
        f = anf.ansicht(paths, ansicht)
        if f is None:
            raise typer.BadParameter(f"Ansicht {ansicht} fehlt in state/views.yaml")
        optionen.update(
            anf.aus_filter(f, vok).model_dump(exclude={"text", "weg"}, exclude_defaults=True)
        )
        weg = "ansicht"
    if text:
        v = anf.uebersetzen(text, vok, modell=anf.claude_modell(vok))
        if not v.ok:
            typer.echo("Abgelehnt: " + "; ".join(v.abgelehnt))
            raise typer.Exit(code=1)
        for h in v.hinweise:
            typer.echo(h)
        optionen.update(v.anfrage.model_dump(exclude={"weg"}, exclude_defaults=True))
        weg = v.anfrage.weg
    if category:
        optionen.update(_kategorie(category, vok))
    if branche:
        ids = _liste(branche)
        optionen["hauptbranchen"] = [b for b in ids if b in vok.haupt]
        optionen["unterbranchen"] = [b for b in ids if b not in vok.haupt]
    if region:
        optionen.update(_kategorie(f"region:{region}", vok))
    if land:
        optionen["laender"] = [x.upper() for x in _liste(land)]
    if size:
        optionen["groessen"] = [g for s in _liste(size) for g in GROESSEN_ALIAS.get(s, [s])]
    if tier:
        optionen["stufen"] = [int(s) for s in _liste(tier) if s.isdigit()]
    if note:
        optionen["noten"] = [n.upper() for n in _liste(note)]
    if stil:
        optionen["stile"] = _liste(stil)
    if horizont:
        optionen["horizont"] = horizont
    if depth:
        optionen["tiefe"] = TIEFE_ALIAS.get(depth, depth)
    if nur_handelbar:
        optionen["handelbarkeit"] = "bestaetigt"
    if beobachtungsliste:
        optionen["beobachtungsliste"] = beobachtungsliste

    if optionen:
        try:
            a = anf.Anfrage(
                weg=weg,
                bewerten=True,
                **{k: v for k, v in optionen.items() if k not in ("weg", "bewerten")},
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    elif sys.stdin.isatty():
        a = dialog(paths, vok, daten, Questionary(), anf.claude_modell(vok))
    else:
        typer.echo("Ohne Terminal keine Rückfragen: Optionen, --text oder --profile angeben.")
        raise typer.Exit(code=2)
    fehler = anf.pruefen(a, vok)
    if fehler:
        typer.echo("Abgelehnt: " + "; ".join(fehler))
        raise typer.Exit(code=1)

    plan = lauf.planen(paths, daten, a, vok)
    if budget_eur is not None:
        plan.hinweise.append(
            f"--budget-eur {budget_eur}: wirkt nur im API-Betrieb (Bauschritt 12). Über das Abo "
            "begrenzt die Anzahl der Tiefenanalysen (HR-18)."
        )
    if als_json and nur_plan:
        typer.echo(json.dumps(asdict(plan), ensure_ascii=False, indent=1))
        return
    zeige_plan(plan)
    if nur_plan:
        return
    if not yes and not typer.confirm("Lauf starten?", default=False):
        typer.echo("Nicht gestartet.")
        raise typer.Exit(code=0)
    tief = {
        "nacheinander": lauf.tief_nacheinander(paths),
        "warteschlange": lauf.in_warteschlange(paths),
        "liste": None,
    }[tiefenanalyse]
    erg = lauf.ausfuehren(paths, plan, daten, vok, tief=tief, melde=typer.echo)
    if als_json:
        typer.echo(
            json.dumps(
                {k: v for k, v in asdict(erg).items() if k != "rangliste"},
                ensure_ascii=False,
                indent=1,
            )
        )
        return
    typer.echo(f"Fertig: {len(erg.bewertet)} bewertet, {len(erg.fehler)} Fehler.")
    for isin, s in erg.tiefenanalysen.items():
        typer.echo(f"  Tiefenanalyse {isin}: {s.get('status')}")
    typer.echo(f"Laufübersicht: {erg.ordner}/report.md")


@app.command("anfrage")
def anfrage_cmd(
    text: str = typer.Argument(..., help="Anfrage in eigenen Worten."),
    ohne_modell: Annotated[
        bool, typer.Option("--ohne-modell", help="Nur die Wortliste, kein claude -p.")
    ] = False,
    als_json: Annotated[bool, typer.Option("--json", help="Ausgabe als JSON.")] = False,
) -> None:
    """Satz in Filter übersetzen und die Trefferzahl zeigen (SPEC 9.9), ohne Lauf."""
    paths = Paths.default()
    connect(paths).close()
    vok = anf.Vokabular.laden(paths)
    daten = Daten(paths)

    def namens_treffer(q: str) -> int:
        return sum(1 for z in daten.zeilen if passt(z, {"q": q}, daten.stile))

    v = anf.uebersetzen(
        text,
        vok,
        namens_treffer=namens_treffer,
        modell=None if ohne_modell else anf.claude_modell(vok),
    )
    from stockagent.titelliste import liste, lockerungen

    f = anf.als_filter(v.anfrage, vok)
    anzahl = liste(daten, f)["anzahl"] if v.ok else 0
    vorschlag = lockerungen(daten, f)[:1] if v.ok and not anzahl else []
    if als_json:
        typer.echo(
            json.dumps(
                {
                    "ok": v.ok,
                    "abgelehnt": v.abgelehnt,
                    "hinweise": v.hinweise,
                    "anfrage": v.anfrage.model_dump(),
                    "filter": f,
                    "anzahl": anzahl,
                    "vorschlag": vorschlag[0] if vorschlag else None,
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        raise typer.Exit(code=0 if v.ok else 1)
    if not v.ok:
        typer.echo("Abgelehnt: " + "; ".join(v.abgelehnt))
        raise typer.Exit(code=1)
    typer.echo(f"Verstanden über {v.anfrage.weg}:")
    for art, t in anf.beschreibung(v.anfrage, vok) or [("", "ganzes Universum")]:
        typer.echo(f"  {art}: {t}" if art else f"  {t}")
    for h in v.hinweise:
        typer.echo(f"  Hinweis: {h}")
    typer.echo(f"{anzahl} Treffer")
    if vorschlag:
        typer.echo(f"Vorschlag: {vorschlag[0]['text']} ergibt {vorschlag[0]['anzahl']} Treffer")
