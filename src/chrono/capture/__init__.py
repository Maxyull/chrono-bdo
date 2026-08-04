"""Capture de la zone du bandeau de quête à l'écran.

Trois étapes séparées pour que la seule qui contienne de la logique soit
vérifiable sans écran :

1. `window` trouve la fenêtre du jeu (Windows, interface système) ;
2. `region` calcule où se trouve le bandeau dans cette fenêtre (calcul pur) ;
3. `screen` capture ce rectangle en niveaux de gris.
"""

from .region import REFERENCE_SIZE, Rect, banner_region
from .screen import Grabber, GrayFrame, ScreenCapture
from .window import TITLE_FRAGMENTS, find_game_window

__all__ = [
    "REFERENCE_SIZE",
    "TITLE_FRAGMENTS",
    "Grabber",
    "GrayFrame",
    "Rect",
    "ScreenCapture",
    "banner_region",
    "find_game_window",
]
