"""Localisation de la fenêtre du jeu.

Le bandeau est repéré par rapport à la fenêtre du jeu, pas à l'écran : sur
plusieurs écrans, ou en mode fenêtré, les deux ne coïncident pas.

Windows uniquement, par l'interface système, sans dépendance supplémentaire.
Sur les autres systèmes, la recherche renvoie `None` plutôt que d'échouer, ce
qui permet aux tests et à l'intégration continue de tourner sur Linux.
"""

from __future__ import annotations

import sys
from typing import Final

from .region import Rect

#: Fragments cherchés dans le titre de la fenêtre, en minuscules. Le client
#: français et le client anglais portent le même titre, mais il a changé au fil
#: des versions du jeu, d'où plusieurs candidats.
TITLE_FRAGMENTS: Final = ("black desert",)


def _windows_rect(fragment: str) -> Rect | None:
    """Cherche une fenêtre visible dont le titre contient `fragment`."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found: list[Rect] = []

    def visit(handle: int, _param: int) -> bool:
        if not user32.IsWindowVisible(handle):
            return True
        length = user32.GetWindowTextLengthW(handle)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buffer, length + 1)
        if fragment not in buffer.value.lower():
            return True
        rect = wintypes.RECT()
        if not user32.GetClientRect(handle, ctypes.byref(rect)):
            return True
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(handle, ctypes.byref(origin))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width > 0 and height > 0:
            found.append(Rect(origin.x, origin.y, width, height))
        return False  # Arrête l'énumération : la première fenêtre suffit.

    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(visit)
    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def find_game_window(fragments: tuple[str, ...] = TITLE_FRAGMENTS) -> Rect | None:
    """Rectangle de la zone client du jeu, ou `None` s'il n'est pas trouvé.

    La **zone client** est renvoyée, pas la fenêtre entière : elle exclut la
    bordure et la barre de titre en mode fenêtré. C'est elle qui correspond à
    l'image du jeu, donc aux coordonnées du bandeau. En plein écran sans
    bordure, les deux coïncident.
    """
    if sys.platform != "win32":
        return None
    for fragment in fragments:
        rect = _windows_rect(fragment.lower())
        if rect is not None:
            return rect
    return None
