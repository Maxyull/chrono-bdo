from __future__ import annotations

import pytest

from rubin.capture import Rect, banner_region, tracker_region
from rubin.reference import Catalog, QuestId
from rubin.tracking import TrackedQuests, read_tracker

REFERENCE = Rect(0, 0, 2559, 1439)

#: Lignes **réellement** rendues par la reconnaissance sur le panneau de suivi,
#: recopiées telles quelles. Mélange de noms de quêtes, d'objectifs, de noms
#: tronqués et de caractères parasites nés des icônes.
REAL_PANEL = [
    ("[Calpheon] Livraison de rations", 0.98),
    ("-Parler au membre de la guilde marchande de", 0.96),
    ("Xian", 0.98),
    ("-Donnerlesrations aKirklas", 0.95),
    ("O[Joum.][Recolte]Decouverte...", 0.93),
    ("-ObtenirduSouffledesfeesenrecoltant", 0.96),
    ("Tissuhaut de gamme", 0.97),
    ("-ApporteruncoconaLakla", 0.97),
    ("Vie citadine", 0.94),
    ("Recolterdes fleursdefloconde feuala", 0.96),
    ("main", 0.97),
]


class TestTrackerRegion:
    def test_est_ancree_en_haut_a_droite(self) -> None:
        # Contrairement au bandeau, qui l'est en bas.
        region = tracker_region(REFERENCE)
        assert region.right == REFERENCE.right - 130
        assert region.top == 440

    def test_ne_recouvre_pas_la_zone_du_bandeau(self) -> None:
        # Les deux sont lues séparément et à des cadences différentes : un
        # recouvrement ferait payer deux fois la même reconnaissance.
        tracker = tracker_region(REFERENCE)
        banner = banner_region(REFERENCE)
        assert tracker.bottom < banner.top

    def test_suit_la_fenetre(self) -> None:
        region = tracker_region(Rect(1920, 100, 2559, 1439))
        assert region.left == 1920 + tracker_region(REFERENCE).left

    def test_ne_sort_jamais_de_la_fenetre(self) -> None:
        region = tracker_region(Rect(0, 0, 800, 600))
        assert region.left >= 0
        assert region.right <= 800
        assert region.bottom <= 600

    def test_refuse_une_echelle_absurde(self) -> None:
        with pytest.raises(ValueError, match="échelle"):
            tracker_region(REFERENCE, ui_scale=0)


class TestReadTracker:
    def test_reconnait_les_quetes_d_un_panneau_reel(self, catalog: Catalog) -> None:
        """Régression : le tri repose sur le catalogue, pas sur la mise en forme.

        La première tentative distinguait les objectifs par le tiret qui les
        préfixe. La reconnaissance ne le rend pas toujours, « Recolterdes
        fleurs... » sort sans, et elle ajoute parfois un caractère parasite né
        d'une icône, « O[Joum.] ». Une règle de mise en forme prendrait donc
        des objectifs pour des quêtes.
        """
        tracked = read_tracker(REAL_PANEL, catalog)
        assert QuestId(21139, 52) in tracked.quests
        assert len(tracked) == 3

    def test_ecarte_les_lignes_d_objectif(self, catalog: Catalog) -> None:
        tracked = read_tracker(REAL_PANEL, catalog)
        # Huit lignes sur onze ne sont pas des quêtes : objectifs, suites
        # d'objectifs, et un nom tronqué par le jeu.
        assert tracked.unresolved == 8

    def test_donne_la_quete_mise_en_evidence(self, catalog: Catalog) -> None:
        assert read_tracker(REAL_PANEL, catalog).active == QuestId(21139, 52)

    def test_deduit_la_chaine_en_cours(self, catalog: Catalog) -> None:
        # C'est l'apport du panneau : le contexte qui permet de trancher quand
        # un nom lu sur le bandeau désigne plusieurs quêtes.
        assert read_tracker(REAL_PANEL, catalog).chain == 3500

    def test_ne_compte_pas_deux_fois_la_meme_quete(self, catalog: Catalog) -> None:
        doublons = [("[Calpheon] Livraison de rations", 0.98)] * 3
        assert len(read_tracker(doublons, catalog)) == 1

    def test_ignore_les_lignes_mal_lues(self, catalog: Catalog) -> None:
        lignes = [("[Calpheon] Livraison de rations", 0.40)]
        assert len(read_tracker(lignes, catalog)) == 0

    def test_survit_a_un_panneau_vide(self, catalog: Catalog) -> None:
        vide = read_tracker([], catalog)
        assert vide.active is None
        assert vide.chain is None
        assert len(vide) == 0


class TestChaineDominante:
    def test_prefere_la_chaine_la_plus_representee(self) -> None:
        # Une quête de récolte épinglée par le joueur ne doit pas faire passer
        # toute la session pour appartenant à sa chaîne.
        quetes = (QuestId(3500, 81), QuestId(21139, 46), QuestId(21139, 52))
        assert TrackedQuests(quests=quetes).chain == 21139
