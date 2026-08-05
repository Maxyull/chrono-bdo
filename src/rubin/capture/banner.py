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

#: Hauteur du dessin de l'icône, et distance entre le haut de la zone et le
#: haut de l'icône. Mesuré en jeu : `y` ne bouge pas d'un pixel d'un bandeau à
#: l'autre.
ICON_SIZE: Final = 55
ICON_TOP: Final = 39

#: Plage horizontale où chercher l'icône, en pixels depuis le bord gauche de la
#: zone.
#:
#: **La barre du bandeau s'adapte à la longueur du nom et reste ancrée à
#: droite.** L'icône, qui est à son extrémité gauche, se déplace donc d'une
#: quête à l'autre. Mesuré en jeu sur une session : 150 pixels d'amplitude
#: entre un nom court sur une ligne et un nom long sur deux.
#:
#: C'est ce qui rendait la détection inopérante : une position fixe, calibrée
#: sur des captures ayant toutes un nom long, ne retrouvait presque jamais
#: l'icône en conditions réelles.
ICON_SEARCH: Final = (0, 200)

#: Au-delà, un bandeau est considéré comme affiché.
#:
#: Sur des captures fixes, la corrélation vaut 0,99 quand le bandeau est là et
#: moins de 0,03 sinon. **En jeu elle plafonne à 0,90**, parce que le bandeau
#: est semi-transparent et que le décor bouge derrière. Un seuil calé sur les
#: captures fixes aurait donc raté la moitié des bandeaux réels, alors même que
#: la marge avec l'absence de bandeau reste énorme.
PRESENCE_THRESHOLD: Final = 0.70

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


def locate_icon(frame: GrayFrame) -> tuple[float, int]:
    """Meilleure corrélation trouvée en glissant sur l'axe horizontal, et son abscisse.

    Ne glisse que sur `x` : la hauteur de l'icône est constante d'un bandeau à
    l'autre, seule sa position horizontale varie avec la longueur du nom.
    Chercher aussi en `y` multiplierait le coût pour rien.

    Le glissement se fait au pixel près. Un pas plus grand irait plus vite mais
    manquerait le pic exact, et sur une corrélation déjà rabotée par la
    transparence du bandeau, chaque centième compte.
    """
    template = icon_template()
    size = template.shape[0]
    if frame.shape[0] < ICON_TOP + size or frame.shape[1] < size:
        return 0.0, 0

    band = frame[ICON_TOP : ICON_TOP + size]
    start, stop = ICON_SEARCH
    stop = min(stop, band.shape[1] - size)
    best, best_x = 0.0, 0
    for x in range(max(0, start), max(0, stop) + 1):
        score = correlation(template, band[:, x : x + size])
        if score > best:
            best, best_x = score, x
    return best, best_x


def banner_score(frame: GrayFrame) -> float:
    """À quel point cette capture de la zone contient l'icône du bandeau."""
    return locate_icon(frame)[0]


def has_banner(frame: GrayFrame, threshold: float = PRESENCE_THRESHOLD) -> bool:
    """Vrai si un bandeau de quête est affiché dans cette capture."""
    return banner_score(frame) >= threshold
