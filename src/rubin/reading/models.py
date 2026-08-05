"""Ce qu'un bandeau de quête annonce.

Le jeu affiche quatre bandeaux différents au même endroit. Deux bornent une
quête, deux racontent ce qui se passe pendant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BannerKind(Enum):
    """Les quatre bandeaux, relevés sur des captures du jeu."""

    #: « Nouvelle quête ». La quête vient d'être acceptée : le chronomètre part.
    ACCEPTED = "acceptee"
    #: « Objectif de quête partiellement accompli ». Une étape intermédiaire,
    #: qui n'est pas la fin. Le titre est tronqué à l'écran.
    PARTIAL = "objectif-partiel"
    #: « Objectif de quête accompli ». Le dernier objectif est atteint, mais la
    #: quête n'est pas rendue : il reste à parler au personnage.
    OBJECTIVE_DONE = "objectif-accompli"
    #: « Quête accomplie ». La quête est terminée : le chronomètre s'arrête.
    COMPLETED = "accomplie"

    @property
    def bounds_a_quest(self) -> bool:
        """Vrai pour les deux bandeaux qui bornent une mesure."""
        return self in (BannerKind.ACCEPTED, BannerKind.COMPLETED)


@dataclass(frozen=True)
class BannerReading:
    """Un bandeau lu à l'écran, avant toute résolution dans le référentiel.

    Le nom est celui affiché, tel que la reconnaissance l'a rendu, préfixe de
    région compris et défauts compris. Le rapprocher d'une quête connue est le
    travail du catalogue, pas celui d'un module de lecture.
    """

    kind: BannerKind
    quest_name: str
    #: Score le plus faible parmi les lignes retenues. C'est le maillon faible
    #: qui compte : un titre lu à 0,99 ne rachète pas un nom lu à 0,40.
    confidence: float
    #: Les lignes du nom, non recollées. Le bandeau n'affiche pas toujours que
    #: le nom : sur un bandeau d'objectif, une ligne de description le suit, et
    #: rien dans sa mise en forme ne la distingue d'une suite de nom. Savoir où
    #: le nom s'arrête demande le catalogue, que ce module n'a pas.
    name_lines: tuple[str, ...] = ()
