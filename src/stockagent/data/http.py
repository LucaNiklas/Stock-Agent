"""Höflicher HTTP-Abruf mit Wiederholungen (SPEC 8.6: 3 Versuche mit wachsender Pause)."""

from __future__ import annotations

import time
import urllib.error
import urllib.request


class FetchError(RuntimeError):
    pass


def fetch(url: str, user_agent: str, timeout: float = 120.0, attempts: int = 3) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data: bytes = response.read()
                return data
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(2 ** (attempt + 1))
    raise FetchError(f"{url} nicht erreichbar nach {attempts} Versuchen: {last}")
