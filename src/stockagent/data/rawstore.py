"""Unveränderliche Ablage der Rohdaten (SPEC 7.6).

Jede Datei liegt komprimiert unter data/raw/<sha256>.gz, daneben <sha256>.json mit Quelle und
Abrufzeit. Der Hash bezieht sich auf den unkomprimierten Inhalt. Gleicher Inhalt wird nicht
doppelt abgelegt.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RawRef:
    sha256: str
    url: str
    retrieved_at: datetime
    size: int


def save(raw_dir: Path, content: bytes, url: str, retrieved_at: datetime) -> RawRef:
    sha = hashlib.sha256(content).hexdigest()
    raw_dir.mkdir(parents=True, exist_ok=True)
    data_path = raw_dir / f"{sha}.gz"
    meta_path = raw_dir / f"{sha}.json"
    if not data_path.exists():
        data_path.write_bytes(gzip.compress(content, mtime=0))
    if not meta_path.exists():
        meta = {
            "sha256": sha,
            "url": url,
            "retrieved_at": retrieved_at.isoformat(),
            "size": len(content),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return RawRef(sha, url, retrieved_at, len(content))


def prune(raw_dir: Path, url_prefixes: tuple[str, ...], keep: set[str]) -> list[str]:
    """Löscht Rohdateien, deren Quelle mit einem der Präfixe beginnt und die nicht in keep stehen.

    Nur für Hilfsdaten ohne Finanzwerte gedacht (GLEIF-Zuordnung und -Stammdaten, ADR 0001).
    Berichte und Abschlussdaten werden nie gelöscht (SPEC 7.6).
    """
    removed = []
    for meta_path in sorted(raw_dir.glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta["sha256"] in keep or not str(meta["url"]).startswith(url_prefixes):
            continue
        (raw_dir / f"{meta['sha256']}.gz").unlink(missing_ok=True)
        meta_path.unlink()
        removed.append(meta["sha256"])
    return removed


def load(raw_dir: Path, sha256: str) -> bytes:
    content = gzip.decompress((raw_dir / f"{sha256}.gz").read_bytes())
    if hashlib.sha256(content).hexdigest() != sha256:
        raise ValueError(f"Rohdatei {sha256} ist beschädigt")
    return content
