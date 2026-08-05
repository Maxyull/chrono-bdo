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


#: Bornes de l'étirement de contraste, en centiles. Écarter les extrêmes évite
#: qu'un unique pixel très clair, un reflet ou une icône, n'écrase tout le
#: reste de l'échelle.
STRETCH_PERCENTILES: tuple[float, float] = (2.0, 98.0)


def stretch_contrast(
    frame: GrayFrame, percentiles: tuple[float, float] = STRETCH_PERCENTILES
) -> GrayFrame:
    """Étale la luminance de l'image sur toute la plage disponible.

    Sans cela, rien n'est lisible dans les scènes sombres. Le panneau de suivi
    de quête n'a aucun fond opaque derrière son texte, contrairement au bandeau
    qui repose sur une barre : sa lisibilité dépend entièrement du décor.
    Mesuré en jeu de nuit, la zone entière plafonnait à 19 sur 255, et la
    reconnaissance n'y trouvait **aucune** ligne. Après étirement, neuf.

    L'opération est sans effet notable sur une image déjà contrastée, elle ne
    coûte donc rien de la faire toujours.

    Une image uniforme est rendue telle quelle : il n'y a rien à étaler, et
    diviser par son amplitude nulle n'aurait pas de sens.
    """
    low, high = np.percentile(frame, percentiles)
    if high <= low:
        return frame
    stretched = (frame.astype(np.float32) - low) * (255.0 / (high - low))
    clipped: GrayFrame = np.clip(stretched, 0, 255).astype(np.uint8)
    return clipped


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
        # L'étirement d'abord, l'agrandissement ensuite : étaler la luminance
        # sur une image déjà agrandie donnerait le même résultat pour quatre
        # fois plus de pixels à parcourir.
        enlarged = upscale(stretch_contrast(image), self._factor)
        # Le moteur attend trois canaux ; la zone est en niveaux de gris depuis
        # la capture, on la réempile plutôt que de la recapturer en couleur.
        rgb = np.stack([enlarged] * 3, axis=-1)
        result, _ = engine(rgb)  # type: ignore[operator]
        if not result:
            return []
        return [(str(text).strip(), float(score)) for _, text, score in result]
