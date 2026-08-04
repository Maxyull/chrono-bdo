"""Où se trouve le bandeau de quête dans la fenêtre du jeu.

Ce module ne touche ni à l'écran ni au système : il calcule des rectangles. La
capture réelle vit dans `screen.py`, la localisation de la fenêtre dans
`window.py`. Cette séparation existe pour que le calcul, qui est la partie où se
logent les erreurs, soit vérifiable sans écran et donc en intégration continue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Rect:
    """Un rectangle en pixels, coin supérieur gauche et dimensions."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def to_mss(self) -> dict[str, int]:
        """Forme attendue par `mss.grab`."""
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


# Mesures relevées sur des captures réelles en 2559x1439, écran 1440p, jeu en
# plein écran sans bordure, échelle d'interface par défaut. La zone couvre la
# barre du bandeau entière, avec assez de hauteur pour un nom de quête qui
# passe sur deux lignes, ce qui arrive dès que le nom dépasse la largeur.
#
# Le bandeau est ancré au coin inférieur droit et garde une taille en pixels :
# l'interface du jeu ne s'étire pas proportionnellement à la résolution. Les
# valeurs sont donc des marges depuis ce coin, pas des fractions de l'écran.
_BANNER_WIDTH: Final = 349
_BANNER_HEIGHT: Final = 115
_MARGIN_RIGHT: Final = 0
_MARGIN_BOTTOM: Final = 139

#: Résolution sur laquelle les mesures ci-dessus ont été relevées.
REFERENCE_SIZE: Final = (2559, 1439)


# Le panneau de suivi de quête, sous la minimap. Ancré en haut à droite, il
# grandit vers le bas selon le nombre de quêtes suivies, jusqu'à dix.
#
# Mesuré sur le même écran de référence. La hauteur retenue couvre un panneau
# plein : capturer trop large ne coûte que quelques pixels, tandis que capturer
# trop court ferait disparaître les dernières quêtes sans prévenir.
_TRACKER_WIDTH: Final = 340
_TRACKER_HEIGHT: Final = 380
_TRACKER_MARGIN_RIGHT: Final = 130
_TRACKER_TOP: Final = 440


def tracker_region(window: Rect, ui_scale: float = 1.0) -> Rect:
    """Rectangle du panneau de suivi de quête, dans les coordonnées de l'écran.

    Ce panneau ne sert pas à mesurer mais à **savoir où l'on en est** : quelles
    quêtes sont acceptées, et surtout dans quelle chaîne. C'est ce contexte qui
    permet de trancher quand un nom lu sur le bandeau désigne plusieurs quêtes,
    ce qui concerne 18 % des quêtes principales.

    Il est ancré en haut à droite, sous la minimap, contrairement au bandeau
    qui l'est en bas. Les noms y sont **tronqués** dès qu'ils dépassent la
    largeur : c'est un complément, jamais la source principale.
    """
    if ui_scale <= 0:
        raise ValueError(f"échelle d'interface invalide : {ui_scale}")

    width = round(_TRACKER_WIDTH * ui_scale)
    height = round(_TRACKER_HEIGHT * ui_scale)
    left = max(window.left, window.right - round(_TRACKER_MARGIN_RIGHT * ui_scale) - width)
    top = window.top + round(_TRACKER_TOP * ui_scale)
    return Rect(
        left=left,
        top=min(top, window.bottom),
        width=min(width, window.right - left),
        height=min(height, max(0, window.bottom - top)),
    )


def banner_region(window: Rect, ui_scale: float = 1.0) -> Rect:
    """Rectangle du bandeau de quête, dans les coordonnées de l'écran.

    `ui_scale` reprend le réglage d'échelle de l'interface du jeu. À 1.0, ce
    sont les mesures relevées sur l'écran de référence.

    Le rectangle est rogné aux bords de la fenêtre : une échelle trop grande ou
    une fenêtre trop petite donnerait sinon des coordonnées hors écran, que la
    capture refuserait avec une erreur système peu parlante.

    ⚠️ Vérifié en 1440p seulement. L'ancrage au coin devrait tenir aux autres
    résolutions puisque l'interface garde sa taille en pixels, mais ce n'est
    pas mesuré. Sur un écran différent, le réglage manuel de la zone reste le
    recours.
    """
    if ui_scale <= 0:
        raise ValueError(f"échelle d'interface invalide : {ui_scale}")

    width = round(_BANNER_WIDTH * ui_scale)
    height = round(_BANNER_HEIGHT * ui_scale)
    right_margin = round(_MARGIN_RIGHT * ui_scale)
    bottom_margin = round(_MARGIN_BOTTOM * ui_scale)

    left = window.right - right_margin - width
    top = window.bottom - bottom_margin - height

    # Rognage aux bords de la fenêtre.
    left = max(window.left, left)
    top = max(window.top, top)
    return Rect(
        left=left,
        top=top,
        width=min(width, window.right - left),
        height=min(height, window.bottom - top),
    )
