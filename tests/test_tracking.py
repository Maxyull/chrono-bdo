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
        # Une seule : les deux autres lignes qui se résolvent sont des quêtes
        # de métier, hors du périmètre mesuré. Voir le test de la chaîne.
        assert len(tracked) == 1

    def test_ecarte_les_lignes_d_objectif(self, catalog: Catalog) -> None:
        tracked = read_tracker(REAL_PANEL, catalog)
        # Dix lignes sur onze ne donnent rien d'utile : objectifs, suites
        # d'objectifs, un nom tronqué par le jeu, et deux quêtes de métier.
        assert tracked.unresolved == 10

    def test_donne_la_quete_mise_en_evidence(self, catalog: Catalog) -> None:
        assert read_tracker(REAL_PANEL, catalog).active == QuestId(21139, 52)

    def test_deduit_la_chaine_en_cours(self, catalog: Catalog) -> None:
        """Régression : deux quêtes de métier épinglées volaient la chaîne.

        Ce panneau est une lecture réelle. Le joueur y fait « [Calpheon]
        Livraison de rations », quête principale de la chaîne 21139. Mais il a
        aussi épinglé « Tissu haut de gamme » (type 5) et « Vie citadine »
        (type 2), toutes deux de la chaîne 3500.

        La chaîne la plus représentée était donc la 3500, à deux voix contre
        une, et le panneau annonçait une chaîne où le joueur n'était pas.
        Prendre la plus fréquente ne protège de rien : ce sont les quêtes de
        métier qu'on épingle, et le joueur en garde plusieurs à la fois.

        Confirmé en jeu le 5 août 2026 : sur un panneau où le joueur suivait
        « [Calpheon] En avançant » (21139/113), la reconnaissance n'a pas su
        lire ce nom-là du tout, la quête active portant un bandeau vert qui
        écrase le contraste en niveaux de gris. Sur sept lignes, une seule
        s'est résolue, « Tissu haut de gamme », et le panneau annonçait la
        chaîne 3500.

        Le produit ne mesure que les quêtes principales. Une quête d'un autre
        type n'a donc rien à dire sur l'endroit où l'on en est.
        """
        assert read_tracker(REAL_PANEL, catalog).chain == 21139

    def test_se_tait_quand_seules_des_quetes_de_metier_se_lisent(
        self, catalog: Catalog
    ) -> None:
        """Le silence vaut mieux qu'une chaîne inventée.

        Cas relevé en jeu : la quête principale active est illisible à cause de
        son bandeau vert, et seule une quête de récolte épinglée se résout. Ne
        rien dire laisse le joueur sans information ; annoncer la chaîne de sa
        quête de récolte lui en donne une fausse, qu'il croira.
        """
        metiers = [("Tissu haut de gamme", 0.96), ("Vie citadine", 0.94)]

        tracked = read_tracker(metiers, catalog)

        assert tracked.chain is None
        assert tracked.active is None
        assert tracked.unresolved == 2

    def test_sans_le_filtre_la_chaine_fausse_revient(self, catalog: Catalog) -> None:
        # Garde-fou : si quelqu'un remet `main_only=False` un jour, ce test dit
        # exactement ce qu'il rétablit.
        assert read_tracker(REAL_PANEL, catalog, main_only=False).chain == 3500

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
