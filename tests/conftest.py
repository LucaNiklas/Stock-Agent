from datetime import UTC, datetime
from typing import Any

import pytest

from stockagent.schemas import AgentOutput, Claim, Envelope, Evidence, SourceType


def make_claim(cid: str = "c-0001", text: str = "Die Marge stieg.", **kw: Any) -> Claim:
    data: dict[str, Any] = {
        "claim_id": cid,
        "text": text,
        "type": "qualitative",
        "evidence": [Evidence(source_type=SourceType.DOCUMENT_TEXT, doc_hash="sha256:ab", page=3)],
        "confidence_level": "mittel",
    }
    data.update(kw)
    return Claim(**data)


def make_output(*claims: Claim) -> AgentOutput:
    env = Envelope(
        run_id="test",
        agent_id="A3_fundamental",
        agent_version="0.1.0",
        prompt_hash="sha256:00",
        model_class="strong",
        model="opus",
        created_at=datetime(2026, 10, 11, tzinfo=UTC),
    )
    return AgentOutput(envelope=env, claims=list(claims))


@pytest.fixture
def claim_factory() -> Any:
    return make_claim


@pytest.fixture
def output_factory() -> Any:
    return make_output
