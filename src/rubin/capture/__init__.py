"""Capture de la zone du bandeau de quête à l'écran.

Trois étapes séparées pour que la seule qui contienne de la logique soit
vérifiable sans écran :

1. `window` trouve la fenêtre du jeu (Windows, interface système) ;
2. `region` calcule où se trouve le bandeau dans cette fenêtre (calcul pur) ;
3. `screen` capture ce rectangle en niveaux de gris.
"""

from .banner import (
    ICON_SEARCH,
    ICON_SIZE,
    ICON_TOP,
    PRESENCE_THRESHOLD,
    banner_score,
    correlation,
    has_banner,
    icon_template,
    locate_icon,
)
from .region import REFERENCE_SIZE, Rect, banner_region, tracker_region
from .screen import ColorFrame, Grabber, GrayFrame, ScreenCapture
from .window import TITLE_FRAGMENTS, find_game_window

__all__ = [
    "ICON_SEARCH",
    "ICON_SIZE",
    "ICON_TOP",
    "PRESENCE_THRESHOLD",
    "REFERENCE_SIZE",
    "TITLE_FRAGMENTS",
    "ColorFrame",
    "Grabber",
    "GrayFrame",
    "Rect",
    "ScreenCapture",
    "banner_region",
    "banner_score",
    "correlation",
    "find_game_window",
    "has_banner",
    "icon_template",
    "locate_icon",
    "tracker_region",
]
