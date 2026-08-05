from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rubin.capture import ICON_SIZE, ICON_TOP, GrayFrame, locate_icon
from rubin.reading import BannerKind
from rubin.watching import NEW_BANNER_DIFF, BannerWatcher, banner_change, frame_difference

DATA = Path(__file__).parent / "data"


def _load(name: str) -> GrayFrame:
    with Image.open(DATA / name) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


@pytest.fixture(scope="session")
def banner() -> GrayFrame:
    """Vraie capture de la zone, bandeau « Nouvelle quête » affiché."""
    return _load("banner_present.png")


@pytest.fixture(scope="session")
def chaine_fin() -> GrayFrame:
    """Vraie capture, 5 août 2026 à 13:45:00.

    « Quête accomplie / [Mediah] Les marchands d'Altinova II ».
    """
    return _load("banner_chaine_fin.png")


@pytest.fixture(scope="session")
def chaine_debut() -> GrayFrame:
    """Vraie capture, 5 août 2026 à 13:45:02, deux secondes après la précédente.

    « Nouvelle quête / [Mediah] Les marchands d'Altinova III ». Rien entre les
    deux dans le journal d'observation : ce sont bien deux bandeaux voisins.
    """
    return _load("banner_chaine_debut.png")


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


class TestBannerChange:
    def test_vaut_zero_pour_deux_images_identiques(self, banner: GrayFrame) -> None:
        assert banner_change(banner, banner, locate_icon(banner)[1]) == 0.0

    def test_ignore_ce_qui_change_hors_de_la_barre(self, banner: GrayFrame) -> None:
        """Le décor au-dessus et en dessous du bandeau ne dit rien de la quête.

        C'est exactement ce que la moyenne sur la zone entière comptait, et ce
        qui la rendait aveugle : ces pixels sont les plus nombreux.
        """
        autre = banner.copy()
        autre[: ICON_TOP - 1] = 255
        autre[ICON_TOP + ICON_SIZE + 1 :] = 255
        assert banner_change(autre, banner, locate_icon(banner)[1]) == 0.0
        # La mesure sur la zone entière, elle, se serait affolée.
        assert frame_difference(autre, banner) > 50.0

    def test_retient_la_ligne_qui_a_le_plus_change(self, banner: GrayFrame) -> None:
        # Une seule ligne de texte modifiée sur la cinquantaine de la barre :
        # la moyenne la dilue, le maximum par ligne la voit.
        autre = banner.copy()
        ligne = ICON_TOP + ICON_SIZE // 2
        autre[ligne, :] = np.clip(autre[ligne, :].astype(np.int16) + 40, 0, 255)
        icon_x = locate_icon(banner)[1]
        assert banner_change(autre, banner, icon_x) == pytest.approx(40.0)
        assert frame_difference(autre, banner) < 1.0

    def test_traite_l_absence_d_image_comme_un_nouveau_bandeau(
        self, banner: GrayFrame
    ) -> None:
        assert banner_change(None, banner, 0) == float("inf")

    def test_traite_un_changement_de_taille_comme_un_nouveau_bandeau(
        self, banner: GrayFrame
    ) -> None:
        assert banner_change(np.zeros((8, 8), dtype=np.uint8), banner, 0) == float("inf")

    def test_retombe_sur_l_image_entiere_quand_la_zone_est_trop_petite(self) -> None:
        # Un découpage vide vaudrait zéro, donc « déjà lu » pour toujours, et la
        # surveillance ne lirait plus jamais rien sans que rien ne le dise.
        a = np.zeros((4, 4), dtype=np.uint8)
        b = np.full((4, 4), 10, dtype=np.uint8)
        assert banner_change(a, b, 0) == pytest.approx(10.0)

    def test_separe_deux_bandeaux_reels_que_la_zone_entiere_confondait(
        self, chaine_fin: GrayFrame, chaine_debut: GrayFrame
    ) -> None:
        """Régression : « ça va trop vite et certaines quêtes ne sont pas comptées ».

        Signalé par Maxime en jouant le 5 août 2026, puis retrouvé dans les
        images d'une session réelle. À 13:45:00 le jeu affiche « Quête accomplie
        / [Mediah] Les marchands d'Altinova II », à 13:45:02 « Nouvelle quête /
        [Mediah] Les marchands d'Altinova III ». Deux bandeaux voisins, rien
        entre eux dans le journal d'observation.

        Sur la zone entière ils ne diffèrent que de **2,54**, très en dessous
        des 8,0 d'alors : le second était pris pour le premier, et le départ de
        la quête suivante n'était **jamais compté**. Sur les vingt minutes
        observées, huit paires voisines sur vingt-huit étaient dans ce cas.

        La bande du nom seule, qui semblait la piste évidente, aurait donné
        **0,84**, donc pire : les deux quêtes portent le même nom à un chiffre
        romain près, et toute la différence est dans le titre.

        Sur la barre du bandeau, ligne par ligne, la même paire donne **34,95**.
        """
        icon_x = locate_icon(chaine_debut)[1]
        assert frame_difference(chaine_fin, chaine_debut) == pytest.approx(2.54, abs=0.01)
        assert banner_change(chaine_fin, chaine_debut, icon_x) == pytest.approx(
            34.95, abs=0.01
        )
        assert banner_change(chaine_fin, chaine_debut, icon_x) > NEW_BANNER_DIFF


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

    def test_compte_les_deux_quetes_d_un_enchainement_reel(
        self, chaine_fin: GrayFrame, chaine_debut: GrayFrame
    ) -> None:
        """Régression : deux vrais bandeaux voisins, séparés de deux secondes.

        Les mêmes captures que `test_separe_deux_bandeaux_reels_...`, passées
        cette fois par la boucle entière. Avec l'ancienne mesure, 2,54 sur la
        zone entière contre un seuil de 8,0, la boucle ne rendait **qu'une
        seule** lecture : « Nouvelle quête / [Mediah] Les marchands d'Altinova
        III » était prise pour le « Quête accomplie » qui la précédait, et le
        chronomètre de cette quête ne démarrait jamais.
        """
        reader = ScriptedReader()
        frames = [chaine_fin] * 4 + [chaine_debut] * 4
        watcher = BannerWatcher(ScriptedSource(frames), reader)
        assert len(list(watcher.watch(max_polls=len(frames)))) == 2
        assert reader.calls == 2

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


