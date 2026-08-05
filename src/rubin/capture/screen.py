"""Capture d'une zone de l'écran, en niveaux de gris.

La capture est la partie bon marché du travail : quelques millisecondes pour la
zone du bandeau. C'est la reconnaissance de caractères qui coûte, entre 300 et
600 millisecondes, et c'est pour cela qu'on capture souvent mais qu'on ne
reconnaît que quand l'image a changé.

La conversion en niveaux de gris a lieu ici, une fois, parce que tout ce qui
suit travaille sur la luminance : la comparaison d'images comme la
reconnaissance. Garder la couleur ne servirait qu'à tripler la mémoire.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import numpy as np
import numpy.typing as npt

from .region import Rect

if TYPE_CHECKING:
    from types import TracebackType

#: Une image en niveaux de gris, valeurs de 0 à 255.
GrayFrame = npt.NDArray[np.uint8]

#: Coefficients de luminance de la recommandation UIT-R BT.601. La moyenne
#: simple des trois canaux donnerait un gris où le texte cyan du bandeau
#: « Quête accomplie » ressort moins que sa lisibilité réelle à l'œil.
_LUMA = np.array([0.114, 0.587, 0.299], dtype=np.float32)  # ordre BGRA de mss


class Grabber(Protocol):
    """Ce que la capture attend de sa source d'images.

    Un protocole plutôt qu'une dépendance directe à `mss` : le reste du code
    devient vérifiable avec une source d'images factice, sans écran, donc en
    intégration continue.
    """

    def grab(self, region: dict[str, int]) -> object: ...


class ScreenCapture:
    """Capture répétée d'une même zone."""

    def __init__(self, region: Rect, grabber: Grabber | None = None) -> None:
        self._region = region
        self._grabber = grabber
        self._owns_grabber = grabber is None

    @property
    def region(self) -> Rect:
        return self._region

    def _ensure_grabber(self) -> Grabber:
        if self._grabber is None:
            import mss

            self._grabber = mss.mss()
        return self._grabber

    def grab_gray(self) -> GrayFrame:
        """Capture la zone et la rend en niveaux de gris."""
        raw = self._ensure_grabber().grab(self._region.to_mss())
        pixels = np.asarray(raw, dtype=np.uint8)
        if pixels.ndim == 2:  # source déjà en niveaux de gris
            return pixels
        return (pixels[..., :3] @ _LUMA).astype(np.uint8)

    def close(self) -> None:
        # Une source fournie de l'extérieur appartient à l'appelant : on ne
        # ferme que celle qu'on a ouverte soi-même.
        if self._owns_grabber and self._grabber is not None:
            closer = getattr(self._grabber, "close", None)
            if closer is not None:
                closer()
            self._grabber = None

    def __enter__(self) -> ScreenCapture:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
