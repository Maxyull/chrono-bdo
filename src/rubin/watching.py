"""La boucle de surveillance : capturer souvent, ne lire qu'au bon moment.

Elle existe pour une raison d'économie. Une capture coûte 4 millisecondes, la
reconnaissance de caractères entre 300 et 600. On capture donc huit fois par
seconde, et on ne reconnaît que dans le seul cas utile : un bandeau est
affiché, il a fini d'apparaître, et ce n'est pas celui qu'on vient déjà de lire.

Trois questions se posent à chaque tour, et chacune a sa réponse mesurée sur
des captures réelles.

**Y a-t-il un bandeau ?** Sans lui, la zone montre le chat du jeu, qui défile
en permanence. La corrélation de forme de l'icône répond, avec 0,97 de marge.

**A-t-il fini d'apparaître ?** Le bandeau arrive en fondu. Lire pendant
l'animation donne du texte à moitié transparent et des résultats aberrants. On
attend donc que l'image cesse de bouger.

**Est-ce un nouveau bandeau ?** C'est la question difficile, et elle vient du
jeu réel : quand on enchaîne les quêtes vite, un bandeau en remplace un autre
sans disparaître entre les deux. Se fier à sa disparition raterait ces
enchaînements ; se fier à son contenu confondrait deux étapes successives de la
même quête, qui affichent exactement le même texte. On compare donc l'image à
celle de la dernière lecture : si elle a changé alors qu'un bandeau est
toujours là, c'est qu'un autre a pris sa place.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np

from .capture import GrayFrame, has_banner
from .reading import BannerReading, TextReader, parse_banner

#: Différence moyenne par pixel en dessous de laquelle l'image est jugée
#: immobile. Assez haut pour ignorer le bruit de compression du jeu, assez bas
#: pour ne pas déclarer stable un fondu en cours.
STABLE_DIFF: Final = 3.0

#: Nombre d'images consécutives immobiles avant de lire. À huit images par
#: seconde, deux images représentent un quart de seconde : imperceptible pour
#: le joueur, suffisant pour laisser passer un fondu.
MIN_STABLE_FRAMES: Final = 2

#: Différence moyenne par pixel au-delà de laquelle on considère qu'un autre
#: bandeau a pris la place du précédent. Plus élevé que le seuil d'immobilité :
#: il s'agit de repérer un changement de contenu, pas un frémissement.
NEW_BANNER_DIFF: Final = 8.0


def frame_difference(a: GrayFrame | None, b: GrayFrame) -> float:
    """Différence absolue moyenne par pixel, de 0 à 255.

    Renvoie l'infini quand les images ne sont pas comparables. Une valeur
    infinie ne franchit aucun seuil vers le bas : une image de taille
    inattendue est donc traitée comme du mouvement, jamais comme du repos.
    """
    if a is None or a.shape != b.shape or b.size == 0:
        return float("inf")
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))


class FrameSource(Protocol):
    """Ce que la surveillance attend de sa source d'images."""

    def grab_gray(self) -> GrayFrame: ...


@dataclass(frozen=True)
class WatchStats:
    """De quoi comprendre ce que la boucle a fait, sans la déranger."""

    frames: int = 0
    banners_seen: int = 0
    reads: int = 0
    readings: int = 0

    @property
    def read_ratio(self) -> float:
        """Part des captures qui ont déclenché une reconnaissance.

        C'est la mesure qui dit si l'économie fonctionne. Elle doit rester
        basse : une valeur qui monte signale que la boucle relit sans cesse le
        même écran, donc qu'un réglage est à revoir.
        """
        return self.reads / self.frames if self.frames else 0.0


class BannerWatcher:
    """Surveille la zone du bandeau et rend les lectures, une par bandeau."""

    def __init__(
        self,
        source: FrameSource,
        reader: TextReader,
        stable_diff: float = STABLE_DIFF,
        min_stable_frames: int = MIN_STABLE_FRAMES,
        new_banner_diff: float = NEW_BANNER_DIFF,
    ) -> None:
        self._source = source
        self._reader = reader
        self._stable_diff = stable_diff
        self._min_stable_frames = max(1, min_stable_frames)
        self._new_banner_diff = new_banner_diff
        self._previous: GrayFrame | None = None
        self._last_read: GrayFrame | None = None
        self._stable_run = 0
        self.stats = WatchStats()

    def _bump(self, **changes: int) -> None:
        current = {
            "frames": self.stats.frames,
            "banners_seen": self.stats.banners_seen,
            "reads": self.stats.reads,
            "readings": self.stats.readings,
        }
        for key, value in changes.items():
            current[key] += value
        self.stats = WatchStats(**current)

    def capture_pending(self) -> GrayFrame | None:
        """Capture, et renvoie l'image **si elle mérite d'être lue**.

        Toute la décision est ici, et rien de coûteux : une capture à 4
        millisecondes et une corrélation à 10. Séparer cette décision de la
        lecture permet de différer celle-ci, qui prend entre 300 et 1 000
        millisecondes pendant lesquelles l'écran ne serait pas surveillé.
        """
        frame = self._source.grab_gray()
        self._bump(frames=1)

        if not has_banner(frame):
            # Plus de bandeau : la prochaine apparition sera forcément nouvelle.
            self._previous = None
            self._last_read = None
            self._stable_run = 0
            return None

        self._bump(banners_seen=1)
        moved = frame_difference(self._previous, frame)
        self._previous = frame

        if moved > self._stable_diff:
            self._stable_run = 0  # apparition en fondu, ou contenu qui change
            return None
        self._stable_run += 1
        if self._stable_run < self._min_stable_frames:
            return None

        if frame_difference(self._last_read, frame) < self._new_banner_diff:
            return None  # même bandeau qu'à la dernière lecture

        # On note l'image avant de connaître le résultat de sa lecture : une
        # lecture qui échoue ne doit pas être retentée à chaque tour.
        self._last_read = frame
        self._bump(reads=1)
        return frame

    def poll(self) -> BannerReading | None:
        """Un tour de boucle, capture et lecture enchaînées.

        `None` est le cas normal : la grande majorité des tours ne voit aucun
        bandeau, ou voit celui qui a déjà été lu.
        """
        frame = self.capture_pending()
        if frame is None:
            return None
        reading = parse_banner(self._reader.read(frame))
        if reading is not None:
            self._bump(readings=1)
        return reading

    def watch(self, max_polls: int | None = None) -> Iterator[BannerReading]:
        """Boucle sans fin, rendant chaque bandeau lu.

        `max_polls` borne le nombre de tours, ce qui rend la boucle vérifiable.
        La cadence n'est pas gérée ici : elle appartient à l'appelant, qui sait
        s'il veut dormir entre deux tours ou rejouer un enregistrement.
        """
        polls = 0
        while max_polls is None or polls < max_polls:
            polls += 1
            reading = self.poll()
            if reading is not None:
                yield reading
