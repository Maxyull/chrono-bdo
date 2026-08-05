"""Où poser la fenêtre de Rubin sans qu'elle aveugle sa propre mesure.

Le problème n'est pas esthétique. Rubin lit une **capture d'écran**, donc ce qui
est composé à l'écran, et non le tampon de rendu du jeu. Une fenêtre posée sur
la zone du bandeau est lue à la place du bandeau, et la session ne mesure rien.

C'est arrivé pour de vrai, avec un navigateur : la fenêtre du jeu était
correctement trouvée, mais Chrome en occupait la moitié gauche, et c'est Chrome
qui a été capturé. Notre propre fenêtre ferait exactement pareil.

**La transparence ne sauve de rien**, et c'est le point contre-intuitif. Une
fenêtre à trente pour cent d'opacité posée sur le bandeau ne laisse pas voir le
bandeau : elle laisse voir un mélange des deux, et c'est ce mélange qui est
capturé. Le texte y perd le contraste dont la reconnaissance a besoin.

Ce module calcule donc une place qui ne recouvre aucune zone lue. Il ne touche
ni à l'écran ni à une fenêtre : il range des rectangles, ce qui le rend
vérifiable sans écran, donc en intégration continue.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from .capture import Rect

#: Marge laissée entre la fenêtre et le bord du jeu, en pixels. Assez pour que
#: la fenêtre ne semble pas collée, assez peu pour ne pas gaspiller la place sur
#: un écran déjà chargé.
MARGIN: Final = 12


def conflicts(placement: Rect, zones: Sequence[Rect]) -> list[Rect]:
    """Les zones de lecture que cette position recouvrirait.

    Rendre la liste plutôt qu'un simple oui ou non : l'interface doit pouvoir
    dire **laquelle** est en cause, parce que « le bandeau » et « le panneau de
    suivi » n'ont pas les mêmes conséquences ni le même remède.
    """
    return [zone for zone in zones if placement.overlaps(zone)]


def candidates(window: Rect, size: tuple[int, int], margin: int = MARGIN) -> list[Rect]:
    """Les emplacements envisagés, du plus souhaitable au moins souhaitable.

    L'ordre porte une intention. Le premier est **à gauche du panneau de
    suivi**, en haut à droite du jeu : c'est là que le joueur regarde déjà pour
    lire ses quêtes, donc c'est là que la liste des suivantes lui coûte le moins
    de déplacement d'yeux. C'est aussi ce que demandait la commande, « à côté
    des quêtes ».

    Les suivants s'éloignent : le bord gauche, puis le haut, puis le bas. Aucun
    n'est bon en soi, ils existent pour qu'une disposition d'écran inhabituelle
    trouve tout de même une place plutôt que d'imposer un recouvrement.
    """
    largeur, hauteur = size
    haut = window.top + margin
    bas = window.bottom - hauteur - margin
    gauche = window.left + margin
    droite = window.right - largeur - margin
    milieu_vertical = window.top + (window.height - hauteur) // 2
    # À gauche du tiers droit, là où vivent les deux zones lues.
    avant_le_bord = window.right - window.width // 3 - largeur - margin
    return [
        Rect(avant_le_bord, haut, largeur, hauteur),
        Rect(gauche, milieu_vertical, largeur, hauteur),
        Rect(gauche, haut, largeur, hauteur),
        Rect(droite, milieu_vertical, largeur, hauteur),
        Rect(gauche, bas, largeur, hauteur),
    ]


def choose(
    window: Rect,
    zones: Sequence[Rect],
    size: tuple[int, int],
    margin: int = MARGIN,
) -> Rect | None:
    """La meilleure place libre, ou `None` s'il n'y en a aucune.

    `None` n'est pas un échec à rattraper en posant la fenêtre quelque part : il
    veut dire que toute position essayée recouvrirait une zone lue, donc qu'il
    faut le dire au joueur et le laisser choisir entre déplacer sa fenêtre et
    accepter de ne rien mesurer. Décider à sa place, ici, reviendrait à casser
    la mesure en silence pour un confort d'affichage.
    """
    for candidate in candidates(window, size, margin):
        if not conflicts(candidate, zones):
            return candidate
    return None


def is_inside(placement: Rect, window: Rect) -> bool:
    """Vrai si la position tient entièrement dans la fenêtre du jeu.

    Sur un écran étroit, un emplacement calculé peut déborder. Une fenêtre à
    moitié hors de l'écran n'est pas seulement laide : la partie visible est
    tronquée sans que rien ne l'annonce.
    """
    return (
        placement.left >= window.left
        and placement.top >= window.top
        and placement.right <= window.right
        and placement.bottom <= window.bottom
    )
