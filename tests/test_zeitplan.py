"""Bauschritt 12: Lauf nach Zeitplan (SPEC 9.1, 9.2, 13.4, 16.14, ADR 0015).

Abnahme laut BAUPLAN: drei Läufe hintereinander ohne manuellen Eingriff. Netz, GitHub und
Benachrichtigung sind durch Attrappen ersetzt.
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from stockagent import benachrichtigung, bewertung, eskalation_issues, eskalationen, zeitplan
from stockagent.cli import app
from stockagent.data import store
from stockagent.paths import Paths
from stockagent.titelliste import Daten, Merkliste
from tests.sec_fixtures import ROOT
from tests.test_bewertung import FIRMEN, NOW, Attrappe, _seed

BEOBACHTET = [FIRMEN[-1][0], FIRMEN[-2][0]]
ISSUER = "sec:" + FIRMEN[-1][1]


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    shutil.copytree(ROOT / "config", tmp_path / "config")
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs/METHODOLOGY_CHANGELOG.md", tmp_path / "docs")
    p = Paths(tmp_path)
    _seed(p)
    m = Merkliste(p.root)
    for isin in BEOBACHTET:
        m.stern(isin, True)
    return p


class Gh:
    """Attrappe für `gh`: ein Repository von luca, Issues mit Kommentaren."""

    def __init__(self) -> None:
        self.aufrufe: list[list[str]] = []
        self.kommentare: dict[int, list[dict[str, Any]]] = {}

    def __call__(self, args: list[str]) -> str:
        self.aufrufe.append(args)
        if args[:2] == ["repo", "view"]:
            return json.dumps({"owner": {"login": "luca"}})
        if args[:2] == ["issue", "create"]:
            return "https://github.com/luca/Stock-Agent/issues/7\n"
        if args[:2] == ["issue", "view"]:
            return json.dumps({"state": "OPEN", "comments": self.kommentare.get(int(args[2]), [])})
        return ""


def _lader(gesendet: list[tuple[str, str]], gh: Gh | None = None, **kw: Any) -> zeitplan.Lader:
    def sender_fuer(kanal: str, env: Any) -> benachrichtigung.Sender:
        return lambda betreff, text: gesendet.append((kanal, betreff))

    werte: dict[str, Any] = {
        "universum": lambda p: "aktuell genug",
        "bewerten": lambda p, i: bewertung.bewerten(p, i, lader=Attrappe().lader(), now=NOW),
        "gh": gh or Gh(),
        "sender_fuer": sender_fuer,
        "env": {},
    }
    return zeitplan.Lader(**{**werte, **kw})


def test_schedule_is_off_by_default(paths: Paths) -> None:
    with pytest.raises(zeitplan.ZeitplanFehler, match="Zeitplan ist aus"):
        zeitplan.ausfuehren(paths, lader=_lader([]))


def test_three_runs_in_a_row_without_intervention(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Abnahme: drei Läufe nacheinander. Lauf 1 ist der Ausgangsstand, in Lauf 2 erscheint ein
    neuer Bericht und ein Restatement bei einem beobachteten Titel, Lauf 3 wiederholt die schon
    gemeldeten Ereignisse nicht."""
    zeitplan.schalten(paths, True)
    gesendet: list[tuple[str, str]] = []
    neu: dict[str, Any] = {"berichte": [], "restatements": []}
    monkeypatch.setattr(store, "berichte_seit", lambda conn, seit, limit=200: neu["berichte"])
    monkeypatch.setattr(store, "restatements_seit", lambda conn, seit: neu["restatements"])

    tage = [NOW + timedelta(days=d) for d in (1, 2, 3)]
    erg1 = zeitplan.ausfuehren(paths, lader=_lader(gesendet), now=tage[0])
    assert erg1.bewertet == 2 and erg1.ereignisse == [] and not erg1.fehler
    assert any("Erster Lauf" in h for h in erg1.hinweise)

    bericht_tag = (tage[0] + timedelta(hours=3)).replace(tzinfo=None)
    neu["berichte"] = [(ISSUER, bericht_tag, "10-Q")]
    neu["restatements"] = [(ISSUER, 4, bericht_tag)]
    erg2 = zeitplan.ausfuehren(paths, lader=_lader(gesendet), now=tage[1])
    arten = sorted(e["art"] for e in erg2.ereignisse)
    assert arten == ["Neuer Bericht", "Restatement"]
    assert {e["isin"] for e in erg2.ereignisse} == {FIRMEN[-1][0]}

    erg3 = zeitplan.ausfuehren(paths, lader=_lader(gesendet), now=tage[2])
    assert erg3.ereignisse == []  # schon gemeldet, nicht wiederholt

    # Ablage je Lauf, Benachrichtigung je Lauf, Stand fortgeschrieben, keine Sperre übrig
    for erg in (erg1, erg2, erg3):
        ordner = paths.runs / "_laeufe" / erg.lauf_id
        assert (ordner / "request.json").exists() and (ordner / "nachricht.txt").exists()
        assert "## Ereignisse seit dem letzten Lauf" in (ordner / "report.md").read_text()
        assert erg.benachrichtigung == {"datei": "gesendet", "macos": "gesendet"}
    assert [k for k, _ in gesendet] == ["macos"] * 3
    assert "2 Ereignisse" in gesendet[1][1]
    s = zeitplan.stand(paths)
    assert s["letzter_lauf"] == tage[2].isoformat(timespec="seconds")
    assert not (paths.runs / "_laeufe" / "zeitplan.lock").exists()
    # Markierung am Titel und im Dashboard
    marken = zeitplan.markierungen(paths)[FIRMEN[-1][0]]
    assert {m["art"] for m in marken} == {"Neuer Bericht", "Restatement"}
    zeile = next(z for z in Daten(paths).zeilen if z.isin == FIRMEN[-1][0])
    assert "Restatement" in zeile.ereignis or "Neuer Bericht" in zeile.ereignis
    # Läufe nach Zeitplan überschreiben Lucas letzte Anfrage nicht
    assert not (paths.root / "state" / "last_request.yaml").exists()


