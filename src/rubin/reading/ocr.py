"""Reconnaissance de caractères sur la zone du bandeau.

Le moteur est isolé derrière un protocole pour deux raisons. Il est lent à
charger, plusieurs secondes au premier appel, et tout le reste du logiciel
peut être vérifié sans lui, avec des lignes de texte écrites à la main.

C'est la partie coûteuse du travail : 300 à 600 millisecondes par lecture,
contre 4 pour une capture. D'où la règle de la boucle de surveillance, qui
capture souvent et ne reconnaît qu'au moment utile.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from ..capture import GrayFrame

#: Le texte du bandeau fait environ 18 pixels de haut en 1440p. La
#: reconnaissance travaille nettement mieux au-delà de 30 : l'agrandissement
#: n'ajoute aucune information, mais il évite au moteur de trancher sur des
#: traits d'un pixel.
UPSCALE: int = 2


@dataclass(frozen=True)
class TextLine:
    """Une ligne reconnue, avec la boîte qui l'entoure.

    Les coordonnées sont celles de l'**image d'origine**, pas de l'image
    agrandie que le moteur a réellement vue : le facteur d'agrandissement est
    un détail de la reconnaissance, que personne d'autre n'a à connaître.

    Cette boîte est ce qui sépare le bandeau du chat du jeu. Le moteur la rend
    depuis toujours ; elle était jetée sur place, et sans elle deux textes
    superposés à l'écran arrivent mélangés, sans rien pour dire lequel vient
    d'où.
    """

    text: str
    score: float
    #: Bords de la boîte, en pixels de l'image d'origine.
    left: float
    right: float
    top: float
    bottom: float

    @property
    def middle(self) -> float:
        """Abscisse du milieu de la ligne.

        C'est elle qui décide de l'appartenance au bandeau, plutôt qu'un bord :
        un bord se compare mal entre une ligne longue et une ligne courte,
        alors que le milieu dit simplement dans quelle colonne la ligne se
        trouve.
        """
        return (self.left + self.right) / 2.0


class TextReader(Protocol):
    """Ce que la lecture attend d'un moteur de reconnaissance."""

    def read(self, image: GrayFrame) -> list[tuple[str, float]]:
        """Lignes reconnues, de haut en bas, avec leur score de 0 à 1."""
        ...


@runtime_checkable
class BoxedTextReader(Protocol):
    """Un moteur qui sait dire **où** il a lu chaque ligne.

    Volontairement un second point d'entrée, et non un changement de ce que
    rend `TextReader.read`. Ce protocole-là est employé par le panneau de suivi,
    par le choix automatique de zone et par la fenêtre : leur imposer une
    géométrie dont ils n'ont que faire aurait touché tout le logiciel pour le
    besoin d'un seul appelant, l'analyse du bandeau.
    """

    def read_boxed(self, image: GrayFrame) -> list[TextLine]:
        """Lignes reconnues, avec la boîte de chacune."""
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
        return [(line.text, line.score) for line in self.read_boxed(image)]

    def read_boxed(self, image: GrayFrame) -> list[TextLine]:
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
        # Les boîtes sont rendues dans l'échelle de l'image agrandie. On les
        # ramène à celle de l'image d'origine, seule échelle que connaissent la
        # zone tracée par le joueur et les vignettes gardées en cas d'échec.
        scale = float(max(1, self._factor))
        lines: list[TextLine] = []
        for box, text, score in result:
            xs = [float(point[0]) / scale for point in box]
            ys = [float(point[1]) / scale for point in box]
            lines.append(
                TextLine(
                    text=str(text).strip(),
                    score=float(score),
                    left=min(xs),
                    right=max(xs),
                    top=min(ys),
                    bottom=max(ys),
                )
            )
        return lines


def read_lines(reader: TextReader, image: GrayFrame) -> list[TextLine]:
    """Lit une image, avec les boîtes si le moteur sait les rendre.

    Les moteurs écrits pour les tests ne rendent que du texte et un score, et
    c'est très bien ainsi : la géométrie n'a de sens que face à une vraie image.
    Ils reçoivent alors une géométrie **neutre**, où toutes les lignes occupent
    la même colonne et se suivent de haut en bas. Le filtre de colonne ne
    rejette rien dans ce cas, ce qui est le comportement voulu : sans boîte, on
    ne sait rien, et deviner reviendrait à jeter des lignes au hasard.
    """
    if isinstance(reader, BoxedTextReader):
        return reader.read_boxed(image)
    return neutral_lines(reader.read(image))


def neutral_lines(lines: Iterable[tuple[str, float]]) -> list[TextLine]:
    """Des lignes sans géométrie connue, rangées dans une colonne unique.

    Le rang tient lieu d'ordonnée : c'est le seul ordre dont on dispose quand
    on n'a que du texte, et c'est celui de la lecture, de haut en bas.
    """
    return [
        TextLine(
            text=text,
            score=score,
            left=0.0,
            right=1.0,
            top=float(rank),
            bottom=float(rank) + 1.0,
        )
        for rank, (text, score) in enumerate(lines)
    ]
