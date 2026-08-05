"""Savoir si le logiciel est à jour, et le dire.

Un exécutable distribué sans moyen d'apprendre qu'il est périmé condamne
chaque correction à ne jamais atteindre personne. Le serveur refuse déjà les
protocoles trop anciens : encore faut-il que le joueur puisse comprendre
pourquoi ses mesures ne partent plus.

**Rien n'est remplacé automatiquement, et c'est délibéré.** Sous Windows, un
programme ne peut pas se réécrire pendant qu'il tourne : son fichier est
verrouillé. Il faudrait un lanceur intermédiaire qui attende la fin du
processus pour permuter les fichiers, or ce genre de binaire qui se remplace
tout seul déclenche les antivirus. Pour un outil de cette taille, le coût et le
risque dépassent le gain.

Ce module se contente donc de comparer deux numéros et de dire quoi faire. Le
téléchargement reste un clic humain, ce qui a l'avantage d'être compréhensible
et de ne jamais casser une installation qui fonctionnait.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

import requests

from . import __version__

_TIMEOUT: Final = 5
_USER_AGENT: Final = "rubin-bdo"
_NUMBER = re.compile(r"\d+")


def parse_version(value: str) -> tuple[int, ...]:
    """Découpe un numéro de version en nombres comparables.

    Comparer « 0.10.0 » et « 0.9.0 » comme des chaînes de caractères donnerait
    la 0.10 pour la plus ancienne, l'ordre alphabétique plaçant « 1 » avant
    « 9 ». Ce genre d'erreur ne se voit qu'à la dixième version, longtemps
    après avoir été écrite.
    """
    return tuple(int(n) for n in _NUMBER.findall(value)) or (0,)


@dataclass(frozen=True)
class UpdateStatus:
    """Ce que le serveur dit de la version installée."""

    current: str
    latest: str
    minimum: str
    download_url: str

    @property
    def outdated(self) -> bool:
        """Une version plus récente existe."""
        return parse_version(self.current) < parse_version(self.latest)

    @property
    def rejected(self) -> bool:
        """Cette version est trop ancienne : le serveur refusera ses mesures."""
        return parse_version(self.current) < parse_version(self.minimum)

    def message(self) -> str | None:
        """Ce qu'il faut dire au joueur, ou `None` s'il n'y a rien à dire."""
        if self.rejected:
            return (
                f"⚠ Cette version ({self.current}) est trop ancienne : le serveur "
                f"refusera vos mesures. Version {self.latest} : {self.download_url}"
            )
        if self.outdated:
            # Signalé mais sans insistance : une version simplement dépassée
            # continue de fonctionner, et interrompre une session pour cela
            # serait plus gênant qu'utile.
            return f"Une version {self.latest} est disponible : {self.download_url}"
        return None


def check_for_update(base_url: str | None, timeout: int = _TIMEOUT) -> UpdateStatus | None:
    """Interroge le serveur sur les versions.

    Ne lève jamais et ne bloque jamais longtemps : savoir si une mise à jour
    existe est utile, mais jamais au point de retarder ou d'empêcher une
    session de jeu. En cas d'échec, on ne sait rien, et ne rien savoir vaut
    mieux qu'un avertissement inventé.
    """
    if not base_url:
        return None
    try:
        response = requests.get(
            base_url.rstrip("/") + "/v1/version",
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
        )
        if response.status_code >= 400:
            return None
        body = response.json()
    except (requests.RequestException, ValueError):
        return None

    latest = str(body.get("derniere", __version__))
    return UpdateStatus(
        current=__version__,
        latest=latest,
        minimum=str(body.get("minimale", latest)),
        download_url=str(body.get("telechargement", "")),
    )
