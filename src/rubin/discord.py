"""Savoir si le compte Discord du joueur est rattaché, et le lui dire.

Le rattachement se fait dans un navigateur, hors du logiciel : Rubin ouvre
une page, le joueur autorise, Discord le renvoie vers le serveur, et le
serveur enregistre. Rien de tout cela ne repasse par la fenêtre. Sans une
question posée au serveur, elle ne peut donc **jamais** apprendre que ça a
marché.

C'est exactement ce qui est arrivé à Maxime le 06/08/2026 : son compte était
rattaché pour de vrai, le serveur avait rendu
`{"rattache":true,"nom":"maxyull"}`, et la fenêtre affichait toujours
« autorisez Rubin dans votre navigateur, puis revenez ici ». Le logiciel
n'avait pas tort, il ne savait pas.

Trois états, jamais deux : rattaché, pas rattaché, et **on ne sait pas**. Le
troisième est le plus important. Un serveur injoignable ne doit pas se lire
« vous n'êtes pas connecté », qui enverrait le joueur refaire un rattachement
déjà fait. C'est le même principe que partout ici : ne rien savoir vaut mieux
qu'affirmer à tort.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import requests

_TIMEOUT: Final = 5
_USER_AGENT: Final = "rubin-bdo"


@dataclass(frozen=True)
class DiscordAccount:
    """Ce que le serveur sait du rattachement de ce contributeur."""

    linked: bool
    name: str | None

    @property
    def display_name(self) -> str | None:
        """Le pseudonyme à montrer, ou `None` s'il n'y a rien à montrer.

        Un rattachement annoncé sans nom ne se distingue pas d'une absence de
        rattachement pour ce que la fenêtre en fait : elle n'a rien à écrire
        dans les deux cas.
        """
        return self.name if self.linked and self.name else None


def fetch_account(
    base_url: str | None, player: str, timeout: int = _TIMEOUT
) -> DiscordAccount | None:
    """Demande au serveur l'état du rattachement. `None` si on ne sait pas.

    Ne lève jamais et ne bloque jamais longtemps, comme `check_for_update` :
    cette question est un confort d'affichage, elle ne doit ni retarder ni
    empêcher quoi que ce soit. Toute panne, tout refus, toute réponse
    illisible rendent `None`, c'est-à-dire « on ne sait pas », et surtout pas
    un `DiscordAccount(linked=False)` qui serait une affirmation.
    """
    if not base_url or not player:
        return None
    try:
        response = requests.get(
            base_url.rstrip("/") + "/v1/discord/compte",
            params={"player": player},
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
        )
        if response.status_code >= 400:
            return None
        body = response.json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(body, dict):
        return None

    nom = body.get("nom")
    return DiscordAccount(
        linked=bool(body.get("rattache")),
        name=str(nom) if nom else None,
    )
