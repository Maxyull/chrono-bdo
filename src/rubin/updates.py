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

#: Les trois niveaux d'importance d'une mise à jour, du plus pressant au moins.
#:
#: Demandés par Maxime le 07/08/2026 : « il faut afficher mise à jour
#: importante (changement majeur OCR), secondaires (visuel, placement changé,
#: quality of life, pas besoin mais recommandé), pas du tout importante ».
IMPORTANT: Final = "importante"
SECONDAIRE: Final = "secondaire"
NEGLIGEABLE: Final = "negligeable"

#: Ce que chaque niveau annonce, en une ligne, et ce qu'il demande au joueur.
#:
#: ⚠️ **Chacune dit ce qu'il faut FAIRE**, pas seulement ce qui a changé. Un
#: joueur ne sait pas ce qu'« OCR » veut dire pour lui ; il sait ce que
#: « vos mesures peuvent être fausses » veut dire.
UPDATE_HEADLINES: Final = {
    IMPORTANT: "⚠ Mise à jour IMPORTANTE, la reconnaissance a changé : "
    "sans elle vos mesures peuvent être fausses",
    SECONDAIRE: "Mise à jour secondaire, affichage et confort : "
    "recommandée, pas indispensable",
    NEGLIGEABLE: "Mise à jour mineure : rien qui presse",
}

#: Le rang, dans le numéro de version, que chaque niveau occupe.
#:
#: Le numéro s'écrit `0.IMPORTANT.SECONDAIRE.NEGLIGEABLE` depuis le
#: 07/08/2026, sur demande de Maxime : « on va passer en 0.X.X.X pour ajouter
#: le dernier chiffre maj vraiment pas importante ».
#:
#: ⚠️ **Le niveau se lit donc dans le numéro lui-même**, sans que le serveur
#: ait rien à dire de plus. C'est ce qui garantit qu'ils ne peuvent pas se
#: contredire : un champ « importance » servi à côté du numéro pourrait
#: annoncer « mineure » sur une version qui change la reconnaissance, et rien
#: ne le rattraperait. Ici, publier une version dont le deuxième chiffre bouge
#: EST l'annonce.
#:
#: Le premier rang, celui qui vaut `0` aujourd'hui, compte comme important :
#: le jour où Rubin passera en 1.0, ce ne sera pas une broutille.
_LEVEL_BY_RANK: Final = (IMPORTANT, IMPORTANT, SECONDAIRE, NEGLIGEABLE)


def update_importance(current: str, latest: str) -> str:
    """À quel point la mise à jour de `current` vers `latest` presse.

    Le rang du **premier chiffre qui diffère** donne le niveau : voir
    `_LEVEL_BY_RANK`. Les deux numéros sont comparés sur la même longueur,
    les manquants valant zéro, parce que les versions publiées avant le
    07/08/2026 n'ont que trois chiffres : « 0.6.2 » et « 0.6.2.1 » ne
    diffèrent qu'au quatrième rang, donc négligeable, ce qui est exact.

    Au-delà du dernier rang connu, on retombe sur le niveau le plus faible :
    un cinquième chiffre, si quelqu'un en ajoute un jour, ne sera pas plus
    grave que le quatrième.
    """
    gauche = parse_version(current)
    droite = parse_version(latest)
    longueur = max(len(gauche), len(droite))
    gauche += (0,) * (longueur - len(gauche))
    droite += (0,) * (longueur - len(droite))
    for rang, (a, b) in enumerate(zip(gauche, droite, strict=True)):
        if a != b:
            return _LEVEL_BY_RANK[min(rang, len(_LEVEL_BY_RANK) - 1)]
    return NEGLIGEABLE


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

    @property
    def importance(self) -> str | None:
        """À quel point cette mise à jour presse, ou `None` s'il n'y en a pas.

        Voir `update_importance` : le niveau se lit dans le numéro lui-même.
        """
        if not self.outdated:
            return None
        return update_importance(self.current, self.latest)

    def message(self) -> str | None:
        """Ce qu'il faut dire au joueur, ou `None` s'il n'y a rien à dire.

        ⚠️ **Trois messages différents, parce qu'ils appellent trois gestes
        différents.** Demandé par Maxime le 07/08/2026 : « il faut afficher
        mise à jour importante, secondaires, pas du tout importante ».

        Un joueur à qui l'on répète « une version est disponible » sur le même
        ton pour un changement de reconnaissance et pour un mot corrigé dans
        une infobulle finit par ne plus lire aucun des deux. Le jour où la
        mise à jour compte vraiment, l'avertissement a été usé par toutes
        celles qui ne comptaient pas.
        """
        if self.rejected:
            return (
                f"⚠ Cette version ({self.current}) est trop ancienne : le serveur "
                f"refusera vos mesures. Version {self.latest} : {self.download_url}"
            )
        niveau = self.importance
        if niveau is None:
            return None
        return f"{UPDATE_HEADLINES[niveau]} ({self.latest}) : {self.download_url}"


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
