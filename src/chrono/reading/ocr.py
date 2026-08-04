"""Reconnaissance de caractères sur la zone du bandeau.

Le moteur est isolé derrière un protocole pour deux raisons. Il est lent à
charger, plusieurs secondes au premier appel, et tout le reste du logiciel
peut être vérifié sans lui, avec des lignes de texte écrites à la main.

C'est la partie coûteuse du travail : 300 à 600 millisecondes par lecture,
contre 4 pour une capture. D'où la règle de la boucle de surveillance, qui
capture souvent et ne reconnaît qu'au moment utile.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from ..capture import GrayFrame

#: Le texte du bandeau fait environ 18 pixels de haut en 1440p. La
#: reconnaissance travaille nettement mieux au-delà de 30 : l'agrandissement
#: n'ajoute aucune information, mais il évite au moteur de trancher sur des
#: traits d'un pixel.
UPSCALE: int = 2


class TextReader(Protocol):
    """Ce que la lecture attend d'un moteur de reconnaissance."""

    def read(self, image: GrayFrame) -> list[tuple[str, float]]:
        """Lignes reconnues, de haut en bas, avec leur score de 0 à 1."""
        ...


def upscale(frame: GrayFrame, factor: int = UPSCALE) -> GrayFrame:
    """Agrandit par répétition de pixels.

    Volontairement sans interpolation : elle adoucirait des contours que la
    reconnaissance utilise, pour un coût plus élevé.
    """
    if factor <= 1:
        return frame
    return np.repeat(np.repeat(frame, factor, axis=0), factor, axis=1)


class RapidOcrReader:
    """Moteur par défaut, entièrement installable par pip.

    Choisi pour la même raison que dans butin : aucun binaire système à
    télécharger à part, aucune variable d'environnement à régler à la main.
    """

    def __init__(self, factor: int = UPSCALE) -> None:
        self._factor = factor
        self._engine: object | None = None

    def _ensure_engine(self) -> object:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def read(self, image: GrayFrame) -> list[tuple[str, float]]:
        engine = self._ensure_engine()
        enlarged = upscale(image, self._factor)
        # Le moteur attend trois canaux ; la zone est en niveaux de gris depuis
        # la capture, on la réempile plutôt que de la recapturer en couleur.
        rgb = np.stack([enlarged] * 3, axis=-1)
        result, _ = engine(rgb)  # type: ignore[operator]
        if not result:
            return []
        return [(str(text).strip(), float(score)) for _, text, score in result]
