"""Höflicher HTTP-Abruf mit Wiederholungen (SPEC 8.6: 3 Versuche mit wachsender Pause)."""

from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable


class FetchError(RuntimeError):
    pass


class NotFound(FetchError):
    """Die Quelle kennt die Adresse nicht (HTTP 404). Wird nicht wiederholt."""


# Längste Wartezeit bei Ratenbegrenzung (HTTP 429), falls die Quelle mehr verlangt.
_MAX_RATE_WAIT_S = 65.0


def fetch(
    url: str,
    user_agent: str,
    timeout: float = 120.0,
    attempts: int = 5,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """GET, mit `data` POST. 404 bricht sofort ab, 429 wartet auf die Freigabe der Quelle."""
    request = urllib.request.Request(
        url, data=data, headers={"User-Agent": user_agent, **(headers or {})}
    )
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFound(f"{url}: nicht gefunden (404)") from exc
            last = exc
            if attempt < attempts - 1:
                wait = float(2 ** (attempt + 1))
                if exc.code == 429:
                    hint = exc.headers.get("Retry-After") or exc.headers.get("ratelimit-reset")
                    wait = min(float(hint), _MAX_RATE_WAIT_S) if hint else _MAX_RATE_WAIT_S
                sleep(wait)
        except (
            urllib.error.URLError,
            TimeoutError,
            http.client.HTTPException,
            ConnectionError,
        ) as exc:
            # Abgebrochene Übertragung (IncompleteRead, RemoteDisconnected) und kurze Netzausfälle
            # wie DNS-Fehler: mit wachsender Pause neu versuchen (2, 4, 8, 16 Sekunden)
            last = exc
            if attempt < attempts - 1:
                sleep(2 ** (attempt + 1))
    raise FetchError(f"{url} nicht erreichbar nach {attempts} Versuchen: {last}")
