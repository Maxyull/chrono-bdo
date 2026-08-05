"""Ce qui vient après la quête en cours.

Le logiciel sait déjà où en est le joueur : `Timeline.current_chain` et
`current_position` le déduisent du dernier bandeau identifié, et le panneau de
suivi confirme la chaîne quand un nom est ambigu. Ce module se contente d'en
tirer la suite et de dire ce qu'on sait du temps de chacune.

C'est la réponse à la question qu'on se pose vraiment en jouant : **qu'est-ce
qui m'attend, et combien de temps ça va me prendre**. Le bilan de fin de session
arrive trop tard pour décider quoi que ce soit.

## Trois façons de mentir, évitées ici

**Les trous de numérotation.** 82 chaînes sur 349 ont des positions manquantes.
La suite d'une quête en position 2 peut être en position 147, comme dans la
chaîne 21130. Deux causes s'y mélangent, et elles n'ont pas les mêmes
conséquences : soit la quête a été retirée du jeu, et il n'y a rien à afficher,
soit elle existe en jeu mais manque à notre référentiel, qui connaît 18 999
quêtes quand le jeu en compte 19 235. Dans le second cas, le joueur verra à
l'écran une quête que cette liste ne montre pas.

On ne sait pas distinguer les deux. Le trou est donc **signalé** plutôt
qu'enjambé en silence : une liste qui affiche 2 puis 147 sans rien dire laisse
croire que 147 suit immédiatement 2.

**Les embranchements.** 69 quêtes principales, réparties sur 38 chaînes, sont
des branches d'un choix : le jeu en propose deux, le joueur en prend une et
abandonne l'autre. Le référentiel dit lesquelles sont des branches, mais **pas
lesquelles s'excluent entre elles** : deux carrefours indépendants dans une même
chaîne y sont indiscernables d'un seul choix à quatre branches.

Elles sont donc marquées, jamais présentées comme une suite à faire dans
l'ordre. Annoncer « puis celle-ci, puis celle-là » là où il faut choisir
donnerait un programme que personne ne peut suivre.

**Les temps qu'on n'a pas.** Une quête que personne n'a mesurée n'affiche pas de
durée, et le dit. Laisser la colonne vide ou afficher un zéro se lirait comme
« instantané » plutôt que comme « inconnu ».

## Ce que ce module ne fait pas

Il ne prévoit pas la durée totale de ce qui vient. La somme des médianes ment
d'un facteur deux : sur une session réelle, le débit au rythme médian annonçait
77 quêtes par heure là où la session en avait produit 36, trajets et dialogues
compris. Additionner cinq médianes pour annoncer « il vous reste vingt minutes »
serait un chiffre faux dans sa forme la plus nuisible, plausible et précis.

Voir `docs/ou-va-le-projet.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .reference import Catalog, Quest
from .references import QuestReference, ReferenceClient

#: Nombre de quêtes affichées par défaut. Cinq tiennent dans un coin d'écran et
#: couvrent largement ce qu'on anticipe en jouant. Chaque quête inconnue du cache
#: coûte un appel au serveur, donc en montrer trente allongerait l'affichage
#: sans que personne les lise.
DEFAULT_COUNT: Final = 5


@dataclass(frozen=True)
class UpcomingQuest:
    """Une quête à venir, avec ce qu'on sait d'elle."""

    quest: Quest
    #: Ce que les autres joueurs ont mesuré, ou `None` si personne ne l'a fait.
    #: `None` veut dire « inconnu », jamais « instantané ».
    reference: QuestReference | None
    #: Positions manquantes entre la quête précédente de la liste et celle-ci.
    #:
    #: Zéro dans le cas normal. Une valeur non nulle signale que le référentiel
    #: ne connaît pas la suite immédiate : soit ces quêtes ont été retirées du
    #: jeu, soit elles existent et nous manquent. On ne sait pas trancher, donc
    #: on le dit au lieu d'enjamber le trou sans rien signaler.
    gap_before: int = 0

    @property
    def is_crossroad(self) -> bool:
        """Vrai si c'est une branche d'un choix, donc pas une étape obligée."""
        return self.quest.is_crossroad

    @property
    def is_measured(self) -> bool:
        return self.reference is not None


def upcoming(
    catalog: Catalog,
    chain: int,
    after_position: int,
    language: str = "fr",
    count: int = DEFAULT_COUNT,
    references: ReferenceClient | None = None,
) -> list[UpcomingQuest]:
    """Les quêtes qui suivent, dans l'ordre des positions.

    `after_position` est exclu : on montre ce qui vient **après** la quête en
    cours, pas elle-même.

    Les positions sont prises telles que le référentiel les connaît, sans
    supposer qu'elles se suivent une à une. Supposer la contiguïté ferait
    disparaître la suite de 82 chaînes sur 349 dès le premier trou rencontré :
    aucune quête n'y porte la position juste après.

    C'est l'inverse du choix fait pour la **déduction** d'une fin manquée, dans
    `timing.py`, et la différence est délibérée. Déduire exige la contiguïté,
    parce qu'un trou peut cacher une quête réellement faite dont on
    inclurait le temps par erreur, ce qui fabriquerait une mesure fausse.
    Afficher n'exige rien : montrer la suite connue n'invente aucun chiffre, et
    le trou est signalé.

    Rend une liste vide plutôt qu'une erreur quand la chaîne est inconnue ou
    qu'il ne reste rien : ne rien avoir à montrer est un cas normal, notamment
    en fin de chaîne.
    """
    if count <= 0:
        return []
    known = catalog.chains(language, kind=None).get(chain)
    if known is None:
        return []

    following = sorted(
        (quest for quest in known.quests if quest.id.position > after_position),
        key=lambda quest: quest.id.position,
    )[:count]

    result: list[UpcomingQuest] = []
    previous = after_position
    for quest in following:
        result.append(
            UpcomingQuest(
                quest=quest,
                reference=references.quest(quest.id) if references is not None else None,
                gap_before=quest.id.position - previous - 1,
            )
        )
        previous = quest.id.position
    return result


def crossroads_ahead(quests: list[UpcomingQuest]) -> int:
    """Combien de ces quêtes sont des branches d'un choix.

    Sert à n'écrire l'avertissement qu'une fois, sous la liste, plutôt que de le
    répéter sur chaque ligne concernée.
    """
    return sum(1 for item in quests if item.is_crossroad)
