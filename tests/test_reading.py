from __future__ import annotations

import numpy as np
import pytest

from chrono.reading import BannerKind, is_known_title, parse_banner, upscale
from chrono.reading.ocr import stretch_contrast

#: Sorties **réelles** du moteur de reconnaissance sur les captures du jeu,
#: recopiées telles quelles, défauts compris. Ce ne sont pas des exemples
#: fabriqués : c'est ce que le logiciel recevra.
REAL_READINGS: list[tuple[list[tuple[str, float]], BannerKind, str]] = [
    (
        [("Objectif de quete accompli", 0.98), ("[Calpheon] Jeron,la tacticienne", 0.95)],
        BannerKind.OBJECTIVE_DONE,
        "[Calpheon] Jeron,la tacticienne",
    ),
    (
        [("Quete accomplie", 0.97), ("[Calpheon] Jeron,la tacticienne", 0.95)],
        BannerKind.COMPLETED,
        "[Calpheon] Jeron,la tacticienne",
    ),
    (
        [
            ("Nouvelle quete", 0.99),
            ("[Calpheon] Cris stridents des", 0.99),
            ("harpies", 0.99),
        ],
        BannerKind.ACCEPTED,
        "[Calpheon] Cris stridents des harpies",
    ),
    (
        [
            ("Objectif de quete partielle...", 0.99),
            ("[Calpheon] Cris stridents des", 0.98),
            ("harpies", 0.99),
        ],
        BannerKind.PARTIAL,
        "[Calpheon] Cris stridents des harpies",
    ),
    (
        [
            ("Nouvelle quete", 0.99),
            ("[Calpheon] Coup de main tant", 0.97),
            ("F", 0.59),
            ("desiré", 0.91),
        ],
        BannerKind.ACCEPTED,
        "[Calpheon] Coup de main tant desiré",
    ),
]

#: Ce que la zone montre quand aucun bandeau n'est affiché : le chat du jeu.
CHAT_LINES = [
    ("de guilde terminees avant la maintenance,", 0.97),
    ("ront pas de Renommee de guilde. (21:45)", 0.97),
    ("a jour de contenu. (21:45)", 0.93),
]


class TestParseBanner:
    @pytest.mark.parametrize(("lines", "kind", "name"), REAL_READINGS)
    def test_lit_les_bandeaux_reels(
        self, lines: list[tuple[str, float]], kind: BannerKind, name: str
    ) -> None:
        reading = parse_banner(lines)
        assert reading is not None
        assert reading.kind is kind
        assert reading.quest_name == name

    def test_recolle_un_nom_sur_deux_lignes(self) -> None:
        reading = parse_banner(
            [("Nouvelle quete", 0.99), ("[Calpheon] Cris stridents des", 0.99), ("harpies", 0.99)]
        )
        assert reading is not None
        assert reading.quest_name == "[Calpheon] Cris stridents des harpies"

    def test_ecarte_un_artefact_de_faible_score(self) -> None:
        """Régression : un « F » à 0,59 s'insérait au milieu d'un nom.

        Relevé sur une capture réelle : le moteur invente une ligne à partir
        d'un bord d'icône. Sans filtrage, le nom devenait « Coup de main tant
        F desiré », que le catalogue ne pouvait plus résoudre, et la mesure
        était perdue sans que rien ne signale pourquoi.
        """
        reading = parse_banner(
            [
                ("Nouvelle quete", 0.99),
                ("[Calpheon] Coup de main tant", 0.97),
                ("F", 0.59),
                ("desiré", 0.91),
            ]
        )
        assert reading is not None
        assert "F" not in reading.quest_name.split()

    def test_distingue_objectif_accompli_de_quete_accomplie(self) -> None:
        # Les deux titres se ressemblent, et les confondre inverserait le sens
        # de la mesure : l'un est une étape, l'autre est la fin.
        objectif = parse_banner([("Objectif de quete accompli", 0.98), ("[X] Une quete", 0.95)])
        quete = parse_banner([("Quete accomplie", 0.97), ("[X] Une quete", 0.95)])
        assert objectif is not None and objectif.kind is BannerKind.OBJECTIVE_DONE
        assert quete is not None and quete.kind is BannerKind.COMPLETED

    def test_reconnait_un_titre_tronque(self) -> None:
        # Le jeu tronque « Objectif de quête partiellement accompli » selon la
        # place disponible : le titre est donc comparé par son début.
        reading = parse_banner(
            [("Objectif de quete partielle...", 0.99), ("[X] Une quete", 0.95)]
        )
        assert reading is not None
        assert reading.kind is BannerKind.PARTIAL

    def test_ne_lit_rien_dans_le_chat_du_jeu(self) -> None:
        assert parse_banner(CHAT_LINES) is None

    def test_ne_lit_rien_sans_nom_de_quete(self) -> None:
        assert parse_banner([("Nouvelle quete", 0.99)]) is None

    def test_ne_lit_rien_sans_titre_connu(self) -> None:
        assert parse_banner([("Bonjour aventurier", 0.99), ("[X] Une quete", 0.95)]) is None

    def test_refuse_une_lecture_globalement_douteuse(self) -> None:
        # Toutes les lignes passent le seuil ligne à ligne, mais l'ensemble
        # reste trop incertain pour entrer dans une médiane.
        assert parse_banner([("Nouvelle quete", 0.78), ("[X] Une quete", 0.77)]) is None

    def test_retient_le_score_le_plus_faible(self) -> None:
        # C'est le maillon faible qui compte : un titre lu à 0,99 ne rachète
        # pas un nom mal lu, et c'est le nom qui identifie la quête.
        reading = parse_banner([("Nouvelle quete", 0.99), ("[X] Une quete", 0.85)])
        assert reading is not None
        assert reading.confidence == pytest.approx(0.85)

    def test_ignore_les_lignes_vides(self) -> None:
        lignes = [("Nouvelle quete", 0.99), ("   ", 0.99), ("[X] Une", 0.95)]
        assert parse_banner(lignes) is not None


