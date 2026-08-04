from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from chrono.capture import GrayFrame
from chrono.reading import BannerKind
from chrono.watching import BannerWatcher, frame_difference

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def banner() -> GrayFrame:
    """Vraie capture de la zone, bandeau « Nouvelle quête » affiché."""
    with Image.open(DATA / "banner_present.png") as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


@pytest.fixture
def chat(banner: GrayFrame) -> GrayFrame:
    """Zone sans bandeau. Du bruit suffit : ce qui compte est que l'icône
    du bandeau n'y soit pas, donc que la corrélation soit basse."""
    return np.random.default_rng(1789).integers(0, 256, banner.shape, dtype=np.uint8)


class ScriptedSource:
    """Source qui rejoue une suite d'images fixée d'avance."""

    def __init__(self, frames: list[GrayFrame]) -> None:
        self._frames = frames
        self.index = 0

    def grab_gray(self) -> GrayFrame:
        frame = self._frames[min(self.index, len(self._frames) - 1)]
        self.index += 1
        return frame


class ScriptedReader:
    """Moteur de reconnaissance factice, qui compte ses appels."""

    def __init__(self, lines: list[tuple[str, float]] | None = None) -> None:
        self.lines = lines if lines is not None else [
            ("Nouvelle quete", 0.99),
            ("[Calpheon] Cris stridents des harpies", 0.98),
        ]
        self.calls = 0

    def read(self, image: GrayFrame) -> list[tuple[str, float]]:
        self.calls += 1
        return self.lines


def altered(frame: GrayFrame, amount: int) -> GrayFrame:
    """Même image, contenu textuel changé : simule un autre bandeau.

    Seule la partie droite est modifiée, là où vit le texte. L'icône reste
    intacte, sans quoi la détection de présence dirait « plus de bandeau » et
    on testerait le mauvais chemin.
    """
    copy = frame.copy()
    copy[:, 100:] = np.clip(copy[:, 100:].astype(np.int16) + amount, 0, 255).astype(np.uint8)
    return copy


class TestFrameDifference:
    def test_vaut_zero_pour_deux_images_identiques(self) -> None:
        image = np.full((4, 4), 100, dtype=np.uint8)
        assert frame_difference(image, image) == 0.0

    def test_mesure_l_ecart_moyen(self) -> None:
        a = np.zeros((4, 4), dtype=np.uint8)
        b = np.full((4, 4), 10, dtype=np.uint8)
        assert frame_difference(a, b) == pytest.approx(10.0)

    def test_traite_l_absence_d_image_comme_du_mouvement(self) -> None:
        # L'infini ne franchit aucun seuil vers le bas : au premier tour, rien
        # ne peut être déclaré immobile, donc rien n'est lu trop tôt.
        assert frame_difference(None, np.zeros((4, 4), dtype=np.uint8)) == float("inf")

    def test_traite_un_changement_de_taille_comme_du_mouvement(self) -> None:
        a = np.zeros((4, 4), dtype=np.uint8)
        b = np.zeros((8, 8), dtype=np.uint8)
        assert frame_difference(a, b) == float("inf")


class TestBannerWatcher:
    def test_ne_lit_rien_sans_bandeau(self, chat: GrayFrame) -> None:
        reader = ScriptedReader()
        watcher = BannerWatcher(ScriptedSource([chat] * 10), reader)
        assert list(watcher.watch(max_polls=10)) == []
        assert reader.calls == 0

    def test_attend_que_l_image_cesse_de_bouger(self, banner: GrayFrame) -> None:
        # Le bandeau arrive en fondu : lire pendant l'animation donne du texte
        # à moitié transparent et des résultats aberrants.
        reader = ScriptedReader()
        watcher = BannerWatcher(ScriptedSource([banner]), reader)
        assert watcher.poll() is None  # première image : rien à comparer
        assert reader.calls == 0
        assert watcher.poll() is None  # une seule image immobile ne suffit pas
        assert watcher.poll() is not None

    def test_lit_le_bandeau_une_seule_fois(self, banner: GrayFrame) -> None:
        """Régression : le bandeau reste affiché plusieurs secondes.

        À huit captures par seconde, s'en remettre à la seule présence du
        bandeau le ferait relire une quarantaine de fois, soit une quarantaine
        de reconnaissances à 300 millisecondes pour un seul événement, et
        autant de mesures en double dans le journal.
        """
        reader = ScriptedReader()
        watcher = BannerWatcher(ScriptedSource([banner] * 40), reader)
        lectures = list(watcher.watch(max_polls=40))
        assert len(lectures) == 1
        assert reader.calls == 1
        assert lectures[0].kind is BannerKind.ACCEPTED

    def test_relit_apres_disparition_puis_reapparition(
        self, banner: GrayFrame, chat: GrayFrame
    ) -> None:
        reader = ScriptedReader()
        frames = [banner] * 5 + [chat] * 3 + [banner] * 5
        watcher = BannerWatcher(ScriptedSource(frames), reader)
        assert len(list(watcher.watch(max_polls=len(frames)))) == 2

    def test_relit_quand_un_bandeau_en_remplace_un_autre(self, banner: GrayFrame) -> None:
        """Régression : deux bandeaux qui s'enchaînent sans blanc entre eux.

        Quand le joueur enchaîne les quêtes vite, « Quête accomplie » est
        remplacé directement par « Nouvelle quête » sans que la zone se vide.
        Une détection fondée sur la disparition du bandeau raterait le second
        et perdrait le départ du chronomètre.
        """
        reader = ScriptedReader()
        frames = [banner] * 4 + [altered(banner, 60)] * 4
        watcher = BannerWatcher(ScriptedSource(frames), reader)
        assert len(list(watcher.watch(max_polls=len(frames)))) == 2

    def test_ne_relit_pas_une_image_qui_a_juste_fremi(self, banner: GrayFrame) -> None:
        # Le bandeau est semi-transparent : le décor qui bouge derrière fait
        # varier ses pixels sans qu'aucun texte n'ait changé.
        reader = ScriptedReader()
        frames = [banner] * 4 + [altered(banner, 2)] * 6
        watcher = BannerWatcher(ScriptedSource(frames), reader)
        assert len(list(watcher.watch(max_polls=len(frames)))) == 1

    def test_ne_retente_pas_une_lecture_ratee_sur_la_meme_image(
        self, banner: GrayFrame
    ) -> None:
        # Une lecture qui n'aboutit pas ne doit pas être relancée à chaque
        # tour : ce serait 300 millisecondes gaspillées huit fois par seconde.
        reader = ScriptedReader(lines=[("texte inconnu", 0.99), ("autre chose", 0.98)])
        watcher = BannerWatcher(ScriptedSource([banner] * 20), reader)
        assert list(watcher.watch(max_polls=20)) == []
        assert reader.calls == 1

    def test_rend_compte_de_son_economie(self, banner: GrayFrame, chat: GrayFrame) -> None:
        reader = ScriptedReader()
        frames = [chat] * 10 + [banner] * 30
        watcher = BannerWatcher(ScriptedSource(frames), reader)
        list(watcher.watch(max_polls=len(frames)))
        assert watcher.stats.frames == 40
        assert watcher.stats.banners_seen == 30
        assert watcher.stats.reads == 1
        assert watcher.stats.readings == 1
        # C'est la mesure qui dit si l'économie fonctionne.
        assert watcher.stats.read_ratio < 0.05

    def test_borne_le_nombre_de_tours(self, chat: GrayFrame) -> None:
        watcher = BannerWatcher(ScriptedSource([chat]), ScriptedReader())
        list(watcher.watch(max_polls=7))
        assert watcher.stats.frames == 7
