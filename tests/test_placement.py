"""Où poser la fenêtre sans aveugler la mesure.

Toutes les positions de ce fichier sont celles de l'écran de référence,
2559 x 1439, avec les deux zones réellement lues par le logiciel.
"""

from __future__ import annotations

import pytest

from rubin.capture import Rect, banner_region, tracker_region
from rubin.placement import candidates, choose, conflicts, is_inside

#: L'écran sur lequel toutes les mesures du projet ont été relevées.
JEU = Rect(0, 0, 2559, 1439)

#: Les deux zones que Rubin lit, telles que le code les calcule.
ZONES = (banner_region(JEU), tracker_region(JEU))

#: Une fenêtre d'interface de taille plausible.
TAILLE = (420, 520)


class TestChevauchement:
    def test_deux_rectangles_disjoints_ne_se_chevauchent_pas(self) -> None:
        assert not Rect(0, 0, 10, 10).overlaps(Rect(100, 100, 10, 10))

    def test_un_rectangle_se_chevauche_lui_meme(self) -> None:
        zone = Rect(10, 20, 30, 40)
        assert zone.overlaps(zone)

    def test_un_seul_pixel_commun_suffit(self) -> None:
        # Un pixel du bandeau caché est un pixel que la reconnaissance n'aura
        # pas, et le nom d'une quête tient à peu de chose.
        assert Rect(0, 0, 11, 11).overlaps(Rect(10, 10, 5, 5))

    def test_deux_rectangles_bord_a_bord_ne_se_chevauchent_pas(self) -> None:
        """Régression : coller deux fenêtres était refusé pour rien.

        Deux rectangles qui se touchent exactement ne partagent aucun pixel :
        `right` est la première colonne **hors** du rectangle. Les traiter comme
        se chevauchant faisait perdre la seule place disponible sur un écran
        chargé, et poussait la fenêtre vers une position bien pire.
        """
        gauche = Rect(0, 0, 100, 100)
        droite = Rect(100, 0, 100, 100)
        assert not gauche.overlaps(droite)
        assert not droite.overlaps(gauche)


class TestConflits:
    def test_une_position_libre_n_a_aucun_conflit(self) -> None:
        assert conflicts(Rect(100, 100, 200, 200), ZONES) == []

    def test_une_position_sur_le_bandeau_est_signalee(self) -> None:
        """Régression : la fenêtre pouvait se poser sur ce qu'elle lit.

        Rubin lit une capture d'écran, donc ce qui est **composé** à l'écran.
        Une fenêtre posée sur la zone du bandeau est lue à la place du bandeau,
        et la session ne mesure rien.

        Ce n'est pas théorique : c'est arrivé avec un navigateur. La fenêtre du
        jeu était correctement trouvée, mais Chrome en occupait la moitié
        gauche, et c'est Chrome qui a été capturé. Notre propre fenêtre ferait
        exactement pareil, à ceci près qu'on l'aurait posée nous-mêmes.
        """
        bandeau = banner_region(JEU)
        sur_le_bandeau = Rect(bandeau.left - 20, bandeau.top - 20, 200, 200)

        en_cause = conflicts(sur_le_bandeau, ZONES)

        assert bandeau in en_cause

    def test_une_position_sur_le_panneau_de_suivi_est_signalee(self) -> None:
        suivi = tracker_region(JEU)
        dessus = Rect(suivi.left + 10, suivi.top + 10, 100, 100)

        assert suivi in conflicts(dessus, ZONES)

    def test_rend_les_deux_zones_quand_les_deux_sont_couvertes(self) -> None:
        # Une fenêtre qui couvre tout le jeu les couvre toutes les deux, et
        # l'interface doit pouvoir nommer chacune.
        assert len(conflicts(JEU, ZONES)) == 2


class TestChoix:
    def test_trouve_une_place_libre_sur_l_ecran_de_reference(self) -> None:
        place = choose(JEU, ZONES, TAILLE)

        assert place is not None
        assert conflicts(place, ZONES) == []

    def test_la_place_choisie_tient_dans_la_fenetre_du_jeu(self) -> None:
        place = choose(JEU, ZONES, TAILLE)

        assert place is not None
        assert is_inside(place, JEU)

    def test_prefere_le_haut_pres_des_quetes(self) -> None:
        # C'est là que le joueur regarde déjà pour lire son panneau de suivi,
        # donc là que la liste des suivantes lui coûte le moins d'yeux.
        place = choose(JEU, ZONES, TAILLE)

        assert place is not None
        assert place.top < JEU.height // 2

    def test_ne_couvre_jamais_la_moindre_zone_lue(self) -> None:
        # Éprouvé sur beaucoup de tailles : aucune ne doit produire une place
        # qui recouvre une zone, quitte à ne rien rendre du tout.
        for largeur in range(200, 1400, 100):
            for hauteur in range(200, 1000, 100):
                place = choose(JEU, ZONES, (largeur, hauteur))
                if place is not None:
                    assert conflicts(place, ZONES) == [], f"{largeur}x{hauteur}"

    def test_rend_None_quand_aucune_place_ne_convient(self) -> None:
        """Régression : mieux vaut ne rien poser que casser la mesure.

        Sur une fenêtre minuscule, ou pour une interface très grande, toute
        position essayée recouvre une zone lue. Poser quand même la fenêtre
        « au moins quelque part » romprait la mesure en silence, pour un
        confort d'affichage.

        `None` veut donc dire : dis-le au joueur, et laisse-le choisir entre
        déplacer sa fenêtre et accepter de ne rien mesurer.
        """
        minuscule = Rect(0, 0, 400, 300)
        zones = (banner_region(minuscule), tracker_region(minuscule))

        assert choose(minuscule, zones, (390, 290)) is None

    @pytest.mark.parametrize("ecran", [Rect(0, 0, 1920, 1080), Rect(-1280, -17, 2560, 1440)])
    def test_marche_sur_d_autres_ecrans_et_en_coordonnees_negatives(self, ecran: Rect) -> None:
        # Un second écran placé à gauche du principal donne des coordonnées
        # négatives, relevées telles quelles sur le poste de développement.
        zones = (banner_region(ecran), tracker_region(ecran))

        place = choose(ecran, zones, TAILLE)

        assert place is not None
        assert conflicts(place, zones) == []
        assert is_inside(place, ecran)


class TestCandidats:
    def test_tous_les_candidats_ont_la_taille_demandee(self) -> None:
        for candidate in candidates(JEU, TAILLE):
            assert (candidate.width, candidate.height) == TAILLE

    def test_le_premier_candidat_est_en_haut(self) -> None:
        assert candidates(JEU, TAILLE)[0].top < JEU.height // 2
