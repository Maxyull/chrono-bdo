"""Ce que le robot lit dans son environnement, et rien d'autre.

Le jeton de robot ne vit **que** dans une variable d'environnement. Ni dans le
dépôt, ni dans un fichier de configuration versionné, ni dans un argument de
ligne de commande, où il finirait dans l'historique du shell et dans la liste
des processus.

Son absence est l'état normal tant que l'application Discord n'existe pas. Elle
ne doit donc produire ni trace de pile, ni jeton vide envoyé à Discord qui
répondrait 401 sans expliquer pourquoi.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlparse

from .api import DEFAULT_BASE_URL, DEFAULT_TIMEOUT

#: Nom de la variable qui porte le jeton de robot, à générer sur le portail
#: développeur Discord, onglet Bot. C'est un nom de variable, pas un secret :
#: le secret, lui, n'apparaît nulle part dans ce dépôt.
TOKEN_VARIABLE: Final = "RUBIN_BOT_JETON"  # noqa: S105

#: Serveur Rubin interrogé. Utile pour pointer une instance de développement.
SERVER_VARIABLE: Final = "RUBIN_BOT_SERVEUR"

#: Délai d'attente des appels HTTP, en secondes.
TIMEOUT_VARIABLE: Final = "RUBIN_BOT_DELAI"

MISSING_TOKEN: Final = f"""Le robot Discord n'est pas configuré, et c'est un état normal.

Il lui faut un jeton de robot dans la variable d'environnement {TOKEN_VARIABLE}.
Ce jeton se génère sur https://discord.com/developers, onglet « Bot » de
l'application, et ne se recopie nulle part dans le dépôt.

Sur le poste, il vit dans D:\\DEV\\secrets ; sur le VPS, dans le fichier
d'environnement du service systemd, lisible par le seul compte de service.

Rien d'autre n'a été démarré, et rien n'a été envoyé à Discord."""


@dataclass(frozen=True)
class Configuration:
    """Tout ce dont le robot a besoin pour tourner."""

    token: str | None
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT

    @property
    def ready(self) -> bool:
        """Vrai quand le robot peut se connecter à la passerelle Discord."""
        return bool(self.token)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Configuration:
        """Lit la configuration, sans jamais échouer sur ce qui manque."""
        source = os.environ if env is None else env
        token = (source.get(TOKEN_VARIABLE) or "").strip() or None
        return cls(
            token=token,
            base_url=_read_url(source.get(SERVER_VARIABLE)),
            timeout=_read_timeout(source.get(TIMEOUT_VARIABLE)),
        )


def _read_url(raw: str | None) -> str:
    """Retient l'adresse fournie si elle est utilisable, le défaut sinon.

    Un schéma exotique est écarté plutôt qu'accepté : le robot n'a aucune
    raison d'aller lire un fichier local, et une adresse mal saisie doit
    dégrader vers le serveur public au lieu d'échouer à chaque commande.
    """
    candidate = (raw or "").strip()
    if not candidate:
        return DEFAULT_BASE_URL
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return DEFAULT_BASE_URL
    return candidate.rstrip("/")


def _read_timeout(raw: str | None) -> float:
    """Retient le délai fourni s'il est plausible, le défaut sinon."""
    try:
        value = float((raw or "").strip())
    except ValueError:
        return DEFAULT_TIMEOUT
    # Un délai nul ou négatif couperait tous les appels ; au-delà d'une minute,
    # ce n'est plus un délai, c'est une commande Discord abandonnée.
    if not 0 < value <= 60:
        return DEFAULT_TIMEOUT
    return value
