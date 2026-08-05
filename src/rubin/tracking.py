"""Lecture du panneau de suivi de quête.

Ce panneau ne sert pas à mesurer. Il sert à savoir **où l'on en est** : quelles
quêtes sont acceptées, et dans quelle chaîne. C'est le contexte qui permet de
trancher quand un nom lu sur le bandeau désigne plusieurs quêtes, ce qui
concerne 705 des 3 924 quêtes principales.

Deux différences avec le bandeau commandent la façon de s'en servir.

**Les noms y sont tronqués** dès qu'ils dépassent la largeur du panneau :
« [Journ.] [Récolte] Découverte ... ». Une partie des lignes n'est donc pas
identifiable, et c'est admis.

**La lecture coûte 1,9 seconde**, contre 0,3 pour le bandeau, parce que la zone
est six fois plus grande. Le panneau n'est donc jamais lu en boucle, seulement
quand on a besoin de se resituer.

Le tri entre noms de quêtes et lignes d'objectif n'est pas fait par une règle
de mise en forme. La première tentative reposait sur le tiret qui préfixe les
objectifs, mais la reconnaissance ne le rend pas toujours, et ajoute parfois un
caractère parasite né d'une icône. C'est donc le catalogue qui arbitre : ce qui
se résout en quête connue est une quête, le reste est du décor.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from .reference import Catalog, QuestId

#: En dessous, une ligne est ignorée. Même valeur que pour le bandeau : les
#: lignes utiles du panneau sortent entre 0,93 et 0,98.
MIN_LINE_SCORE: Final = 0.75


@dataclass(frozen=True)
class TrackedQuests:
    """Ce que le panneau de suivi apprend sur la partie en cours."""

    #: Les quêtes reconnues, dans l'ordre d'affichage.
    quests: tuple[QuestId, ...]
    #: Nombre de lignes que le catalogue n'a pas su rattacher à une quête.
    #: Ce sont surtout des objectifs, mais aussi les noms tronqués : un compte
    #: qui gonfle signale que la zone est mal placée.
    unresolved: int = 0

    @property
    def active(self) -> QuestId | None:
        """La quête suivie en premier, celle que le jeu met en évidence."""
        return self.quests[0] if self.quests else None

    @property
    def chain(self) -> int | None:
        """La chaîne la plus représentée parmi les quêtes suivies.

        C'est elle qui sert de contexte au chronomètre. Prendre la plus
        fréquente plutôt que celle de la première quête évite qu'une quête de
        récolte, épinglée par le joueur et sans rapport, ne fasse passer toute
        une session pour appartenant à sa chaîne.
        """
        if not self.quests:
            return None
        return Counter(q.chain for q in self.quests).most_common(1)[0][0]

    def __len__(self) -> int:
        return len(self.quests)


def read_tracker(
    lines: Iterable[tuple[str, float]],
    catalog: Catalog,
    language: str = "fr",
    min_line_score: float = MIN_LINE_SCORE,
) -> TrackedQuests:
    """Reconnaît les quêtes suivies parmi les lignes lues sur le panneau.

    Chaque ligne est soumise au catalogue. Celles qui ne se résolvent pas sont
    comptées mais écartées : ce sont les objectifs, et les noms trop longs que
    le jeu a tronqués.

    Aucune ligne n'est fusionnée avec la suivante, contrairement au bandeau.
    Sur le panneau, un nom qui déborde n'est pas coupé en deux lignes, il est
    tronqué : recoller les lignes ne ferait que fabriquer des noms inexistants
    à partir des objectifs.
    """
    found: list[QuestId] = []
    unresolved = 0
    for text, score in lines:
        cleaned = text.strip()
        if score < min_line_score or not cleaned:
            continue
        quest_id = catalog.resolve(cleaned, language)
        if quest_id is None:
            unresolved += 1
        elif quest_id not in found:
            found.append(quest_id)
    return TrackedQuests(quests=tuple(found), unresolved=unresolved)
