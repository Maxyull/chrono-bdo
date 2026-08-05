"""Le tracé d'une zone sur une capture, et sa conversion en coordonnées d'écran.

C'est exactement le genre de calcul qui se trompe d'un facteur ou d'une origine
sans lever la moindre erreur : on obtient une zone plausible, au mauvais
endroit, et le logiciel ne mesure plus rien sans dire pourquoi.
"""

from __future__ import annotations

import pytest

from rubin.capture import Rect
from rubin.interface.picker import MAX_PREVIEW, normalise, scale_for, to_game

#: L'écran du poste de développement, second moniteur à gauche du principal,
#: donc en coordonnées négatives. Relevé tel quel.
JEU = Rect(-1280, -17, 2560, 1440)


class TestEchelle:
    def test_ne_reduit_pas_une_petite_fenetre(self) -> None:
        assert scale_for(Rect(0, 0, 800, 600)) == 1.0

    def test_reduit_une_grande_fenetre_sous_la_limite(self) -> None:
        échelle = scale_for(JEU)
        assert échelle < 1.0
        assert JEU.width * échelle == pytest.approx(MAX_PREVIEW)


class TestNormalisation:
    def test_un_trace_ordinaire(self) -> None:
        assert normalise(10, 20, 60, 90) == Rect(10, 20, 50, 70)

    def test_un_trace_a_l_envers_donne_le_meme_rectangle(self) -> None:
        """Régression : tracer vers le haut à gauche donnait une largeur négative.

        On trace aussi bien de bas à droite vers haut à gauche. Sans
        normalisation, la zone était rejetée à la relecture comme « plate », et
        le joueur croyait avoir mal cliqué alors que son tracé était bon.
        """
        assert normalise(60, 90, 10, 20) == normalise(10, 20, 60, 90)


class TestConversion:
    def test_rend_les_coordonnees_d_ecran(self) -> None:
        # À l'échelle 1, le tracé se décale simplement de l'origine du jeu.
        zone = to_game(Rect(100, 50, 349, 115), JEU, 1.0)
        assert zone == Rect(-1180, 33, 349, 115)

    def test_tient_compte_de_la_reduction(self) -> None:
        """Régression : oublier l'échelle donne une zone quatre fois trop petite.

        L'aperçu est réduit pour tenir à l'écran. Un rectangle tracé dessus est
        donc en pixels d'aperçu, pas en pixels de jeu. Ne pas diviser par
        l'échelle produit une zone plausible, bien placée à l'œil sur l'aperçu,
        et qui ne couvre en réalité qu'un coin du bandeau.
        """
        échelle = 0.5
        zone = to_game(Rect(100, 50, 200, 100), JEU, échelle)

        assert zone.width == 400
        assert zone.height == 200
        assert zone.left == JEU.left + 200
        assert zone.top == JEU.top + 100

    def test_ne_rend_jamais_une_zone_plate(self) -> None:
        # Une largeur nulle capturerait une image vide, que la reconnaissance
        # traite comme un écran sans bandeau : « aucune quête mesurée » sans le
        # moindre indice, et le réglage survit au redémarrage.
        zone = to_game(Rect(10, 10, 0, 0), JEU, 0.35)
        assert zone.width >= 1
        assert zone.height >= 1

    def test_un_aller_retour_retombe_sur_la_zone_visee(self) -> None:
        échelle = scale_for(JEU)
        visée = Rect(JEU.left + 2090, JEU.top + 440, 340, 380)
        # Ce que le tracé donnerait sur l'aperçu pour viser cette zone.
        tracé = Rect(
            int((visée.left - JEU.left) * échelle),
            int((visée.top - JEU.top) * échelle),
            int(visée.width * échelle),
            int(visée.height * échelle),
        )

        retour = to_game(tracé, JEU, échelle)

        # Aux arrondis de l'échelle près, on retombe sur la zone visée.
        assert abs(retour.left - visée.left) <= 4
        assert abs(retour.top - visée.top) <= 4
        assert abs(retour.width - visée.width) <= 4
        assert abs(retour.height - visée.height) <= 4
