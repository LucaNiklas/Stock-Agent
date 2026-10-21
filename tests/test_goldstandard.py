"""Goldstandard (SPEC 11.6): Fälle stimmig, Fangquoten, Live-Lauf mit Attrappe, Kappa."""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from stockagent import goldstandard
from stockagent.core import goldstandard as gold_core
from stockagent.paths import Paths

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    for ordner in ("config", "eval/kandidaten"):
        shutil.copytree(ROOT / ordner, tmp_path / ordner)
    ziel = tmp_path / "src/stockagent/agents/prompts"
    ziel.mkdir(parents=True)
    shutil.copy(ROOT / "src/stockagent/agents/prompts/versions.yaml", ziel)
    return Paths(tmp_path)


def _satz(paths: Paths) -> goldstandard.Satz:
    return next(s for s in goldstandard.laden(paths.root) if s.herkunft == "kandidaten")


def test_candidate_cases_are_consistent(paths: Paths) -> None:
    """20 Fälle aus 5 Unternehmen, jedes Zitat wörtlich im Auszug, richtige Fälle gleich Gold."""
    satz = _satz(paths)
    assert len(satz.j1) + len(satz.j2) >= 20
    assert len({f.unternehmen for f in [*satz.j1, *satz.j2]}) == 5
    assert goldstandard.stimmigkeit(satz, paths) == []


def test_gold_value_hand_calculation(paths: Paths) -> None:
    # Apple Geschäftsjahr bis 27.09.2025: GrossProfit 195.201 Mio. USD durch Umsatz
    # 416.161 Mio. USD = 0,46905... (10-K, Meldung 0000320193-25-000079)
    fall = next(f for f in _satz(paths).j1 if f.id == "J1_APPLE_01")
    assert fall.eingaben["brutto"].accn == "0000320193-25-000079"
    g = goldstandard.goldwert(fall)
    assert g is not None and abs(g - Decimal("0.469051641")) < Decimal("1e-9")


def test_deterministic_j1_catches_injected_errors(paths: Paths) -> None:
    b = goldstandard.auswerten(paths, _satz(paths))
    assert b.bestanden
    assert b.quoten["J1 gesamt"]["quote"] == "1"
    # Periodenfehler mit 1,5 % Abweichung bleibt unter der Toleranz: J1 warnt nur (Rundung)
    grenz = next(e for e in b.ergebnisse if e.fehlerart == "falsche_periode_unter_toleranz")
    assert grenz.urteil == "rounding"
    assert any("J2 noch nie live gemessen" in h for h in b.hinweise)


def test_broken_case_is_reported(paths: Paths) -> None:
    datei = paths.root / "eval/kandidaten/faelle.yaml"
    d = yaml.safe_load(datei.read_text())
    d["j2"][0]["beleg"]["zitat"] = "this sentence is not in the excerpt"
    d["j1"][0]["behauptet"] = "0.5"
    datei.write_text(yaml.safe_dump(d, allow_unicode=True))
    fehler = goldstandard.stimmigkeit(_satz(paths), paths)
    assert any("Zitat steht nicht wörtlich" in f for f in fehler)
    assert any("richtiger Fall, Behauptung weicht" in f for f in fehler)


def test_gold_folder_only_takes_checked_cases(paths: Paths) -> None:
    (paths.root / "eval/gold").mkdir()
    shutil.copy(paths.root / "eval/kandidaten/faelle.yaml", paths.root / "eval/gold/x.yaml")
    with pytest.raises(ValueError, match="nur von Luca geprüfte"):
        goldstandard.laden(paths.root)


def test_live_j2_with_retry_and_recording(paths: Paths) -> None:
    """Erste Antwort mit Kennung plus Text wird wie im Lauf abgelehnt und berichtigt. Danach
    misst der Bericht aus der Aufzeichnung, bis die J2-Vorlage eine neue Version bekommt."""
    from datetime import UTC, datetime

    satz = _satz(paths)
    aufrufe: list[list[str]] = []

    def aufruf(befehl: list[str], cwd: Path) -> str:
        aufrufe.append(befehl)
        lauf = next(cwd.joinpath("eval", "laeufe").iterdir())
        aussagen = json.loads((lauf / "J2.json").read_text())["daten"]["aussagen"]
        nach_text = {f.aussage: f for f in satz.j2}
        urteile = [
            {
                "claim": a["kennung"] if aufrufe[1:] else f"{a['kennung']}: Kurzform",
                "urteil": nach_text[a["text"]].erwartet[-1],
                "begruendung": "Die Stelle sagt das.",
            }
            for a in aussagen
        ]
        antwort = {"auftrag": f"{lauf.name}/J2", "urteile": urteile}
        return json.dumps({"result": json.dumps(antwort), "session_id": "s-1"})

    now = datetime(2026, 10, 21, 12, tzinfo=UTC)
    urteile = goldstandard.j2_live(paths, satz.j2, aufruf=aufruf, now=now)
    assert len(aufrufe) == 2 and aufrufe[1][2].startswith("Antwort abgelehnt: Kennung k-001")
    assert "--resume" in aufrufe[1] and "s-1" in aufrufe[1]
    assert set(urteile) == {f.id for f in satz.j2} and None not in urteile.values()
    # Die Reihenfolge ist gemischt, die Herkunft bleibt verborgen
    lauf = next(paths.root.joinpath("eval", "laeufe").iterdir())
    texte = [a["text"] for a in json.loads((lauf / "J2.json").read_text())["daten"]["aussagen"]]
    assert texte != [f.aussage for f in satz.j2] and "J2_" not in (lauf / "J2.json").read_text()

    goldstandard.aufzeichnen(paths, urteile, "sonnet", now)
    b = goldstandard.auswerten(paths, satz)
    assert b.bestanden and b.quoten["J2 gesamt"]["quote"] == "1"
    assert b.quoten["J2 keiner"]["erkannt"] == 5  # keine Fehlalarme

    versionen = paths.root / "src/stockagent/agents/prompts/versions.yaml"
    versionen.write_text(
        versionen.read_text().replace('j2-belegpruefer: "1.0.0"', 'j2-belegpruefer: "1.1.0"')
    )
    b = goldstandard.auswerten(paths, satz)
    assert not b.bestanden and any("Live-Lauf nötig" in f for f in b.stimmigkeit)


