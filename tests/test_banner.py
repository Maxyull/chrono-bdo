from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from chrono.capture import (
    PRESENCE_THRESHOLD,
    GrayFrame,
    banner_score,
    correlation,
    has_banner,
    icon_template,
)

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def banner_frame() -> GrayFrame:
    """Une vraie capture de la zone, bandeau « Nouvelle quête » affiché."""
    with Image.open(DATA / "banner_present.png") as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


class TestCorrelation:
    def test_vaut_un_pour_deux_images_identiques(self) -> None:
        image = np.arange(64, dtype=np.uint8).reshape(8, 8)
        assert correlation(image, image) == pytest.approx(1.0)

    def test_ignore_un_changement_de_luminosite(self) -> None:
        # C'est la propriété qui rend l'indice utilisable : le bandeau est
        # semi-transparent, donc sa clarté dépend du décor derrière le joueur.
        image = np.arange(64, dtype=np.uint8).reshape(8, 8)
        assombrie = (image // 2).astype(np.uint8)
        assert correlation(image, assombrie) == pytest.approx(1.0, abs=0.01)

    def test_vaut_zero_pour_une_image_uniforme(self) -> None:
        # La corrélation n'est pas définie sans relief. Zéro est le bon défaut :
        # une image plate ne ressemble à rien, et surtout pas au bandeau.
        image = np.arange(64, dtype=np.uint8).reshape(8, 8)
        plate = np.full((8, 8), 128, dtype=np.uint8)
        assert correlation(image, plate) == 0.0

    def test_vaut_zero_pour_des_tailles_differentes(self) -> None:
        a = np.zeros((8, 8), dtype=np.uint8)
        b = np.zeros((4, 4), dtype=np.uint8)
        assert correlation(a, b) == 0.0

    def test_est_negative_pour_une_image_inversee(self) -> None:
        image = np.arange(64, dtype=np.uint8).reshape(8, 8)
        assert correlation(image, (255 - image).astype(np.uint8)) == pytest.approx(-1.0)


class TestBannerDetection:
    def test_reconnait_un_bandeau_reel(self, banner_frame: GrayFrame) -> None:
        """Régression : une capture avec bandeau doit dépasser 0,99.

        Mesuré sur douze captures du jeu, neuf avec bandeau et trois sans : la
        corrélation vaut au moins 0,994 quand un bandeau est affiché, et au
        plus 0,022 quand la zone ne montre que le chat du jeu.

        Sans cet indice, la surveillance se déclencherait sur le défilement du
        chat et lancerait la reconnaissance des milliers de fois par heure pour
        lire des conversations de guilde.
        """
        assert banner_score(banner_frame) > 0.99
        assert has_banner(banner_frame)

    def test_ecarte_du_bruit(self) -> None:
        bruit = np.random.default_rng(1789).integers(0, 256, (115, 349), dtype=np.uint8)
        assert not has_banner(bruit)

    def test_ecarte_une_image_uniforme(self) -> None:
        assert not has_banner(np.full((115, 349), 40, dtype=np.uint8))

    def test_ecarte_une_capture_trop_petite(self) -> None:
        # Une fenêtre de jeu minuscule donne une zone rognée : mieux vaut
        # répondre « pas de bandeau » que lever une erreur d'indice.
        assert not has_banner(np.zeros((10, 10), dtype=np.uint8))

    def test_le_seuil_laisse_de_la_marge_des_deux_cotes(self, banner_frame: GrayFrame) -> None:
        # Le seuil ne départage rien de ce qui a été observé, ce qui est le
        # signe que sa valeur exacte n'a pas d'importance.
        assert 0.03 < PRESENCE_THRESHOLD < 0.99
        assert banner_score(banner_frame) > PRESENCE_THRESHOLD


class TestIconTemplate:
    def test_a_la_taille_attendue(self) -> None:
        assert icon_template().shape == (55, 55)

    def test_n_est_pas_uniforme(self) -> None:
        # Un gabarit sans relief rendrait la corrélation toujours nulle, et la
        # détection ne dirait plus jamais oui, en silence.
        assert icon_template().std() > 10
