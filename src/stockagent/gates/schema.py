"""Schema-Gate: Agentenausgabe gegen Pydantic-Modell validieren (SPEC 12.6, Schritt 1)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from stockagent.gates import GateResult


def check[M: BaseModel](raw: str | dict[str, Any], model: type[M]) -> tuple[M | None, GateResult]:
    result = GateResult("schema")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return model.model_validate(data), result
    except json.JSONDecodeError as exc:
        result.errors.append(f"kein gültiges JSON: {exc.msg} (Zeile {exc.lineno})")
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            result.errors.append(f"{loc}: {err['msg']}")
    return None, result
