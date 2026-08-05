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

⚠️ **Cette dernière comparaison ne porte pas sur l'image entière**, et c'est le
défaut qui faisait perdre des quêtes quand le joueur enchaînait vite. Voir
`banner_change` : la moyenne sur toute la zone est diluée par le décor, qui
occupe la majeure partie des pixels et ne dit rien du bandeau.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np

from .capture import (
    ICON_SIZE,
    ICON_TOP,
    PRESENCE_THRESHOLD,
    GrayFrame,
    locate_icon,
)
from .reading import BannerReading, TextReader, parse_banner

#: Différence moyenne par pixel en dessous de laquelle l'image est jugée
#: immobile. Assez haut pour ignorer le bruit de compression du jeu, assez bas
#: pour ne pas déclarer stable un fondu en cours.
STABLE_DIFF: Final = 3.0

#: Nombre d'images consécutives immobiles avant de lire. À huit images par
#: seconde, deux images représentent un quart de seconde : imperceptible pour
#: le joueur, suffisant pour laisser passer un fondu.
MIN_STABLE_FRAMES: Final = 2

#: Au-delà, on considère qu'un autre bandeau a pris la place du précédent.
#:
#: ⚠️ **Ce seuil s'applique à `banner_change`, pas à `frame_difference`.** Il
#: valait 8,0 sur la moyenne de la zone entière, et cette mesure est diluée : le
#: décor occupe la majeure partie des pixels et ne change pas quand le nom de la
#: quête change. Mesuré sur les vingt minutes de jeu du 5 août 2026, **huit
#: paires de bandeaux voisins sur vingt-huit** passaient sous 8,0 alors que les
#: deux bandeaux étaient bel et bien différents, la plus faible à **2,15**. Le
#: cas le plus net est le passage de « Quête accomplie / [Mediah] Les marchands
#: d'Altinova II » à « Nouvelle quête / [Mediah] Les marchands d'Altinova III » :
#: **2,54 sur la zone entière**, donc un départ de quête jamais compté.
#:
#: Sur `banner_change`, ces mêmes vingt-huit paires sortent toutes au-dessus de
#: **6,78**. Le seuil est posé à 5,0, soit un quart de marge sous la plus faible
#: valeur réellement observée.
#:
#: L'asymétrie décide du sens de l'erreur : **relire un bandeau déjà lu ne coûte
#: qu'un peu de calcul**, la mesure suivante écrasant la précédente pour la même
#: quête, alors que **rater un bandeau coûte une quête entière**. Le risque du
#: côté généreux est de noyer la file de lecture, et il est borné : sur cette
#: même session, un bandeau n'est présent à l'écran que 5 à 11 % du temps, donc
#: **relire absolument toutes** les images qui en portent un donnerait 0,4 à
#: 0,9 lecture par seconde à huit images par seconde, contre 1 à 3 que le moteur
#: soutient, avec les 500 places de `MAX_PENDING` comme matelas.
NEW_BANNER_DIFF: Final = 5.0


def frame_difference(a: GrayFrame | None, b: GrayFrame) -> float:
    """Différence absolue moyenne par pixel, de 0 à 255.

    Renvoie l'infini quand les images ne sont pas comparables. Une valeur
    infinie ne franchit aucun seuil vers le bas : une image de taille
    inattendue est donc traitée comme du mouvement, jamais comme du repos.
    """
    if a is None or a.shape != b.shape or b.size == 0:
        return float("inf")
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))


