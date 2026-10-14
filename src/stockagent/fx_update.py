"""Wechselkurse der EZB laden (Bauschritt 4, Abteilung Recherche, SPEC 5.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import yaml

from stockagent.core import dq
from stockagent.data import store
from stockagent.data.http import fetch
from stockagent.data.sources import fx
from stockagent.paths import Paths


@dataclass
class FxErgebnis:
    neu: int
    bis: date | None
    uebersprungen: bool = False


def update(
    paths: Paths,
    *,
    refresh: bool = False,
    fetcher: Callable[..., bytes] = fetch,
    now: datetime | None = None,
) -> FxErgebnis:
    """Beim ersten Mal und mit `refresh` alle Kurse ab `start`, sonst ab dem letzten Kurstag."""
    now = now or datetime.now(UTC)
    cfg = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))
    ecb = cfg["ecb"]
    conn = store.connect(paths.db)
    try:
        letzter = store.last_fx(conn)
        if (
            letzter
            and not refresh
            and dq.juenger_als(letzter[1].date(), now.date(), int(ecb["aktuell_tage"]))
        ):
            return FxErgebnis(0, letzter[0], uebersprungen=True)
        # Mit --refresh alles neu ab `start`, etwa nach einem abgebrochenen ersten Abruf
        start = letzter[0] if letzter and not refresh else date.fromisoformat(str(ecb["start"]))
        client = fx.EcbClient(ecb, cfg["user_agent"], paths.raw, fetcher=fetcher, now=lambda: now)
        abruf = client.kurse(list(ecb["waehrungen"]), start)
        store.save_fx(
            conn,
            [(k.datum, k.waehrung, k.je_eur) for k in abruf.kurse],
            abruf.raw.sha256,
            now,
        )
        bis = max((k.datum for k in abruf.kurse), default=letzter[0] if letzter else None)
        return FxErgebnis(len(abruf.kurse), bis)
    finally:
        conn.close()
