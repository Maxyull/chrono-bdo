"""Reconnaître qu'un bandeau de quête est affiché.

Sans bandeau, la zone surveillée ne montre pas un fond fixe : elle montre le
chat du jeu, **qui défile en permanence**. Une détection fondée sur « les
pixels ont changé » se déclencherait donc en continu et lancerait la
reconnaissance de caractères des milliers de fois par heure pour lire des
conversations de guilde.

Il faut reconnaître le bandeau lui-même. Trois pistes ont été mesurées sur des
captures réelles, neuf avec bandeau et trois sans :

| Indice | Séparation des deux cas |
|---|---|
| luminance moyenne de la zone | les deux se chevauchent |
| luminance moyenne de l'icône | 2 niveaux de gris de marge |
| **corrélation de forme de l'icône** | **0,97 de marge** |

La corrélation gagne parce qu'elle regarde la forme et non la clarté : le
bandeau est semi-transparent, sa luminosité dépend du décor derrière, mais le
dessin de son icône, lui, ne change pas.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

import numpy as np

from .screen import GrayFrame

#: Position de l'icône dans la zone du bandeau : gauche, haut, droite, bas.
ICON_BOX: Final = (25, 40, 80, 95)

#: Au-delà, un bandeau est considéré comme affiché. Les mesures donnent 0,994
#: au minimum quand il l'est, et 0,022 au maximum quand il ne l'est pas. Le
#: seuil est posé loin des deux, là où il ne départage rien d'observé : le
#: choix exact n'a donc aucune influence, ce qui est le signe d'un bon indice.
PRESENCE_THRESHOLD: Final = 0.80

_TEMPLATE_PATH: Final = Path(__file__).parent / "data" / "banner_icon.png"


@lru_cache(maxsize=1)
def icon_template() -> GrayFrame:
    """Le dessin de l'icône du bandeau, chargé une fois.

    Extrait de 55 sur 55 pixels de l'interface du jeu, sans texte, conservé
    pour permettre la reconnaissance. Chargé paresseusement pour que l'import
    du module ne lise pas le disque.
    """
    from PIL import Image

    with Image.open(_TEMPLATE_PATH) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


def correlation(a: GrayFrame, b: GrayFrame) -> float:
    """Corrélation croisée normalisée de deux images, de -1 à 1.

    Normalisée, donc insensible à la luminosité et au contraste d'ensemble :
    c'est ce qui la rend utilisable sur un bandeau semi-transparent, dont la
    clarté dépend de ce que le joueur a derrière lui à l'écran.

    Renvoie 0 quand l'une des images est uniforme, cas où la corrélation n'est
    pas définie. Zéro est le bon défaut : une image sans relief ne ressemble à
    rien, et surtout pas au bandeau.
    """
    if a.shape != b.shape or a.size == 0:
        return 0.0
    x = a.astype(np.float64)
    y = b.astype(np.float64)
    x -= x.mean()
    y -= y.mean()
    denominator = np.sqrt((x * x).sum() * (y * y).sum())
    if denominator == 0:
        return 0.0
    return float((x * y).sum() / denominator)


def banner_score(frame: GrayFrame) -> float:
    """À quel point cette capture de la zone contient l'icône du bandeau."""
    left, top, right, bottom = ICON_BOX
    if frame.shape[0] < bottom or frame.shape[1] < right:
        return 0.0
    return correlation(icon_template(), frame[top:bottom, left:right])


def has_banner(frame: GrayFrame, threshold: float = PRESENCE_THRESHOLD) -> bool:
    """Vrai si un bandeau de quête est affiché dans cette capture."""
    return banner_score(frame) >= threshold
