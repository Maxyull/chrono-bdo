from __future__ import annotations

import numpy as np
import pytest

from rubin.capture import REFERENCE_SIZE, Rect, ScreenCapture, banner_region, find_game_window
from rubin.capture.window import GAME_EXECUTABLES, Candidate, choose_window


class FakeGrabber:
    """Source d'images factice : rend l'image qu'on lui donne, en BGRA.

    Permet de vérifier la capture sans écran, donc en intégration continue.
    """

    def __init__(self, image: np.ndarray) -> None:
        self.image = image
        self.calls: list[dict[str, int]] = []

    def grab(self, region: dict[str, int]) -> object:
        self.calls.append(region)
        return self.image


class TestRect:
    def test_calcule_ses_bords(self) -> None:
        rect = Rect(10, 20, 100, 50)
        assert (rect.right, rect.bottom) == (110, 70)

    def test_se_traduit_pour_la_capture(self) -> None:
        assert Rect(1, 2, 3, 4).to_mss() == {"left": 1, "top": 2, "width": 3, "height": 4}


class TestBannerRegion:
    def test_retrouve_la_zone_verifiee_en_1440p(self) -> None:
        """Régression : la zone doit valoir exactement (2210, 1185, 349, 115).

        C'est le rectangle sur lequel la reconnaissance a été mesurée, et qui a
        rendu neuf bandeaux sur neuf avec des scores de 0,95 à 1,0. Un décalage
        de quelques dizaines de pixels vers le haut ramène le panneau d'infos
        du jeu dans le cadre, et la reconnaissance se met à lire le chat de
        guilde en croyant lire des noms de quêtes.
        """
        window = Rect(0, 0, *REFERENCE_SIZE)
        assert banner_region(window) == Rect(2210, 1185, 349, 115)

    def test_suit_la_fenetre_quand_elle_n_est_pas_a_l_origine(self) -> None:
        # Deuxième écran, ou mode fenêtré : la zone est relative à la fenêtre.
        window = Rect(1920, 100, *REFERENCE_SIZE)
        region = banner_region(window)
        assert (region.left, region.top) == (1920 + 2210, 100 + 1185)

    def test_reste_ancree_au_coin_inferieur_droit(self) -> None:
        # L'interface du jeu garde sa taille en pixels : à résolution
        # différente, c'est la distance au coin qui est conservée, pas la
        # proportion de l'écran.
        region = banner_region(Rect(0, 0, 1920, 1080))
        assert region.right == 1920
        assert region.bottom == 1080 - 139

    def test_grandit_avec_l_echelle_d_interface(self) -> None:
        window = Rect(0, 0, *REFERENCE_SIZE)
        normale = banner_region(window)
        agrandie = banner_region(window, ui_scale=1.5)
        assert agrandie.width > normale.width
        assert agrandie.height > normale.height

    def test_ne_sort_jamais_de_la_fenetre(self) -> None:
        # Une échelle absurde sur une petite fenêtre donnerait des coordonnées
        # négatives, que la capture refuserait avec une erreur système
        # incompréhensible.
        region = banner_region(Rect(0, 0, 200, 150), ui_scale=4.0)
        assert region.left >= 0
        assert region.top >= 0
        assert region.right <= 200
        assert region.bottom <= 150

    @pytest.mark.parametrize("scale", [0.0, -1.0])
    def test_refuse_une_echelle_absurde(self, scale: float) -> None:
        with pytest.raises(ValueError, match="échelle"):
            banner_region(Rect(0, 0, *REFERENCE_SIZE), ui_scale=scale)


class TestScreenCapture:
    def test_capture_la_zone_demandee(self) -> None:
        grabber = FakeGrabber(np.zeros((4, 4, 4), dtype=np.uint8))
        capture = ScreenCapture(Rect(10, 20, 4, 4), grabber=grabber)
        capture.grab_gray()
        assert grabber.calls == [{"left": 10, "top": 20, "width": 4, "height": 4}]

    def test_convertit_en_niveaux_de_gris(self) -> None:
        # mss sert du BGRA. Un rouge pur vaut 76 en luminance BT.601, pas 85 :
        # une moyenne des trois canaux donnerait un gris où le texte coloré du
        # bandeau ressort autrement qu'à l'œil.
        rouge = np.zeros((1, 1, 4), dtype=np.uint8)
        rouge[..., 2] = 255
        gris = ScreenCapture(Rect(0, 0, 1, 1), grabber=FakeGrabber(rouge)).grab_gray()
        assert gris.shape == (1, 1)
        assert gris[0, 0] == 76

    def test_accepte_une_source_deja_en_gris(self) -> None:
        image = np.full((2, 2), 128, dtype=np.uint8)
        gris = ScreenCapture(Rect(0, 0, 2, 2), grabber=FakeGrabber(image)).grab_gray()
        assert np.array_equal(gris, image)

    def test_ne_ferme_pas_une_source_qui_ne_lui_appartient_pas(self) -> None:
        grabber = FakeGrabber(np.zeros((1, 1, 4), dtype=np.uint8))
        with ScreenCapture(Rect(0, 0, 1, 1), grabber=grabber) as capture:
            capture.grab_gray()
        # La source vient de l'appelant : elle doit rester utilisable après.
        assert capture.grab_gray().shape == (1, 1)


