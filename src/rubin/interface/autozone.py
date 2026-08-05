"""Trouver tout seul où le bandeau de quête apparaît.

Tracer sa zone à la main marche, mais suppose que le joueur sache viser. Ce
module cherche à sa place, et il n'y arrive qu'en combinant deux indices dont
aucun ne suffit seul.

## Pourquoi l'icône seule ne marche pas

Chercher le gabarit de l'icône sur un quart d'écran, c'est tester des dizaines
de milliers de positions. Le maximum de corrélation finit toujours par dépasser
le seuil, et on « trouve » du décor. C'est arrivé pour de vrai : score de 0,710
sur des rochers et un mur de pierre, très au-dessus des 0,70 requis.

Un seuil n'a de sens qu'avec le nombre d'essais pour lequel il a été calé.
Celui du bandeau vaut pour une bande de 349 pixels de large, pas pour 1280.

## Pourquoi le texte seul ne suffit pas non plus

« Nouvelle quête » ou « Quête accomplie » ne se trouvent nulle part ailleurs à
l'écran : les lire prouve qu'un bandeau est affiché. Mais la reconnaissance rend
du texte sans dire **où** elle l'a lu, donc elle prouve la présence sans donner
la position.

## La combinaison

Le titre prouve qu'un bandeau est là **maintenant** ; l'icône, cherchée dans ce
seul instant, le localise. Le décor n'a pas disparu, mais on ne consulte plus le
gabarit à l'aveugle : on ne l'interroge que sur une image dont on sait qu'elle
contient un vrai bandeau, et on retient le meilleur score, qui est alors le bon.

Reste que le joueur doit **faire une quête** pendant la recherche. C'est le prix
à payer, et il est annoncé : sans bandeau à l'écran, il n'y a rien à trouver.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

from ..capture import GrayFrame, Rect, ScreenCapture, find_game_window, icon_template
from ..capture.banner import correlation
from ..capture.region import banner_region
from ..reading import RapidOcrReader
from ..reading.parsing import TITLES
from ..reference.catalog import fold

#: Durée maximale de la recherche. Assez pour accepter ou rendre une quête sans
#: se presser, assez peu pour qu'on n'oublie pas qu'elle tourne.
TIMEOUT: Final = 120.0

#: Pas du balayage vertical, en pixels. Quatre suffisent : l'icône fait 55 de
#: haut, on ne peut pas la manquer, et diviser le pas par quatre quadruplerait
#: le temps de recherche sans rien gagner.
STEP: Final = 4


def titles_folded() -> set[str]:
    """Les libellés de titre, pliés comme le catalogue les compare.

    ⚠️ `TITLES` associe un **genre** de bandeau à ses libellés : le texte est
    dans les valeurs, pas dans les clés. S'y tromper donne un ensemble de
    `BannerKind` et une erreur incompréhensible à la première comparaison.
    """
    return {fold(libellé) for libellés in TITLES.values() for libellé in libellés}


def contains_title(lines: list[tuple[str, float]], expected: set[str]) -> bool:
    """Vrai si l'une des lignes porte un titre de bandeau.

    Comparaison sur la forme pliée, sans espaces ni ponctuation : la
    reconnaissance rend « Objectif dequete accompli », et un test d'égalité
    stricte ne verrait jamais rien.
    """
    return any(any(attendu in fold(texte) for attendu in expected) for texte, _ in lines)


def locate_banner(image: GrayFrame, template: GrayFrame, step: int = STEP) -> tuple[int, float]:
    """Hauteur du meilleur accord de l'icône dans l'image, et son score.

    Rendue séparément du reste pour être vérifiable sans écran. La hauteur est
    relative au haut de l'image fournie.
    """
    haut, largeur = template.shape
    meilleur_y, meilleur = 0, -1.0
    for y in range(0, image.shape[0] - haut, step):
        tranche = image[y : y + haut]
        score = max(
            correlation(tranche[:, x : x + largeur], template)
            for x in range(0, tranche.shape[1] - largeur, 8)
        )
        if score > meilleur:
            meilleur_y, meilleur = y, score
    return meilleur_y, meilleur


def search(
    report: Callable[[str], None],
    should_stop: Callable[[], bool],
    timeout: float = TIMEOUT,
) -> Rect | None:
    """Cherche le bandeau et rend sa zone, ou `None` si rien n'a été vu.

    `report` reçoit des messages destinés au joueur, `should_stop` permet
    d'interrompre. Les deux sont appelés depuis le fil de recherche.
    """
    fenêtre = find_game_window()
    if fenêtre is None:
        report("jeu introuvable")
        return None

    quart = Rect(
        fenêtre.left + fenêtre.width // 2,
        fenêtre.top + fenêtre.height // 2,
        fenêtre.width // 2,
        fenêtre.height // 2,
    )
    attendus = titles_folded()
    gabarit = icon_template()
    lecteur = RapidOcrReader()
    calculée = banner_region(fenêtre)

    report("acceptez ou terminez une quête, je cherche le bandeau…")
    début = time.time()
    with ScreenCapture(quart) as capture:
        while time.time() - début < timeout and not should_stop():
            image = capture.grab_gray()
            if not contains_title(lecteur.read(image), attendus):
                continue
            # Un bandeau est là MAINTENANT : le gabarit peut parler.
            y, score = locate_banner(image, gabarit)
            if score < 0.5:  # pragma: pas de couverture
                continue
            haut = quart.top + y
            # La largeur et la hauteur restent celles mesurées : c'est la
            # POSITION qu'on cherchait, pas la taille du bandeau, qui ne varie
            # pas. Déduire les deux d'une seule observation multiplierait les
            # façons de se tromper.
            trouvée = Rect(calculée.left, haut, calculée.width, calculée.height)
            report(f"bandeau trouvé, zone réglée à {trouvée.width}x{trouvée.height}")
            return trouvée

    report(f"aucun bandeau vu en {int(time.time() - début)} s : aucune quête faite ?")
    return None
