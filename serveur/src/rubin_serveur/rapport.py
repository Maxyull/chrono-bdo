"""Relaie un rapport de bogue vers un salon Discord, par webhook.

Le webhook est un secret que seul ce serveur connaît : jamais dans
l'exécutable distribué aux joueurs, qui pourrait sinon être extrait et
détourné pour poster n'importe quoi dans le salon. Voir
`D:\\DEV\\bdo\\COORDINATION.md` pour la décision et son contexte.

Ne lève jamais : un rapport qui échoue à partir doit rester une ligne d'état
pour le joueur, jamais une trace qui l'inquiète pour un souci
d'infrastructure qu'il n'a pas causé.
"""

from __future__ import annotations

import logging
from typing import Final

import requests

_log = logging.getLogger(__name__)

_TIMEOUT: Final = 10

#: Un message Discord plafonne à 2000 caractères. Tronquer ici, à l'appel du
#: webhook, est le dernier filet : la route qui reçoit le rapport borne déjà
#: sa taille d'entrée, voir `MAX_REPORT_LENGTH` dans `main.py`.
_DISCORD_MESSAGE_LIMIT: Final = 2000


def send_report(webhook_url: str, message: str, *, timeout: int = _TIMEOUT) -> bool:
    """Poste `message` sur le webhook Discord donné. Rend le succès, ne lève jamais."""
    try:
        response = requests.post(
            webhook_url,
            json={"content": message[:_DISCORD_MESSAGE_LIMIT]},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as erreur:
        _log.warning("envoi du rapport à Discord échoué : %s", erreur)
        return False
    return True