class TestImagesRepetees:
    """Le compteur de captures identiques à la précédente.

    Ajouté après la séance du 5 août 2026 : une session a trouvé 2 bandeaux là
    où un témoin extérieur, sur la même zone et la même période, en trouvait
    47. Les images gardées à l'aveugle (#67) ont montré la bonne zone sur le
    jeu vivant, écartant une capture périmée ou mal placée. Il ne restait que
    le soupçon d'une capture qui répète une image déjà prise, et rien pour le
    mesurer.
    """

    def test_deux_images_identiques_comptent_une_repetition(self, chat: GrayFrame) -> None:
        source = ScriptedSource([chat, chat.copy(), chat.copy()])
        guetteur = BannerWatcher(source, ScriptedReader([]))

        for _ in range(3):
            guetteur.capture_pending()

        assert guetteur.stats.repeats == 2

    def test_des_images_qui_changent_ne_comptent_aucune_repetition(
        self, chat: GrayFrame
    ) -> None:
        rng = np.random.default_rng(2026)
        images = [rng.integers(0, 256, chat.shape, dtype=np.uint8) for _ in range(5)]
        source = ScriptedSource(images)
        guetteur = BannerWatcher(source, ScriptedReader([]))

        for _ in range(5):
            guetteur.capture_pending()

        assert guetteur.stats.repeats == 0

    def test_regression_le_cas_du_5_aout_une_capture_qui_stagne(
        self, chat: GrayFrame
    ) -> None:
        """Régression : ce que verrait le compteur sur une capture qui stagne.

        Le fait mesuré ce jour-là : un témoin voyait 47 bandeaux sur une
        période où la session n'en trouvait que 2, sur la même zone. Si la
        capture avait rendu la même image en boucle au lieu d'en produire une
        neuve à chaque tour, c'est exactement ce chiffre qui l'aurait montré
        AVANT d'écrire cinq programmes de diagnostic hors du logiciel.

        Le test fige la propriété attendue d'un tel cas : un taux de
        répétition proche de 100 %, et non quelques pourcents de bruit normal.
        """
        source = ScriptedSource([chat] * 40)  # la même image, quarante fois
        guetteur = BannerWatcher(source, ScriptedReader([]))

        for _ in range(40):
            guetteur.capture_pending()

        assert guetteur.stats.repeats == 39
        assert guetteur.stats.repeats / guetteur.stats.frames > 0.9