class TestFindGameWindow:
    def test_ne_trouve_rien_pour_un_titre_absent(self) -> None:
        # Vérifiable partout : sur Linux la recherche rend None sans erreur,
        # sur Windows aucune fenêtre ne porte ce titre. Le cas important est
        # qu'une absence se traduise par None et non par une exception, sans
        # quoi le logiciel s'arrêterait dès que le jeu n'est pas lancé.
        assert find_game_window(("fenetre qui n'existe pas 4f3c9a",)) is None


def _fenetre(executable: str | None, titre: str, largeur: int, hauteur: int) -> Candidate:
    return Candidate(rect=Rect(0, 0, largeur, hauteur), title=titre, executable=executable)


#: Les deux fenêtres relevées ensemble sur le poste de développement, telles
#: quelles. Les tailles et les titres sont ceux qui ont été mesurés.
CHROME = _fenetre(
    "chrome.exe",
    "(3) RETOUR SUR BLACK DESERT ! 10ANS DU JEU, SERAPH - YouTube - Google Chrome",
    2560,
    1392,
)
JEU = _fenetre("blackdesert64.exe", "BLACK DESERT - 526388", 2560, 1440)


class TestChooseWindow:
    def test_ecarte_le_navigateur_qui_affiche_une_video_du_jeu(self) -> None:
        """Régression : la recherche rendait la fenêtre de Chrome.

        Relevé sur le poste de développement, les deux fenêtres ouvertes en même
        temps. Chrome jouait une vidéo intitulée « RETOUR SUR BLACK DESERT ! ...
        - YouTube », donc son titre contenait le fragment cherché. La recherche
        s'arrêtait à la première fenêtre trouvée, dans l'ordre d'affichage, et
        rendait donc celle du navigateur.

        La conséquence était la pire possible : `rubin verifier` répondait
        « fenêtre du jeu... 2560x1392 » puis « tout est en ordre », et la
        session qui suivait capturait un coin de navigateur sans jamais rien
        mesurer ni dire pourquoi. Un joueur de Black Desert qui regarde une
        vidéo de Black Desert n'est pas un cas tordu, c'est le cas courant.

        C'est désormais le programme propriétaire qui tranche, jamais le titre.
        """
        assert choose_window([CHROME, JEU]) == JEU.rect
        # Et dans l'autre sens : l'ordre d'énumération ne doit plus rien décider.
        assert choose_window([JEU, CHROME]) == JEU.rect

    def test_ne_rend_rien_quand_seul_un_autre_programme_correspond(self) -> None:
        # Mieux vaut dire que le jeu est introuvable que désigner une fenêtre au
        # hasard : une zone capturée au mauvais endroit ne lève aucune erreur,
        # elle produit une session muette.
        assert choose_window([CHROME]) is None

    def test_garde_une_fenetre_dont_le_programme_est_illisible(self) -> None:
        # Le client tourne parfois avec des privilèges plus élevés que Rubin, à
        # cause de son anti-triche, et l'interrogation du processus échoue. Une
        # fenêtre inconnue reste un candidat de dernier recours.
        inconnue = _fenetre(None, "Black Desert", 2560, 1440)
        assert choose_window([CHROME, inconnue]) == inconnue.rect

    def test_le_jeu_l_emporte_sur_une_fenetre_inconnue(self) -> None:
        inconnue = _fenetre(None, "Black Desert - guide", 3840, 2160)
        # Plus grande, et pourtant écartée : la certitude prime sur la taille.
        assert choose_window([inconnue, JEU]) == JEU.rect

    def test_a_egalite_la_plus_grande_gagne(self) -> None:
        # Le client ouvre parfois une fenêtre secondaire, écran de lancement ou
        # boîte de dialogue. C'est la surface de jeu qui nous intéresse.
        lanceur = _fenetre("blackdesert64.exe", "Black Desert", 800, 600)
        assert choose_window([lanceur, JEU]) == JEU.rect

    def test_ne_rend_rien_sans_candidat(self) -> None:
        assert choose_window([]) is None


class TestCandidate:
    def test_reconnait_les_executables_du_jeu(self) -> None:
        assert JEU.is_game
        assert not JEU.is_other_program

    def test_un_autre_programme_est_identifie_comme_tel(self) -> None:
        assert not CHROME.is_game
        assert CHROME.is_other_program

    def test_un_programme_illisible_n_est_accuse_de_rien(self) -> None:
        # Ni le jeu, ni « un autre programme » : on ne sait pas, et c'est
        # cette nuance qui permet de le garder en dernier recours.
        inconnue = _fenetre(None, "Black Desert", 2560, 1440)
        assert not inconnue.is_game
        assert not inconnue.is_other_program

    @pytest.mark.parametrize("nom", GAME_EXECUTABLES)
    def test_toutes_les_variantes_connues_sont_acceptees(self, nom: str) -> None:
        assert _fenetre(nom, "Black Desert", 2560, 1440).is_game
