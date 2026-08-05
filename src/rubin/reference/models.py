"""Les objets du référentiel : une quête, une chaîne de quêtes.

Le vocabulaire suit celui du jeu, pas celui du site d'où viennent les données.
Ce que bdocodex appelle un « quest group » est ce que le journal affiche comme
une entrée de l'onglet « Principales », avec son compteur `0/117`. On l'appelle
donc une **chaîne**, puisque c'est ce que l'utilisateur voit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# Codes de la colonne « type » du référentiel. Établis par recoupement : le
# nombre de quêtes portant le code correspond exactement au nombre renvoyé par
# l'URL filtrée du site (`type=mission` -> 3924 quêtes, toutes de code 1).
#
# Les autres codes existent mais n'ont pas encore de nom vérifié. On ne les
# devine pas : une quête de code inconnu reste exploitable, elle est simplement
# hors du périmètre du chronomètre.
KIND_BLACK_SPIRIT: Final = 0
KIND_MAIN: Final = 1
KIND_DAILY: Final = 3

#: Marqueurs d'embranchement, entre crochets dans le nom de la quête. Le jeu
#: propose alors un choix entre deux quêtes et une seule sera faite.
#:
#: Cherchés entre crochets et non n'importe où dans le nom : une quête peut
#: parler d'un carrefour sans en être un.
CROSSROAD_MARKERS: Final = ("carrefour", "crossroad")

#: Valeur que le référentiel emploie quand une quête n'est rattachée à aucune
#: région. Plus de la moitié du catalogue est dans ce cas, ce qui rend la
#: colonne peu utile seule : le préfixe du nom est une meilleure source.
NO_REGION: Final = "Tous"


@dataclass(frozen=True, order=True)
class QuestId:
    """Identifiant d'une quête, stable et indépendant de la langue.

    Le site l'expose sous la forme `21136/1` : le premier nombre désigne la
    chaîne, le second la position dans cette chaîne. C'est cette paire, et non
    le nom, qui sert de clé partout. Un joueur sur le client anglais et un
    joueur sur le client français produisent le même identifiant pour la même
    quête, ce qui est toute la raison pour laquelle le classement peut être
    commun aux deux langues.
    """

    chain: int
    position: int

    @classmethod
    def parse(cls, raw: str) -> QuestId:
        """Lit un identifiant `chaîne/position`.

        Lève `ValueError` sur toute autre forme. Le référentiel est une source
        externe : une ligne mal formée doit s'arrêter ici, bruyamment, plutôt
        que de se propager en identifiant plausible mais faux.
        """
        chain, sep, position = raw.partition("/")
        if not sep or not chain.isdigit() or not position.isdigit():
            raise ValueError(f"identifiant de quête illisible : {raw!r}")
        return cls(int(chain), int(position))

    def __str__(self) -> str:
        return f"{self.chain}/{self.position}"


@dataclass(frozen=True)
class Quest:
    """Une quête du référentiel, dans une langue donnée."""

    id: QuestId
    #: Nom complet tel qu'affiché en jeu, préfixe compris.
    name: str
    #: Le `[Calpheon]` de tête, sans les crochets. `None` si le nom n'en a pas.
    prefix: str | None
    #: Le nom débarrassé de son préfixe.
    title: str
    #: Région déclarée par le référentiel, `None` quand elle vaut « Tous ».
    region: str | None
    kind: int
    level: int

    @property
    def is_crossroad(self) -> bool:
        """Vrai si cette quête est l'une des branches d'un choix.

        Le jeu affiche alors un panneau « Choisir une quête » : le joueur en
        prend une et abandonne l'autre. Une chaîne qui en contient ne sera donc
        jamais faite en entier, et additionner les temps de toutes ses quêtes
        surestime sa durée.
        """
        return any(
            marker in group.casefold()
            for group in re.findall(r"\[([^\]]+)\]", self.name)
            for marker in CROSSROAD_MARKERS
        )

    @property
    def is_main(self) -> bool:
        """Vrai pour les quêtes de l'onglet « Principales ».

        C'est le seul périmètre que le chronomètre mesure : classer une quête
        répétable au temps n'aurait aucun sens, puisqu'on la refait indéfiniment.
        """
        return self.kind == KIND_MAIN


@dataclass(frozen=True)
class Chain:
    """Une suite de quêtes partageant le même numéro de chaîne.

    Correspond à une ligne de l'onglet « Principales » du journal, du type
    `[Calpheon] Le héros de Calpheon : 0/117`.
    """

    number: int
    quests: tuple[Quest, ...]

    @property
    def name(self) -> str:
        """Nom de la chaîne, emprunté à sa première quête.

        Le référentiel ne porte pas de titre de chaîne. Le jeu en affiche un,
        qui ne se déduit pas des quêtes. Faute de mieux, on prend le nom de la
        première, ce qui donne un libellé reconnaissable sans prétendre être
        celui du jeu.
        """
        return self.quests[0].name if self.quests else f"chaîne {self.number}"

    @property
    def region(self) -> str | None:
        """Région dominante de la chaîne, ou `None` si aucune ne se dégage."""
        seen = [q.region for q in self.quests if q.region is not None]
        if not seen:
            return None
        return max(set(seen), key=seen.count)

    @property
    def crossroads(self) -> tuple[Quest, ...]:
        """Les quêtes de cette chaîne qui sont des branches d'un choix.

        Le référentiel dit lesquelles sont des embranchements, mais pas
        lesquelles s'excluent entre elles : deux carrefours indépendants dans
        une même chaîne y sont indiscernables d'un seul choix à quatre
        branches. On expose donc le compte, sans prétendre trancher.
        """
        return tuple(q for q in self.quests if q.is_crossroad)

    @property
    def is_contiguous(self) -> bool:
        """Vrai si les positions vont de 1 à N sans trou.

        Environ trois chaînes sur quatre sont dans ce cas. Les autres portent
        des trous, parce que des quêtes ont été retirées du jeu ou parce que la
        chaîne comporte un embranchement. Une chaîne à trous reste utilisable :
        l'ordre relatif des positions connues reste juste, seule la complétude
        n'est pas garantie.
        """
        positions = sorted(q.id.position for q in self.quests)
        return positions == list(range(1, len(positions) + 1))

    def __len__(self) -> int:
        return len(self.quests)
