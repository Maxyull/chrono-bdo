"""Décodage des lignes brutes du référentiel.

La source ne sert pas des objets, elle sert le contenu d'un tableau de site web :
chaque quête est une liste de onze cases, dont plusieurs contiennent du HTML
d'affichage. Ce module ramène ça à des `Quest`, et refuse ce qu'il ne comprend
pas plutôt que de produire une quête à moitié remplie.
"""

from __future__ import annotations

import html
import re
from typing import Any

from .models import NO_REGION, Quest, QuestId

#: Indices des cases utiles dans une ligne. Les cases 1, 8 et 9 portent des
#: icônes et des récompenses dont le chronomètre n'a pas l'usage.
_ID = 0
_NAME = 2
_LEVEL = 3
_REGION = 4
_KIND = 10
_EXPECTED_COLUMNS = 11

_TAGS = re.compile(r"<[^>]+>")
#: Un préfixe de tête entre crochets : `[Calpheon] Jeron, la tacticienne`.
#: Volontairement non gourmand, pour ne pas avaler un second groupe de crochets
#: quand le nom en contient un, comme `[Mediah][I] L'ancienne famille royale`.
_PREFIX = re.compile(r"^\[([^\]]+)\]\s*")


def clean_text(raw: str) -> str:
    """Retire le balisage et rend les entités HTML.

    Sans `unescape`, la région d'O'dyllita arrive sous la forme `O&#39;dyllita`
    et ne correspond plus à rien de ce que le jeu affiche.
    """
    return html.unescape(_TAGS.sub("", raw)).strip()


def split_prefix(name: str) -> tuple[str | None, str]:
    """Sépare le préfixe entre crochets du reste du nom.

    Le préfixe est la seule indication de région disponible sur la majorité des
    quêtes, puisque la colonne région vaut « Tous » plus d'une fois sur deux.
    Il ne désigne d'ailleurs pas toujours un lieu : `[Livre de contes]` ou
    `[Récolte]` sont des familles de quêtes. On l'extrait sans l'interpréter.
    """
    match = _PREFIX.match(name)
    if match is None:
        return None, name
    return match.group(1), name[match.end() :].strip()


def _display(cell: Any) -> str:
    """Lit une case qui est soit une chaîne, soit un objet `{display, sort_value}`.

    Le tableau mélange les deux formes selon les colonnes, parce que celles qui
    doivent se trier autrement que par ordre alphabétique portent leur clé de
    tri à côté de leur libellé.
    """
    if isinstance(cell, dict):
        return str(cell.get("display", ""))
    return str(cell)


def parse_row(row: list[Any]) -> Quest:
    """Convertit une ligne brute en `Quest`.

    Lève `ValueError` si la ligne n'a pas la forme attendue. Le nombre de
    colonnes est vérifié explicitement : le jour où le site en ajoute une, on
    veut un échec net au chargement, pas des régions lues dans la colonne du
    niveau pendant des semaines.
    """
    if len(row) != _EXPECTED_COLUMNS:
        raise ValueError(f"ligne à {len(row)} colonnes, {_EXPECTED_COLUMNS} attendues")

    quest_id = QuestId.parse(_display(row[_ID]))
    name = clean_text(str(row[_NAME]))
    if not name:
        raise ValueError(f"quête {quest_id} sans nom")

    prefix, title = split_prefix(name)
    region = clean_text(_display(row[_REGION]))

    return Quest(
        id=quest_id,
        name=name,
        prefix=prefix,
        title=title,
        region=None if region in {NO_REGION, ""} else region,
        kind=int(row[_KIND]),
        level=int(row[_LEVEL]),
    )


def parse_payload(payload: dict[str, Any]) -> list[Quest]:
    """Convertit la réponse complète du référentiel.

    Les lignes illisibles sont écartées silencieusement plutôt que de faire
    échouer le chargement entier : une seule quête mal formée en amont ne doit
    pas priver l'utilisateur des 18 998 autres. Le compte des rejets est
    consultable par différence avec `aaData`.
    """
    rows = payload.get("aaData")
    if not isinstance(rows, list):
        raise ValueError("réponse du référentiel sans tableau `aaData`")

    quests: list[Quest] = []
    for row in rows:
        try:
            quests.append(parse_row(row))
        except (ValueError, TypeError, KeyError, IndexError):
            continue
    return quests
