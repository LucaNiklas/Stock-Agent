"""Schranken, die jede Agentenausgabe in fester Reihenfolge durchläuft (SPEC 12.6)."""

from dataclasses import dataclass, field


@dataclass
class GateResult:
    gate: str
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors
