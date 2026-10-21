"""Pfade relativ zum Projektordner (oder STOCKAGENT_HOME)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def default(cls) -> Paths:
        """STOCKAGENT_HOME, sonst der nächste Ordner aufwärts mit config/sources.yaml."""
        if home := os.environ.get("STOCKAGENT_HOME"):
            return cls(Path(home).resolve())
        start = Path.cwd().resolve()
        for folder in (start, *start.parents):
            if (folder / "config" / "sources.yaml").exists():
                return cls(folder)
        return cls(start)

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def db(self) -> Path:
        return self.root / "data" / "stockagent.duckdb"

    @property
    def views(self) -> Path:
        return self.root / "data" / "views"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def tr_checks(self) -> Path:
        return self.root / "state" / "tr_checks.yaml"
