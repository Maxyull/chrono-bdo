"""Le référentiel des quêtes : ce que le jeu contient, indépendamment du joueur.

Sépare deux choses qu'il ne faut pas confondre : ce que le jeu contient, qui
est fixe et se télécharge une fois, et ce que le joueur fait, qui se mesure à
l'écran. Ce paquet ne s'occupe que du premier.
"""

from .catalog import MIN_TRUNCATED_KEY, Catalog, fold, is_roman_numeral
from .models import (
    KIND_BLACK_SPIRIT,
    KIND_DAILY,
    KIND_MAIN,
    NO_REGION,
    Chain,
    Quest,
    QuestId,
)
from .parsing import clean_text, parse_payload, parse_row, split_prefix

__all__ = [
    "KIND_BLACK_SPIRIT",
    "KIND_DAILY",
    "KIND_MAIN",
    "MIN_TRUNCATED_KEY",
    "NO_REGION",
    "Catalog",
    "Chain",
    "Quest",
    "QuestId",
    "clean_text",
    "fold",
    "is_roman_numeral",
    "parse_payload",
    "parse_row",
    "split_prefix",
]