def banner_change(a: GrayFrame | None, b: GrayFrame, icon_x: int) -> float:
    """De combien le **bandeau** a changé, sans compter le décor autour.

    C'est la mesure qui répond à « est-ce un autre bandeau ? », et la moyenne
    sur la zone entière ne savait pas y répondre. Deux corrections, chacune
    mesurée sur les vingt minutes de jeu du 5 août 2026.

    **On ne regarde que la barre du bandeau.** Elle occupe les mêmes lignes que
    son icône, dont la hauteur ne bouge pas d'un bandeau à l'autre, et s'étend
    de l'icône jusqu'au bord droit. Tout le reste de la zone est du décor, ou du
    chat de guilde que la barre opaque masque justement sur ces lignes. Le décor
    est la majeure partie des pixels et il ne dit rien de la quête : le compter
    revient à noyer le seul signal utile.

    ⚠️ **Ni la largeur ni la hauteur de la zone n'apparaissent ici.** Le
    découpage vient de l'icône, retrouvée par glissement, exactement comme la
    détection de présence. Un seuil d'abscisse calé sur des captures est le
    deuxième piège du projet, et la barre du bandeau se déplace de 150 pixels
    d'une quête à l'autre puisqu'elle s'adapte à la longueur du nom.

    **On retient la ligne qui a le plus changé, pas la moyenne des lignes.** Un
    bandeau ne se distingue du précédent que par son titre et par son nom, soit
    deux ou trois lignes de texte sur la cinquantaine que compte la barre. Faire
    la moyenne les dilue ; prendre le maximum les laisse parler.

    Ce que ça donne sur les vingt-huit paires de bandeaux voisins de la session
    réelle, toutes différentes deux à deux :

    | Mesure | Plus faible valeur observée | Paires sous 8,0 |
    |---|---|---|
    | moyenne de la zone entière | 2,15 | **8 sur 28** |
    | moyenne de la bande du nom | 0,84 | pire encore |
    | maximum par ligne sur la barre | **6,78** | 0 sur 28 |

    La bande du nom seule, qui semblait la piste évidente, est **la pire des
    trois** : deux quêtes qui se suivent dans une chaîne portent souvent le même
    nom à un chiffre romain près, et c'est le titre, « Quête accomplie » puis
    « Nouvelle quête », qui porte alors toute la différence.

    Renvoie l'infini quand les images ne sont pas comparables, comme
    `frame_difference` : une valeur infinie ne franchit aucun seuil vers le bas,
    donc une image inattendue est toujours traitée comme un nouveau bandeau.
    Une zone trop petite pour contenir la barre retombe sur l'image entière,
    faute de mieux, plutôt que de comparer un découpage vide qui vaudrait zéro
    et déclarerait « déjà lu » pour toujours.
    """
    if a is None or a.shape != b.shape or b.size == 0:
        return float("inf")
    top, bottom, left = ICON_TOP, ICON_TOP + ICON_SIZE, icon_x + ICON_SIZE
    bar_a, bar_b = a[top:bottom, left:], b[top:bottom, left:]
    if bar_a.size == 0:
        return frame_difference(a, b)
    rows = np.mean(np.abs(bar_a.astype(np.float32) - bar_b.astype(np.float32)), axis=1)
    return float(rows.max())


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
    #: Captures rigoureusement identiques à la précédente, pixel pour pixel.
    #:
    #: Doit rester très bas. Le jeu redessine en permanence, et même un
    #: personnage immobile a de l'herbe qui bouge : deux captures successives
    #: rendues identiques signalent que la capture **répète une image déjà
    #: prise** au lieu d'en produire une neuve.
    #:
    #: Ajouté après la séance du 5 août 2026, où une session a trouvé 2 images
    #: avec bandeau là où un témoin extérieur en trouvait 47 sur la même zone et
    #: la même période. Les images gardées à l'aveugle ont prouvé que la zone
    #: était la bonne et le jeu bien vivant dedans ; il ne restait que le
    #: soupçon d'images répétées, et rien pour le mesurer.
    repeats: int = 0

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
        #: La dernière image capturée, quelle qu'ait été la décision prise.
        #:
        #: Gardée pour un seul usage : quand une session ne voit **aucun**
        #: bandeau pendant longtemps, c'est la seule façon de savoir ce que sa
        #: capture contient vraiment. Toutes les autres images retenues par le
        #: projet ont franchi le seuil de présence ; celle-ci est là justement
        #: parce qu'elle ne l'a pas franchi.
        self.last_frame: GrayFrame | None = None

    def _bump(self, **changes: int) -> None:
        current = {
            "frames": self.stats.frames,
            "banners_seen": self.stats.banners_seen,
            "reads": self.stats.reads,
            "readings": self.stats.readings,
            "repeats": self.stats.repeats,
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
        # Comparée AVANT d'écraser la précédente. `array_equal` sur 40 kilooctets
        # coûte quelques dizaines de microsecondes, soit trois ordres de grandeur
        # sous le glissement de l'icône qui suit.
        if self.last_frame is not None and np.array_equal(self.last_frame, frame):
            self._bump(repeats=1)
        self.last_frame = frame
        self._bump(frames=1)

        # L'icône est cherchée une fois et sa position resservie plus bas, pour
        # découper la barre du bandeau. `has_banner` la chercherait à nouveau,
        # et ce glissement est la partie coûteuse du tour : 10 des 14
        # millisecondes.
        score, icon_x = locate_icon(frame)
        if score < PRESENCE_THRESHOLD:
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

        if banner_change(self._last_read, frame, icon_x) < self._new_banner_diff:
            return None  # même bandeau qu'à la dernière lecture

        # On note l'image avant de connaître le résultat de sa lecture : une
        # lecture qui échoue ne doit pas être retentée à chaque tour.
        #
        # ⚠️ Ça retient donc aussi les bandeaux saisis pendant leur animation
        # d'entrée, dont le titre sort tronqué, « Quete acc » ou « Nou », et qui
        # ne correspondent à aucun titre connu. Vingt et un cas sur la session
        # du 5 août 2026. Ces images-là n'apportent rien, et pire, elles
        # servaient de référence au bandeau posé qui suivait : mesuré sur une
        # paire réelle, 7,66 sur la zone entière, donc **sous l'ancien seuil de
        # 8,0**, et le bandeau posé était perdu. Sur `banner_change` la même
        # paire vaut 17,31, très au-dessus des 5,0.
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
