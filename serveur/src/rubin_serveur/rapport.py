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

#: Un nom de fil plafonne à 100 caractères. Contrairement au message, celui-ci
#: n'est borné nulle part ailleurs : le pseudonyme Discord d'un joueur peut
#: être long, et un nom trop long fait rendre 400 au webhook entier.
_DISCORD_THREAD_NAME_LIMIT: Final = 100


def send_report(
    webhook_url: str, message: str, *, thread_name: str, timeout: int = _TIMEOUT
) -> bool:
    """Poste `message` sur le webhook Discord donné. Rend le succès, ne lève jamais.

    `thread_name` est obligatoire, et sans valeur par défaut exprès. Les deux
    salons de rapports (`#rubin-bugs` et `#butin-bugs`) sont des **forums**, et
    un webhook de forum refuse un message qui n'ouvre pas de fil. Mesuré contre
    l'API par la session `discord-bdo` le 06/08/2026, sur les deux webhooks
    réels (voir `D:\\DEV\\bdo\\COORDINATION.md`) :

        POST {"content": ...}                        -> 400, code 220001
             « Webhooks posted to forum channels must have a thread_name
               or thread_id »
        POST {"content": ..., "thread_name": ...}    -> 200

    Un défaut à `None` aurait laissé le prochain appelant reproduire ce 400
    sans rien voir, puisque cette fonction ne lève jamais : l'échec ne serait
    ressorti que dans le journal du serveur, et le joueur aurait vu son
    rapport partir dans le vide. Le rendre obligatoire fait trancher mypy à
    l'écriture plutôt que Discord en production.
    """
    try:
        response = requests.post(
            webhook_url,
            json={
                "content": message[:_DISCORD_MESSAGE_LIMIT],
                "thread_name": thread_name[:_DISCORD_THREAD_NAME_LIMIT],
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as erreur:
        _log.warning("envoi du rapport à Discord échoué : %s", erreur)
        return False
    return True
