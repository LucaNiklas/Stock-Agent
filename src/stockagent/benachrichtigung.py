"""Benachrichtigung nach einem Lauf (SPEC 13.4, ADR 0015).

Kurze Nachricht mit Anzahl attraktiver Unternehmen, Ereignissen, Eskalationen und Link zum
Dashboard. Kanäle aus `config/run_profiles.yaml` (`zeitplan.benachrichtigung.kanaele`):

- `datei`: immer, `runs/_laeufe/<lauf_id>/nachricht.txt`
- `macos`: Mitteilung auf diesem Mac über `osascript`
- `telegram`: Bot-Nachricht, Zugang nur über `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID`
- `smtp`: E-Mail, Zugang nur über `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORT`, `SMTP_AN`

Geheimnisse stehen nur in Umgebungsvariablen (`.env`), nie in `config/` oder im Code. Fehlt ein
Zugang oder scheitert ein Kanal, steht das im Ergebnis, der Lauf läuft weiter.
"""

from __future__ import annotations

import json
import os
import smtplib
import subprocess
import urllib.request
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from pathlib import Path
from typing import Any

Sender = Callable[[str, str], None]  # (Betreff, Text)


def _macos(betreff: str, text: str) -> None:
    def q(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    skript = f'display notification "{q(text[:240])}" with title "{q(betreff)}"'
    subprocess.run(["osascript", "-e", skript], check=True, capture_output=True, timeout=20)


def _telegram(env: Mapping[str, str]) -> Sender:
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise RuntimeError("TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlt")

    def senden(betreff: str, text: str) -> None:
        daten = json.dumps({"chat_id": chat, "text": f"{betreff}\n\n{text}"}).encode()
        anfrage = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=daten,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            antwort.read()

    return senden


def _smtp(env: Mapping[str, str]) -> Sender:
    noetig = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORT", "SMTP_AN")
    fehlt = [k for k in noetig if not env.get(k)]
    if fehlt:
        raise RuntimeError(f"{', '.join(fehlt)} fehlt")

    def senden(betreff: str, text: str) -> None:
        nachricht = EmailMessage()
        nachricht["Subject"] = betreff
        nachricht["From"] = env["SMTP_USER"]
        nachricht["To"] = env["SMTP_AN"]
        nachricht.set_content(text)
        with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT") or 587), timeout=30) as s:
            s.starttls()
            s.login(env["SMTP_USER"], env["SMTP_PASSWORT"])
            s.send_message(nachricht)

    return senden


def sender(kanal: str, env: Mapping[str, str]) -> Sender:
    if kanal == "macos":
        return _macos
    if kanal == "telegram":
        return _telegram(env)
    if kanal == "smtp":
        return _smtp(env)
    raise ValueError(f"Unbekannter Kanal {kanal}")


def senden(
    ordner: Path,
    betreff: str,
    text: str,
    kanaele: list[str],
    *,
    env: Mapping[str, str] | None = None,
    sender_fuer: Callable[[str, Mapping[str, str]], Sender] = sender,
) -> dict[str, Any]:
    """Nachricht über alle Kanäle. Zurück je Kanal `gesendet` oder der Grund des Fehlers."""
    env = os.environ if env is None else env
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "nachricht.txt").write_text(f"{betreff}\n\n{text}\n", "utf-8")
    ergebnis: dict[str, Any] = {"datei": "gesendet"}
    for kanal in kanaele:
        if kanal == "datei":
            continue
        try:
            sender_fuer(kanal, env)(betreff, text)
            ergebnis[kanal] = "gesendet"
        except Exception as exc:  # ein Kanal bricht den Lauf nicht ab (HR-16: steht im Bericht)
            ergebnis[kanal] = f"nicht gesendet: {str(exc)[:200]}"
    return ergebnis
