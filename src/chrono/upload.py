"""Envoi des mesures au serveur.

L'envoi n'a jamais lieu tout seul. Il faut l'adresse d'un serveur pour qu'un lot
parte, et sans elle le logiciel se contente de mesurer et d'écrire ses résultats
en local. Transmettre les données de quelqu'un sans qu'il l'ait demandé serait
une décision prise à sa place, et le fait qu'elles soient anonymes n'y change
rien.

Il a lieu en fin de session et non au fil de l'eau : aucune requête réseau ne
part pendant que le joueur joue.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import requests

from .protocol import SessionPayload

_TIMEOUT: Final = 30
_USER_AGENT: Final = "chrono-bdo"


@dataclass(frozen=True)
class UploadResult:
    """Ce que le serveur a répondu, ou pourquoi il n'a rien répondu."""

    ok: bool
    detail: str
    stored: int = 0
    refused: int = 0


def save_session(payload: SessionPayload, path: Path) -> Path:
    """Écrit le lot sur le disque.

    Toujours, y compris quand l'envoi réussit. Une session mesurée puis perdue
    parce que le réseau a hoqueté serait irrattrapable : la partie, elle, ne se
    rejoue pas.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.to_json(), encoding="utf-8")
    return path


def send_session(payload: SessionPayload, url: str, timeout: int = _TIMEOUT) -> UploadResult:
    """Envoie un lot au serveur.

    Ne lève jamais. Un serveur injoignable ne doit pas faire disparaître le
    bilan d'une session sous une trace d'erreur : le joueur veut voir ses temps,
    que l'envoi ait abouti ou non. Le lot est de toute façon conservé sur le
    disque et pourra être renvoyé.
    """
    endpoint = url.rstrip("/") + "/v1/sessions"
    try:
        response = requests.post(
            endpoint,
            data=payload.to_json().encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
            timeout=timeout,
        )
    except requests.RequestException as error:
        return UploadResult(ok=False, detail=f"serveur injoignable : {error}")

    if response.status_code >= 400:
        detail = response.text[:300]
        # Le serveur explique son refus dans un champ « detail ». S'il répond
        # autre chose, le texte brut fera l'affaire : un message approximatif
        # vaut mieux qu'une erreur d'analyse par-dessus une erreur d'envoi.
        with contextlib.suppress(ValueError, AttributeError):
            detail = str(response.json().get("detail", detail))
        return UploadResult(ok=False, detail=f"refusé ({response.status_code}) : {detail}")

    try:
        body = response.json()
    except ValueError:
        return UploadResult(ok=True, detail="accepté, réponse illisible")
    return UploadResult(
        ok=True,
        detail="accepté",
        stored=int(body.get("enregistrees", 0)),
        refused=int(body.get("refusees", 0)),
    )