def test_j2_quote_below_minimum_fails(paths: Paths) -> None:
    satz = _satz(paths)
    urteile = {f.id: "supported" for f in satz.j2}  # Prüfer winkt alles durch
    b = goldstandard.auswerten(paths, satz, j2_urteile=urteile)
    assert not b.bestanden and b.quoten["J2 gesamt"]["quote"] == "0"


def test_rates_and_kappa_hand_calculation() -> None:
    assert gold_core.quote(17, 20) == Decimal("0.85")
    assert gold_core.quote(0, 0) is None
    # 10 Paare: a=4 beide ja, d=4 beide nein, b=1, c=1. po = 0,8. pe = 0,5*0,5 + 0,5*0,5 = 0,5.
    # Kappa = (0,8 - 0,5) / (1 - 0,5) = 0,6
    paare = [(True, True)] * 4 + [(False, False)] * 4 + [(True, False), (False, True)]
    assert gold_core.kappa(paare) == Decimal("0.6")
    assert gold_core.kappa([(True, True)] * 3) is None  # ohne Streuung nicht definiert


def _prozess(stdout: str, code: int = 0) -> Any:
    import subprocess

    return subprocess.CompletedProcess([], code, stdout=stdout, stderr="Quota exceeded")


def test_gemini_j2_validates_schema_and_falls_back(paths: Paths, monkeypatch: Any) -> None:
    """Gemini bekommt Rolle, Auftrag und Seiten im Aufruf, ohne Werkzeuge. Ungültige Antwort,
    Fehler der CLI oder abgeschaltetes extern: GeminiNichtVerfuegbar, der Aufrufer fällt zurück."""
    from datetime import UTC, datetime

    from stockagent.agents.tools import gemini

    vorlage = paths.root / ".claude/agents/j2-belegpruefer.md"
    vorlage.parent.mkdir(parents=True)
    vorlage.write_text("---\nname: j2\n---\nDu bist Belegprüfer.")
    satz = _satz(paths)
    gesehen: list[str] = []

    def aufruf(befehl: list[str]) -> Any:
        prompt = befehl[2]
        gesehen.append(prompt)
        lauf = next(paths.root.joinpath("eval", "laeufe").iterdir())
        aussagen = json.loads((lauf / "J2.json").read_text())["daten"]["aussagen"]
        antwort = {
            "auftrag": f"{lauf.name}/J2",
            "urteile": [
                {"claim": a["kennung"], "urteil": "supported", "begruendung": "passt"}
                for a in aussagen
            ],
        }
        return _prozess(json.dumps({"response": "```json\n" + json.dumps(antwort) + "\n```"}))

    now = datetime(2026, 10, 21, 12, tzinfo=UTC)
    urteile = goldstandard.j2_gemini(
        paths, satz.j2, now=now, aufruf=aufruf, pruefe_verfuegbar=False
    )
    assert set(urteile.values()) == {"supported"}
    assert gesehen[0].startswith("Du bist Belegprüfer.") and "Monthly Dividend" in gesehen[0]
    assert "name: j2" not in gesehen[0]  # Kopf der Agent-Datei nicht im Prompt

    with pytest.raises(gemini.GeminiNichtVerfuegbar, match=r"extern\.aktiv ist aus"):
        goldstandard.j2_gemini(paths, satz.j2, now=now, aufruf=aufruf)
    with pytest.raises(gemini.GeminiNichtVerfuegbar, match="beendet mit 1"):
        goldstandard.j2_gemini(
            paths, satz.j2, now=now, aufruf=lambda b: _prozess("", 1), pruefe_verfuegbar=False
        )
    with pytest.raises(gemini.GeminiNichtVerfuegbar, match="ohne gültiges JSON"):
        goldstandard.j2_gemini(
            paths,
            satz.j2,
            now=now,
            aufruf=lambda b: _prozess(json.dumps({"response": "Ich kann das nicht."})),
            pruefe_verfuegbar=False,
        )
    monkeypatch.setattr(gemini.shutil, "which", lambda _: None)
    assert gemini.test()["ok"] is False
