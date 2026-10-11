"""Formelregister (SPEC 12.2, HR-06).

Jede Kennzahl aus `config/metrics.yaml` hat genau eine hier registrierte Funktion. Die
Kennzahlen selbst kommen in Schritt 3 dazu.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

MetricFn = Callable[..., Any]

_REGISTRY: dict[str, MetricFn] = {}


def metric(metric_id: str) -> Callable[[MetricFn], MetricFn]:
    def register(fn: MetricFn) -> MetricFn:
        if metric_id in _REGISTRY:
            raise ValueError(f"Kennzahl doppelt registriert: {metric_id}")
        _REGISTRY[metric_id] = fn
        return fn

    return register


def get(metric_id: str) -> MetricFn:
    return _REGISTRY[metric_id]


def ids() -> set[str]:
    return set(_REGISTRY)
