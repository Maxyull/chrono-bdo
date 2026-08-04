from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from chrono.capture import GrayFrame
from chrono.deferred import DeferredWatcher
from chrono.reading import BannerKind
from chrono.watching import BannerWatcher

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def banner() -> GrayFrame:
    with Image.open(DATA / "banner_present.png") as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


class LoopingSource:
    """Rend toujours la même image, en comptant les captures."""

    def __init__(self, frame: GrayFrame) -> None:
        self.frame = frame
        self.grabs = 0

    def grab_gray(self) -> GrayFrame:
        self.grabs += 1
        return self.frame


class SlowReader:
    """Moteur lent, pour vérifier que la capture n'attend pas la lecture."""

    def __init__(self, delay: float = 0.3) -> None:
        self.delay = delay
        self.calls = 0

    def read(self, image: GrayFrame) -> list[tuple[str, float]]:
        self.calls += 1
        time.sleep(self.delay)
        return [("Nouvelle quete", 0.99), ("[Calpheon] Cris stridents des harpies", 0.98)]


def build(
    frame: GrayFrame, delay: float = 0.3
) -> tuple[DeferredWatcher, LoopingSource, SlowReader]:
    source = LoopingSource(frame)
    reader = SlowReader(delay)
    watcher = BannerWatcher(source, reader)
    return DeferredWatcher(watcher, reader, interval=0.01), source, reader


class TestDeferredWatcher:
    def test_continue_de_capturer_pendant_une_lecture_lente(self, banner: GrayFrame) -> None:
        """Régression : la boucle simple cesse de regarder pendant qu'elle lit.

        Une reconnaissance prend de 300 à 1 000 millisecondes, durant
        lesquelles l'écran n'est pas surveillé. Un bandeau qui apparaît et
        disparaît dans cet intervalle est perdu sans que rien ne le signale, et
        c'est justement quand le joueur enchaîne vite que le risque est le plus
        grand.
        """
        deferred, source, _ = build(banner, delay=0.4)
        with deferred:
            time.sleep(0.5)
            captures_pendant_la_lecture = source.grabs
        # À un centième de seconde par tour, une lecture de 4 dixièmes laisse
        # largement le temps de plusieurs dizaines de captures.
        assert captures_pendant_la_lecture > 10

    def test_lit_ce_qui_a_ete_capture(self, banner: GrayFrame) -> None:
        deferred, _, _ = build(banner, delay=0.01)
        with deferred:
            time.sleep(0.2)
            lues = []
            for reading, at in deferred.readings(timeout=0.5):
                lues.append((reading, at))
                break
        assert lues
        assert lues[0][0].kind is BannerKind.ACCEPTED

    def test_horodate_a_la_capture_et_non_a_la_lecture(self, banner: GrayFrame) -> None:
        # C'est l'instant où le bandeau est apparu à l'écran qui compte, pas
        # celui où le logiciel a fini d'y réfléchir. Confondre les deux
        # allongerait chaque mesure de la durée de sa propre lecture.
        deferred, _, _ = build(banner, delay=0.3)
        with deferred:
            time.sleep(0.1)
            frames = deferred.take_pending()
            assert frames
            capture = frames[0].at
        assert capture < time.monotonic()

    def test_ne_lit_qu_une_fois_un_bandeau_qui_reste_affiche(self, banner: GrayFrame) -> None:
        deferred, _, reader = build(banner, delay=0.01)
        with deferred:
            time.sleep(0.3)
        assert reader.calls <= 1
        assert deferred.pending_count <= 1

    def test_s_arrete_proprement(self, banner: GrayFrame) -> None:
        deferred, source, _ = build(banner, delay=0.01)
        deferred.start()
        time.sleep(0.05)
        deferred.stop()
        arrivees = source.grabs
        time.sleep(0.1)
        # Plus aucune capture après l'arrêt.
        assert source.grabs == arrivees

    def test_demarrer_deux_fois_ne_lance_qu_un_fil(self, banner: GrayFrame) -> None:
        deferred, _, _ = build(banner, delay=0.01)
        deferred.start()
        deferred.start()
        try:
            time.sleep(0.05)
        finally:
            deferred.stop()
        assert deferred.overflowed == 0

    def test_borne_la_file_sans_se_taire(self, banner: GrayFrame) -> None:
        # La file ne doit pas gonfler sans fin si la lecture s'effondre, mais
        # les pertes doivent se voir plutôt que de disparaître en silence.
        deferred, _, _ = build(banner, delay=0.01)
        deferred._pending.extend(deferred.take_pending())
        assert deferred.overflowed == 0
