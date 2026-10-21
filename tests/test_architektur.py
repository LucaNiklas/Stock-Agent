"""Architekturregeln, die sich statisch prüfen lassen.

HR-06: Arithmetik nur in `src/stockagent/core/`. Außerhalb von `core/` sind nur Rechenzeichen
erlaubt, die keine Finanzwerte berühren: Pfade (`ordner / "datei"`), Texte (`"a" + b`,
`"?" * n`), Zähler (`+= 1`) und die einzeln begründeten Fälle in `ERLAUBT`. Neue Rechenzeichen
außerhalb von `core/` lassen diesen Test scheitern. Dann gehört die Rechnung nach `core/`, oder
sie bekommt hier einen Eintrag mit Begründung.

HR-19: Jede Kennzahl im Register hat Pflicht-Prüfpunkte, mindestens CP-01 und CP-02.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from stockagent.core import registry

SRC = Path(__file__).resolve().parents[1] / "src" / "stockagent"
ROOT = SRC.parents[1]

# (Datei relativ zu src/stockagent, Ausdruck wie von ast.unparse) -> Begründung
ERLAUBT: dict[tuple[str, str], str] = {
    ("universe.py", "now - last"): "Zeitabstand seit dem letzten Abruf",
    ("sec_update.py", "start + block"): "Blockgrenzen beim Speichern",
    ("sec_update.py", "n % 100"): "Fortschrittsanzeige alle 100 Firmen",
    ("sec_update.py", "only - {i for v in by_cik.values() for i in v}"): "Mengendifferenz",
    ("sec_update.py", "now - timedelta(days=recheck_days)"): "Datum der Neuprüfung",
    (
        "sec_update.py",
        "now - timedelta(days=int(cfg['sec']['master_refresh_days']))",
    ): "Datum der Neuprüfung",
    ("sec_update.py", "len(to_query) // 250 + 1"): "Anzahl Blöcke für die Anzeige",
    ("sec_update.py", "len(to_query) // 250"): "Anzahl Blöcke für die Anzeige",
    ("cli/universe.py", "len(rows) - limit"): "Anzahl nicht angezeigter Zeilen",
    ("data/http.py", "attempts - 1"): "Wiederholungsversuche",
    ("data/http.py", "2 ** (attempt + 1)"): "Wartezeit zwischen Versuchen",
    ("data/http.py", "attempt + 1"): "Wiederholungsversuche",
    ("data/quality.py", "mindest + 1"): "Mindestanzahl Werte",
    ("data/sources/sec.py", "1.0 / per_second"): "Abstand zwischen Abrufen",
    ("data/sources/sec.py", "now + self._interval"): "Abstand zwischen Abrufen",
    ("data/sources/sec.py", "self._next - now"): "Abstand zwischen Abrufen",
    ("data/sources/gleif.py", "i + batch_size"): "Blockgrenzen beim Abruf",
    ("data/sources/openfigi.py", "60.0 / float(self.cfg['requests_per_minute'])"): "Abrufabstand",
    ("data/sources/openfigi.py", "i + size"): "Blockgrenzen beim Abruf",
    ("gates/number.py", "m.start() - 15"): "Textausschnitt um eine gefundene Zahl",
    ("gates/number.py", "m.end() + 15"): "Textausschnitt um eine gefundene Zahl",
    ("agents/render.py", "src_dir / PREAMBLE_FILE"): "Pfad",
    ("metrics_update.py", "config / name"): "Pfad",
    ("sec_update.py", "header + yaml.safe_dump(data, sort_keys=True)"): "Text",
    ("tr_checks.py", "header + yaml.safe_dump(body, sort_keys=False)"): "Text",
    ("prices_update.py", "header + yaml.safe_dump(data, sort_keys=True)"): "Text",
    ("bewertung.py", "config / name"): "Pfad",
    ("bewertung.py", "now.year - 1"): "letztes volles Kalenderjahr für den Umsatzabruf",
    (
        "bewertung.py",
        "int(cfg.scoring['vergleichsgruppe']['mindest']) - 1",
    ): "Mindestzahl der Vergleichstitel ohne die Firma selbst",
    ("dashboard/app.py", "s - {isin}"): "Mengendifferenz",
    ("data/sources/esef.py", "dt.date() - timedelta(days=1)"): "halboffenes Periodenende (Datum)",
    ("metrics_update.py", "config.parent / 'state' / name"): "Pfad",
    (
        "dashboard/app.py",
        "len(self.warteschlange()) - 1",
    ): "Anzahl Titel in der Warteschlange davor",
    ("dashboard/app.py", "self.paths.runs / letzter.run_id"): "Pfad",
    ("dashboard/app.py", "paths.runs / run_id"): "Pfad",
    ("agents/eingaben.py", "paths.config / name"): "Pfad",
    ("agents/eingaben.py", "paths.root / a.ausgabe"): "Pfad",
    ("agents/runner.py", "a + 15"): "höchstens 15 Jahre in einem Bereich",
    ("agents/runner.py", "b + 1"): "Textausschnitt bzw. Jahresbereich",
    ("data/dokumente.py", "m.end() + kontext"): "Textausschnitt um eine Fundstelle",
    ("data/dokumente.py", "m.start() - kontext"): "Textausschnitt um eine Fundstelle",
    (
        "orchestrator.py",
        "sum((1 for _ in (paths.runs / run_id / 'antworten').glob(f'{a.id}_*.txt'))) + 1",
    ): "laufende Nummer der Antwortdatei",
    ("orchestrator.py", "_ordner(paths, run_id) / ordner"): "Pfad",
    ("orchestrator.py", "a.nr + 1"): "Nummer des Folgeauftrags",
    ("orchestrator.py", "erlaubt + 1 - a.versuche"): "verbleibende Wiederholungen",
    ("orchestrator.py", "erlaubt + 1"): "verbleibende Wiederholungen",
    ("orchestrator.py", "g.seiten + 1"): "Seitennummern",
    ("orchestrator.py", "len(z.auftraege) + 2"): "Auftragsgrenze HR-18",
    (
        "orchestrator.py",
        "now - datetime.fromisoformat(a.beauftragt_um or z.erstellt)",
    ): "Dauer eines Auftrags",
    ("orchestrator.py", "now - datetime.fromisoformat(z.erstellt)"): "Zeitlimit des Laufs",
    ("orchestrator.py", "ordner / sub"): "Pfad",
    ("orchestrator.py", "paths.root / a.ausgabe"): "Pfad",
    ("orchestrator.py", "paths.root / a.eingabe"): "Pfad",
    ("orchestrator.py", "paths.runs / run_id"): "Pfad",
    ("orchestrator.py", "z.auftraege.index(a) + 1"): "Einfügestelle in der Auftragsliste",
    ("report/analyse.py", "paths.config / name"): "Pfad",
    ("report/analyse.py", "paths.root / a.ausgabe"): "Pfad",
    ("data/store.py", "set(isins) - offen"): "Mengendifferenz",
    ("data/store.py", "offen - set(isins)"): "Mengendifferenz",
    ("data/xlsx.py", "nummer * 26 + (ord(b) - 64)"): "Spaltenname einer Excel-Zelle in Nummer",
    ("data/xlsx.py", "nummer * 26"): "Spaltenname einer Excel-Zelle in Nummer",
    ("data/xlsx.py", "ord(b) - 64"): "Spaltenname einer Excel-Zelle in Nummer",
    ("data/xlsx.py", "nummer - 1"): "Spaltenname einer Excel-Zelle in Nummer",
    ("data/xlsx.py", "breite + 1"): "Anzahl Zellen einer Zeile",
    ("data/xlsx.py", "basis.toordinal() + tage"): "Excel-Datum in Kalenderdatum",
    ("data/sources/damodaran.py", "kopf + 1"): "Zeile nach der Kopfzeile",
    ("kapitalmarkt_update.py", "kopf + 1"): "Zeile nach der Kopfzeile",
    ("kapitalmarkt_update.py", "now.year + 1"): "Jahresdateien bis zum laufenden Jahr",
    ("kapitalmarkt_update.py", "[r[0] for r in rows] + ([bis] if bis else [])"): "Liste",
}
# Listen und Zähler, die mit += wachsen (keine Finanzwerte)
ERLAUBT_ANHAENGEN = {"sql", "params", "flags", "detail"}
VERBOTENE_AUFRUFE = {"round", "pow", "divmod", "fsum"}
VERBOTENE_MODULE = {"math", "statistics", "numpy", "scipy", "pandas"}


def _text(n: ast.expr) -> bool:
    return (isinstance(n, ast.Constant) and isinstance(n.value, str)) or isinstance(
        n, ast.JoinedStr
    )


def _harmlos(n: ast.BinOp | ast.AugAssign) -> bool:
    if isinstance(n, ast.AugAssign):
        ziel = n.target
        if isinstance(n.op, ast.Add) and isinstance(n.value, ast.Constant) and n.value.value == 1:
            return True  # Zähler
        if isinstance(ziel, ast.Name) and ziel.id in ERLAUBT_ANHAENGEN:
            return True
        if isinstance(n.op, ast.Add) and isinstance(n.value, (ast.List, ast.ListComp)):
            return True  # Liste verlängern
        if isinstance(n.op, ast.Add) and isinstance(n.value, ast.Call):
            return ast.unparse(n.value).startswith("len(")  # Zähler um eine Anzahl
        return False
    links, rechts = n.left, n.right
    if isinstance(n.op, ast.Div):
        return _text(rechts) or (isinstance(rechts, ast.Attribute) and rechts.attr == "name")
    if isinstance(n.op, ast.Add):
        return _text(links) or _text(rechts) or (isinstance(links, ast.BinOp) and _harmlos(links))
    if isinstance(n.op, ast.Mult):
        return _text(links) or _text(rechts) or isinstance(links, ast.List)
    return isinstance(n.op, (ast.BitOr, ast.BitAnd))


def _verstoesse() -> list[str]:
    out = []
    for datei in sorted(SRC.rglob("*.py")):
        rel = datei.relative_to(SRC).as_posix()
        if rel.startswith("core/"):
            continue
        for n in ast.walk(ast.parse(datei.read_text("utf-8"))):
            if isinstance(n, (ast.BinOp, ast.AugAssign)):
                ausdruck = ast.unparse(n)
                if not _harmlos(n) and (rel, ausdruck) not in ERLAUBT:
                    out.append(f"{rel}:{n.lineno}: {ausdruck}")
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id in VERBOTENE_AUFRUFE:
                    out.append(f"{rel}:{n.lineno}: {ast.unparse(n)}")
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                module = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module]
                if any(str(m).split(".")[0] in VERBOTENE_MODULE for m in module):
                    out.append(f"{rel}:{n.lineno}: import {module}")
    return out


def test_arithmetic_only_in_core() -> None:
    assert _verstoesse() == []


def test_allowlist_has_no_stale_entries() -> None:
    gefunden = set()
    for rel, ausdruck in ERLAUBT:
        baum = ast.parse((SRC / rel).read_text("utf-8"))
        if any(ast.unparse(n) == ausdruck for n in ast.walk(baum) if isinstance(n, ast.BinOp)):
            gefunden.add((rel, ausdruck))
    assert set(ERLAUBT) - gefunden == set()


def test_scanner_finds_financial_arithmetic(tmp_path: Path) -> None:
    beispiel = ast.parse("marge = ebit / umsatz\nsumme += wert\nx = round(y, 2)")
    knoten = [n for n in ast.walk(beispiel) if isinstance(n, (ast.BinOp, ast.AugAssign))]
    assert not any(_harmlos(n) for n in knoten)


def test_every_metric_has_checkpoints() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "metrics.yaml").read_text("utf-8"))
    for m in cfg["metrics"]:
        assert {"CP-01", "CP-02"} <= set(m["pruefpunkte"]), m["id"]
        assert m["id"] in registry.ids()