class TestKnownTitle:
    @pytest.mark.parametrize(
        "titre",
        ["Nouvelle quête", "Quête accomplie", "Objectif de quête accompli", "NOUVELLE QUETE"],
    )
    def test_reconnait_les_titres_du_jeu(self, titre: str) -> None:
        assert is_known_title(titre)

    def test_ne_reconnait_pas_un_message_de_chat(self) -> None:
        assert not is_known_title("de guilde terminees avant la maintenance,")


class TestUpscale:
    def test_double_les_dimensions(self) -> None:
        assert upscale(np.zeros((10, 20), dtype=np.uint8), 2).shape == (20, 40)

    def test_ne_touche_a_rien_au_facteur_un(self) -> None:
        image = np.arange(4, dtype=np.uint8).reshape(2, 2)
        assert np.array_equal(upscale(image, 1), image)

    def test_repete_les_pixels_sans_les_adoucir(self) -> None:
        # Sans interpolation : elle adoucirait des contours que la
        # reconnaissance utilise, pour un coût plus élevé.
        agrandie = upscale(np.array([[0, 255]], dtype=np.uint8), 2)
        assert set(np.unique(agrandie)) == {0, 255}


class TestStretchContrast:
    def test_etale_une_image_sombre_sur_toute_la_plage(self) -> None:
        """Régression : le panneau de suivi est illisible de nuit.

        Contrairement au bandeau, qui repose sur une barre, le panneau n'a
        aucun fond opaque derrière son texte : sa lisibilité dépend entièrement
        du décor. Mesuré en jeu de nuit, la zone entière plafonnait à 19 sur
        255 et la reconnaissance n'y trouvait aucune ligne. Après étirement,
        neuf.
        """
        sombre = np.linspace(0, 19, 100, dtype=np.uint8).reshape(10, 10)
        etiree = stretch_contrast(sombre)
        assert etiree.max() > 240
        assert etiree.min() < 15

    def test_ne_change_presque_rien_a_une_image_deja_contrastee(self) -> None:
        # C'est ce qui permet de l'appliquer toujours, sans se demander si
        # l'image en a besoin.
        contrastee = np.linspace(0, 255, 100, dtype=np.uint8).reshape(10, 10)
        assert np.abs(stretch_contrast(contrastee).astype(int) - contrastee.astype(int)).max() < 20

    def test_rend_une_image_uniforme_telle_quelle(self) -> None:
        # Il n'y a rien à étaler, et diviser par une amplitude nulle n'aurait
        # pas de sens.
        plate = np.full((8, 8), 42, dtype=np.uint8)
        assert np.array_equal(stretch_contrast(plate), plate)

    def test_resiste_a_un_pixel_aberrant(self) -> None:
        # Un reflet ou un bord d'icône ne doit pas écraser toute l'échelle,
        # d'où les bornes en centiles plutôt que le minimum et le maximum.
        # Sans elles, ce seul pixel à 255 laisserait le texte sombre inchangé.
        image = np.linspace(0, 20, 400, dtype=np.uint8).reshape(20, 20)
        image[0, 0] = 255
        etiree = stretch_contrast(image)
        assert etiree.max() > 200
        assert etiree.std() > image.std() * 5
