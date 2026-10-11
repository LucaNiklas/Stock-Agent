"""Beleg-Gate (HR-02): Claims ohne Beleg werden nach `removed_claims` verschoben."""

from __future__ import annotations

from stockagent.gates import GateResult
from stockagent.schemas.base import AgentOutput, Claim, RemovedClaim


def apply(output: AgentOutput) -> tuple[AgentOutput, GateResult]:
    result = GateResult("evidence")
    keep: list[Claim] = []
    removed = list(output.removed_claims)
    for claim in output.claims:
        if claim.evidence:
            keep.append(claim)
        else:
            removed.append(RemovedClaim(claim=claim, reason="kein Beleg"))
            result.errors.append(f"{claim.claim_id}: ohne Beleg entfernt")
    return output.model_copy(update={"claims": keep, "removed_claims": removed}), result
