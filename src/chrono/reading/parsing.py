"""Transformer des lignes de texte reconnues en un bandeau typé.

Séparé de la reconnaissance elle-même, qui est lente, dépend d'un moteur et
demande un écran. Ici tout est pur : des lignes de texte entrent, un bandeau
sort. C'est donc la partie vérifiable sans rien installer, et c'est là que se
logent les cas tordus.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from ..reference import fold
from .models import BannerKind, BannerReading

#: Titres reconnus, par type de bandeau, sous leur forme normalisée.
#:
#: Ce sont des **préfixes** : « Objectif de quête partiellement accompli »
#: s'affiche tronqué en « Objectif de quête partielle... », et la troncature
#: dépend de la largeur disponible, donc du texte lui-même.
#:
#: L'ordre compte. « objectif de quete accompli » et « quete accomplie » se
#: ressemblent assez pour qu'un préfixe trop court attrape l'autre : les titres
#: sont donc essayés du plus long au plus court, et le premier qui convient
#: l'emporte.
TITLES: Final[dict[BannerKind, tuple[str, ...]]] = {
    BannerKind.PARTIAL: ("objectif de quete partielle",),
    BannerKind.OBJECTIVE_DONE: ("objectif de quete accompli",),
    BannerKind.ACCEPTED: ("nouvelle quete",),
    BannerKind.COMPLETED: ("quete accomplie",),
}

#: En dessous, une ligne est ignorée. Relevé sur les captures : les lignes
#: utiles sortent entre 0,91 et 1,00, tandis qu'un artefact isolé, un « F »
#: né d'un bord d'icône, sortait à 0,59.
MIN_LINE_SCORE: Final = 0.75

#: En dessous, le bandeau entier est refusé. Plus exigeant que pour une ligne :
#: une mesure attribuée à la mauvaise quête coûte plus cher qu'une mesure
#: perdue.
MIN_READING_SCORE: Final = 0.80


def _match_title(text: str) -> BannerKind | None:
    normalized = fold(text)
    candidates = sorted(
        ((kind, title) for kind, titles in TITLES.items() for title in titles),
        key=lambda pair: len(pair[1]),
        reverse=True,
    )
    for kind, title in candidates:
        if normalized.startswith(title):
            return kind
    return None


def parse_banner(
    lines: Iterable[tuple[str, float]],
    min_line_score: float = MIN_LINE_SCORE,
    min_reading_score: float = MIN_READING_SCORE,
) -> BannerReading | None:
    """Assemble les lignes reconnues en un bandeau, ou renvoie `None`.

    `lines` arrive dans l'ordre de lecture, de haut en bas : le titre d'abord,
    puis le nom de la quête, qui passe sur deux lignes dès qu'il est trop long.
    Les lignes du nom sont recollées par un espace.

    Renvoie `None` dans tous les cas douteux, et ils sont nombreux : la zone
    peut ne contenir aucun bandeau mais du chat de guilde, le bandeau peut être
    capturé pendant son apparition en fondu, une ligne peut être un artefact.
    Un `None` ne coûte qu'une mesure ; un bandeau inventé fausse un classement.
    """
    kept = [(text.strip(), score) for text, score in lines if score >= min_line_score]
    kept = [(text, score) for text, score in kept if text]
    if len(kept) < 2:  # il faut au moins un titre et un nom
        return None

    kind = _match_title(kept[0][0])
    if kind is None:
        return None

    name = " ".join(text for text, _ in kept[1:])
    if not name:
        return None

    confidence = min(score for _, score in kept)
    if confidence < min_reading_score:
        return None
    return BannerReading(kind=kind, quest_name=name, confidence=confidence)


def is_known_title(text: str) -> bool:
    """Vrai si ce texte est l'un des titres de bandeau connus.

    Sert à savoir si la zone montre bien un bandeau plutôt qu'autre chose,
    quand on n'a qu'une ligne sous la main.
    """
    return _match_title(text) is not None


def known_titles() -> Sequence[str]:
    """Tous les titres reconnus, normalisés. Pour diagnostic."""
    return [title for titles in TITLES.values() for title in titles]