def test_event_titles_get_deep_analysis_only_with_depth_in_profile(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = yaml.safe_load((paths.config / "run_profiles.yaml").read_text())
    cfg["profile"]["scheduled"]["tiefe"] = "standard"
    (paths.config / "run_profiles.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    zeitplan.schalten(paths, True)
    zeitplan.ausfuehren(paths, lader=_lader([]), now=NOW + timedelta(days=1))
    tag = (NOW + timedelta(days=1, hours=2)).replace(tzinfo=None)
    bericht = [(ISSUER, tag, "10-K")]
    monkeypatch.setattr(store, "berichte_seit", lambda conn, seit, limit=200: bericht)
    gestartet: list[str] = []

    def tief(p: Paths, art: str) -> Any:
        assert art == "warteschlange"
        return lambda isin: gestartet.append(isin) or {"status": "wartet"}

    erg = zeitplan.ausfuehren(paths, lader=_lader([], tief=tief), now=NOW + timedelta(days=2))
    assert gestartet == [FIRMEN[-1][0]] and erg.tiefenanalysen[FIRMEN[-1][0]]["status"] == "wartet"


def test_lock_prevents_parallel_runs_and_stale_lock_is_removed(paths: Paths) -> None:
    zeitplan.schalten(paths, True)
    sperre = paths.runs / "_laeufe" / "zeitplan.lock"
    sperre.parent.mkdir(parents=True)
    sperre.write_text(str(os.getpid()))
    with pytest.raises(zeitplan.ZeitplanFehler, match="läuft schon"):
        zeitplan.ausfuehren(paths, lader=_lader([]), now=NOW)
    sperre.write_text("999999999")  # Prozess gibt es nicht mehr
    assert zeitplan.ausfuehren(paths, lader=_lader([]), now=NOW).bewertet == 2


def test_universe_failure_does_not_stop_the_run(paths: Paths) -> None:
    zeitplan.schalten(paths, True)

    def kaputt(p: Paths) -> str:
        raise OSError("keine Verbindung")

    erg = zeitplan.ausfuehren(paths, lader=_lader([], universum=kaputt), now=NOW)
    assert erg.bewertet == 2 and "keine Verbindung" in erg.universum


def test_notification_channels_and_missing_secrets(tmp_path: Path) -> None:
    def kaputt(kanal: str, env: Any) -> benachrichtigung.Sender:
        return benachrichtigung.sender(kanal, env)

    erg = benachrichtigung.senden(
        tmp_path, "Betreff", "Text", ["datei", "telegram", "smtp"], env={}, sender_fuer=kaputt
    )
    assert erg["datei"] == "gesendet"
    assert "TELEGRAM_BOT_TOKEN" in erg["telegram"] and "SMTP_HOST" in erg["smtp"]
    assert (tmp_path / "nachricht.txt").read_text().startswith("Betreff")
    with pytest.raises(ValueError):
        benachrichtigung.sender("fax", {})


def _fall(run_id: str = "2026-10-20T10-00-00Z_US0000000200") -> eskalationen.Fall:
    return eskalationen.Fall(
        run_id=run_id,
        isin="US0000000200",
        name="FIRMA 19",
        erstellt="2026-10-20T10:00:00+00:00",
        kategorie_vor_eskalation="Beobachten",
        streitpunkte=[
            eskalationen.Streitpunkt("J1", "Bruttomarge weicht ab", {"agent": "0.41", "j1": "0.38"})
        ],
    )


def test_escalations_become_issues_and_owner_comments_decide(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    fall = _fall()
    offen = [fall]
    entschieden: list[tuple[str, str, str]] = []
    monkeypatch.setattr(eskalationen, "faelle", lambda p, alle=False: list(offen))

    def entscheiden(p: Paths, run_id: str, e: str, notiz: str, **kw: Any) -> dict[str, Any]:
        entschieden.append((run_id, e, notiz))
        offen.clear()
        return {}

    monkeypatch.setattr(eskalationen, "entscheiden", entscheiden)
    gh = Gh()
    erg = eskalation_issues.abgleichen(paths, gh)
    assert erg["angelegt"] == [fall.run_id]
    erstellt = next(a for a in gh.aufrufe if a[:2] == ["issue", "create"])
    text = erstellt[erstellt.index("--body") + 1]
    assert "Bruttomarge weicht ab" in text and '"j1": "0.38"' in text and "/entscheidung" in text
    assert eskalation_issues.zuordnung(paths)[fall.run_id]["nummer"] == 7

    # Kein zweites Issue für denselben Fall, Kommentar eines anderen wird ignoriert
    gh.kommentare[7] = [
        {"id": "k1", "author": {"login": "fremd"}, "body": "/entscheidung annehmen hack"},
        {"id": "k2", "author": {"login": "luca"}, "body": "/entscheidung neu-pruefen Seite 41"},
    ]
    erg = eskalation_issues.abgleichen(paths, gh)
    assert erg["angelegt"] == [] and erg["neu_pruefen"] == [fall.run_id] and entschieden == []
    assert eskalation_issues.zuordnung(paths)[fall.run_id]["neu_pruefen"] == "Seite 41"

    gh.kommentare[7].append(
        {"id": "k3", "author": {"login": "luca"}, "body": "Ok.\n/entscheidung annehmen Zitat passt"}
    )
    erg = eskalation_issues.abgleichen(paths, gh)
    assert entschieden == [(fall.run_id, "freigeben", "GitHub #7: Zitat passt")]
    assert gh.aufrufe[-1][:3] == ["issue", "close", "7"]
    assert eskalation_issues.zuordnung(paths)[fall.run_id]["status"] == "geschlossen"


def test_launchd_plist_runs_the_scheduled_profile(paths: Paths) -> None:
    d = plistlib.loads(zeitplan.launchd_plist(paths, "07:30", uv="/opt/homebrew/bin/uv"))
    assert d["ProgramArguments"] == [
        "/opt/homebrew/bin/uv",
        "run",
        "--directory",
        str(paths.root),
        "stockagent",
        "run",
        "--profile",
        "scheduled",
        "--yes",
    ]
    assert d["StartCalendarInterval"] == {"Hour": 7, "Minute": 30}


def test_cli_schedule_switch_and_run_profile(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKAGENT_HOME", str(paths.root))
    runner = CliRunner()
    r = runner.invoke(app, ["run", "--profile", "scheduled", "--yes"])
    assert r.exit_code == 1 and "Zeitplan ist aus" in r.output
    assert runner.invoke(app, ["zeitplan", "an"]).exit_code == 0
    r = runner.invoke(app, ["zeitplan", "status"])
    assert "Zeitplan: an" in r.output and "Letzter Lauf: noch keiner" in r.output
    ohne_netz = _lader([])  # kein Netz, kein gh, keine Mitteilung
    original = zeitplan.ausfuehren
    monkeypatch.setattr(
        zeitplan, "ausfuehren", lambda p, **kw: original(p, **{**kw, "lader": ohne_netz})
    )
    r = runner.invoke(app, ["run", "--profile", "scheduled", "--yes"])
    assert r.exit_code == 0, r.output
    assert "Fertig: 2 bewertet" in r.output
    assert datetime.fromisoformat(zeitplan.stand(paths)["letzter_lauf"]).tzinfo == UTC
