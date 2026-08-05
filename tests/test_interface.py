"""Ce que l'interface affiche, éprouvé sans écran.

Rien ici ne touche à Tk : ce sont des états qui entrent et des chaînes qui
sortent. Une fenêtre mal dessinée se voit ; un temps mal formaté ou un compte de
mesures oublié se croit.
"""

from __future__ import annotations

import pytest

from rubin.capture import Rect, banner_region, tracker_region
from rubin.interface import (
    COVERAGE_TAGS,
    FRAGILE_BELOW,
    ZoneState,
    describe_conflict,
    describe_reading,
    describe_zone,
    format_coverage,
    format_duration,
    format_gap,
    format_reference,
    format_running,
    format_upcoming_line,
    main_quest_total,
    running_seconds,
)
from rubin.interface.app import ZONE_KEYS, ZONE_ROLES
from rubin.interface.help import EXAMPLES
from rubin.interface.theme import (
    COLORS,
    FULL_SCORE_AT,
    UNPLACED_CAP,
    confidence_colour,
    confidence_score,
)
from rubin.reference import Catalog, Quest, QuestId
from rubin.references import Coverage, QuestReference
from rubin.settings import Settings
from rubin.upcoming import UpcomingQuest

JEU = Rect(0, 0, 2559, 1439)
ZONES = {"le bandeau de quête": banner_region(JEU), "le panneau de suivi": tracker_region(JEU)}


def _quete(position: int, nom: str) -> Quest:
    return Quest(
        id=QuestId(21136, position),
        name=nom,
        prefix="Calpheon",
        title=nom,
        region=None,
        kind=1,
        level=0,
    )


def _a_venir(
    position: int = 2,
    nom: str = "[Calpheon] Cris stridents des harpies",
    reference: QuestReference | None = None,
    gap: int = 0,
) -> UpcomingQuest:
    return UpcomingQuest(quest=_quete(position, nom), reference=reference, gap_before=gap)


class TestDurees:
    @pytest.mark.parametrize(
        ("secondes", "attendu"),
        [(0, "0 s"), (42.5, "42 s"), (60, "1 min 00 s"), (252, "4 min 12 s"), (3600, "1 h 00 min")],
    )
    def test_ecrit_une_duree_lisible(self, secondes: float, attendu: str) -> None:
        assert format_duration(secondes) == attendu


class TestChronometreEnDirect:
    def test_compte_le_temps_de_la_quete_en_cours(self) -> None:
        assert running_seconds(1_000.0, 1_042.5) == pytest.approx(42.5)

    def test_ne_compte_rien_quand_aucune_quete_n_est_ouverte(self) -> None:
        assert running_seconds(None, 1_042.5) is None

    def test_ecrit_le_temps_qui_court(self) -> None:
        assert format_running(65.0) == "chronomètre : 1 min 05 s"
        assert format_running(0.0) == "chronomètre : 0 s"

    def test_un_depart_ignore_le_dit_au_lieu_de_se_taire(self) -> None:
        """Régression : « ça va trop vite et certaines quêtes ne sont pas comptées ».

        Signalé par Maxime le 05/08/2026. Deux bandeaux consécutifs se
        ressemblent beaucoup, et le second peut être refusé avant lecture comme
        trop proche du premier : la quête n'est alors jamais comptée. Le défaut
        est aujourd'hui **parfaitement silencieux**, et ne se découvre qu'une
        heure plus tard, en comptant les quêtes manquantes.

        Il faut donc que « rien n'est chronométré » s'écrive, et qu'il ne
        s'écrive pas comme « ça vient de démarrer ». Un blanc ou un « 0 s » se
        liraient exactement à l'envers, comme la colonne vide d'une quête jamais
        mesurée se lisait « instantané ».
        """
        assert format_running(None) == "aucune quête chronométrée"
        assert format_running(None) != format_running(0.0)
        assert format_running(None).strip() != ""

    def test_ne_montre_jamais_un_chronometre_negatif(self) -> None:
        """Régression : l'instant courant est lu avant le journal.

        Les deux lectures sont séparées d'une poignée de microsecondes, pendant
        lesquelles le fil de mesure peut ouvrir une quête. Le départ est alors
        postérieur à l'instant courant, et la soustraction rendrait « -0 s »,
        qui n'a aucun sens à l'écran.
        """
        assert running_seconds(1_042.5, 1_042.0) == 0.0
        assert format_running(running_seconds(1_042.5, 1_042.0)) == "chronomètre : 0 s"


class TestCouverture:
    def test_compte_les_grises_en_soustrayant_du_catalogue(self) -> None:
        couverture = Coverage(
            well_measured=0, lightly_measured=11, threshold=5, measured_quests=11
        )
        # L'espace des milliers est insécable, U+00A0, écrite ici en clair : à
        # l'œil, elle est indiscernable d'une espace ordinaire.
        assert format_coverage(couverture, 3_924) == (
            "0 verte",
            "11 orange",
            "3 913 jamais mesurées",
        )

    def test_le_serveur_ne_rend_pas_les_grises_et_c_est_au_client_de_soustraire(
        self,
    ) -> None:
        """Régression : réclamer au serveur un chiffre qu'il n'a pas.

        `GET /v1/couverture` rend aujourd'hui, en production, exactement
        `{"well_measured": 0, "lightly_measured": 11, "threshold": 5,
        "measured_quests": 11}`. Les quêtes jamais mesurées **n'y sont pas**, et
        ce n'est pas un oubli : le serveur ne connaît que les quêtes dont il a
        reçu une mesure, et rien ne lui garantit que tous les clients lisent le
        même catalogue.

        Les 3 924 quêtes principales sont un fait du catalogue, que ce client
        porte. La soustraction lui appartient, et son résultat, 3 913, est le
        seul chiffre qui donne l'échelle de ce qui reste.
        """
        couverture = Coverage(
            well_measured=0, lightly_measured=11, threshold=5, measured_quests=11
        )
        parts = format_coverage(couverture, 3_924)
        assert parts is not None
        assert parts[2].startswith("3\u00a0913")
        # Le total du serveur, lui, ne dit rien des grises.
        assert couverture.measured_quests == 11

    def test_un_serveur_muet_ne_produit_aucun_chiffre(self) -> None:
        """Régression : trois zéros affirment ce qu'on ne sait pas.

        « 0 verte, 0 orange, 3 924 jamais mesurées » se lit comme « personne n'a
        jamais rien mesuré ». C'est une affirmation, et elle est fausse quand
        c'est seulement le serveur qui n'a pas répondu. La bonne réponse est
        « je ne sais pas », donc rien du tout.
        """
        assert format_coverage(None, 3_924) is None

    def test_ne_compte_rien_sans_catalogue(self) -> None:
        couverture = Coverage(
            well_measured=0, lightly_measured=11, threshold=5, measured_quests=11
        )
        assert format_coverage(couverture, 0) is None

    def test_ne_rend_jamais_un_nombre_negatif_de_grises(self) -> None:
        # Un référentiel plus court que ce que le serveur a reçu : client
        # d'une version antérieure, ou langue en retard.
        couverture = Coverage(
            well_measured=40, lightly_measured=30, threshold=5, measured_quests=70
        )
        parts = format_coverage(couverture, 10)
        assert parts is not None
        assert parts[2] == "0 jamais mesurée"

    def test_accorde_le_singulier_et_le_pluriel(self) -> None:
        couverture = Coverage(
            well_measured=1, lightly_measured=1, threshold=5, measured_quests=2
        )
        assert format_coverage(couverture, 3) == ("1 verte", "1 orange", "1 jamais mesurée")

    def test_les_trois_tranches_portent_les_couleurs_de_la_legende(self) -> None:
        """Les balises du compteur sont celles de la légende juste au-dessus.

        Deux listes parallèles finiraient par diverger, et un compte peint de la
        couleur du voisin ne lève aucune erreur : il se croit sur parole.
        """
        assert COVERAGE_TAGS == ("sur", "moyen", "absent")
        for balise in COVERAGE_TAGS:
            assert balise in COLORS

    def test_compte_les_quetes_principales_du_catalogue(self, catalog: Catalog) -> None:
        # Les quêtes principales seulement : ce sont les seules mesurées, donc
        # les seules dont une couverture veut dire quelque chose. L'échantillon
        # de test en porte quatorze sur trente-trois.
        assert main_quest_total(catalog, "fr") == 14
        assert main_quest_total(catalog, "fr") < len(catalog)


class TestTempsDeReference:
    def test_une_quete_jamais_mesuree_le_dit_en_toutes_lettres(self) -> None:
        """Régression : une colonne vide se lit comme « instantané ».

        C'est l'inverse de ce qu'on veut dire. « Inconnu » et « immédiat » sont
        deux réponses opposées à « combien de temps », et un blanc penche du
        mauvais côté.
        """
        assert format_reference(_a_venir()) == "jamais mesurée"

    def test_annonce_le_nombre_de_mesures_derriere_le_temps(self) -> None:
        item = _a_venir(reference=QuestReference(252.0, samples=14, fastest_seconds=201.0))

        texte = format_reference(item)

        assert "4 min 12 s" in texte
        assert "14 mesures" in texte

    def test_marque_un_temps_qui_repose_sur_trop_peu(self) -> None:
        """Régression : une médiane sur une mesure passait pour une référence.

        La base ne contient aujourd'hui que onze mesures, d'un seul joueur, sur
        une seule chaîne. Presque tout ce que l'interface affiche repose donc
        sur très peu, et l'afficher comme un temps établi serait le chiffre faux
        dans sa forme la plus courante : exact, mais pris pour ce qu'il n'est
        pas.
        """
        item = _a_venir(reference=QuestReference(97.5, samples=1, fastest_seconds=97.5))

        texte = format_reference(item)

        assert "1 mesure" in texte
        assert "peu sûr" in texte

    def test_ne_marque_pas_un_temps_suffisamment_assis(self) -> None:
        item = _a_venir(
            reference=QuestReference(252.0, samples=FRAGILE_BELOW, fastest_seconds=201.0)
        )
        assert "peu sûr" not in format_reference(item)

    def test_accorde_le_singulier(self) -> None:
        item = _a_venir(reference=QuestReference(97.5, samples=1, fastest_seconds=97.5))
        assert "1 mesure " in format_reference(item) or "1 mesure)" in format_reference(item)
        assert "1 mesures" not in format_reference(item)


class TestLignesAVenir:
    def test_montre_la_position_et_le_nom(self) -> None:
        ligne = format_upcoming_line(_a_venir())
        assert ligne.startswith("2. ")
        assert "Cris stridents des harpies" in ligne

    def test_marque_une_branche_d_un_choix(self) -> None:
        # 69 quêtes principales sur 38 chaînes sont des branches : les lister
        # comme une suite à faire donnerait un programme impossible à suivre.
        item = UpcomingQuest(
            quest=_quete(1, "[Calpheon][Carrefour] Du côté de Valks"),
            reference=None,
        )
        assert "branche d'un choix" in format_upcoming_line(item)

    def test_ne_marque_rien_sur_une_quete_ordinaire(self) -> None:
        assert "branche" not in format_upcoming_line(_a_venir())


class TestTrous:
    def test_aucun_avertissement_sans_trou(self) -> None:
        assert format_gap(_a_venir()) is None

    def test_annonce_un_trou(self) -> None:
        assert "144 positions inconnues" in (format_gap(_a_venir(gap=144)) or "")

    def test_accorde_le_singulier_d_un_trou(self) -> None:
        texte = format_gap(_a_venir(gap=1)) or ""
        assert "1 position inconnue" in texte
        assert "positions" not in texte


class TestZones:
    def test_dit_si_la_zone_est_calculee_ou_choisie(self) -> None:
        calculee = ZoneState("bandeau", banner_region(JEU), chosen=False)
        choisie = ZoneState("bandeau", banner_region(JEU), chosen=True)

        assert "calculée" in describe_zone(calculee)
        assert "choisie" in describe_zone(choisie)

    def test_montre_la_taille_et_la_position(self) -> None:
        texte = describe_zone(ZoneState("bandeau", Rect(2210, 1185, 349, 115), chosen=True))
        assert "349x115" in texte
        assert "2210" in texte

    def test_une_zone_qui_ne_lit_rien_le_dit_et_suggere_pourquoi(self) -> None:
        """Régression : une zone muette ressemblait à un écran vide.

        Sans cet aperçu, régler un rectangle revient à le déplacer à l'aveugle
        puis à jouer une session entière pour découvrir qu'il était à côté.
        Trois défauts de ce projet ont coûté une séance chacun faute de pouvoir
        répondre à « qu'est-ce que tu lis, là, tout de suite ».

        Une liste vide est un résultat, et le plus instructif de tous.
        """
        texte = describe_reading(ZoneState("suivi", tracker_region(JEU), chosen=False))

        assert "rien lu" in texte
        assert "à côté" in texte

    def test_rend_les_lignes_lues(self) -> None:
        etat = ZoneState(
            "suivi",
            tracker_region(JEU),
            chosen=False,
            lines=("Objectifactuel:Alamemoire des soldats", "Tissu haut de gamme"),
        )

        texte = describe_reading(etat)

        assert "Tissu haut de gamme" in texte
        assert texte.count("\n") == 1


class TestLesTroisZones:
    """Les trois surfaces lisibles du domaine, et le même nom pour chacune partout.

    Rien ici ne dessine : ce sont des tables qui doivent rester d'accord entre
    elles. Le jour où elles ne le sont plus, l'interface propose un bouton qui
    n'enregistre rien, ou apparie une zone à la lecture d'une autre, et aucun
    des deux ne lève la moindre erreur.
    """

    def test_les_memes_trois_zones_dans_les_trois_tables(self) -> None:
        assert ZONE_KEYS == ("banner", "tracker", "choice")
        assert tuple(EXAMPLES) == ZONE_KEYS
        # Et chacune a bien son champ de réglage, sans quoi le tracé du joueur
        # partirait dans le vide au premier enregistrement.
        for clé in ZONE_KEYS:
            assert hasattr(Settings(), clé)

    def test_chaque_role_dit_ce_qu_on_perd_a_le_placer_de_travers(self) -> None:
        # C'est l'intérêt du rôle affiché : le joueur voit trois rectangles et
        # doit savoir lequel compte. Les trois n'ont pas le même poids.
        rôles = {clé: rôle for clé, _nom, rôle in ZONE_ROLES}
        assert "rien n'est jamais mesuré" in rôles["banner"]
        assert "on mesure quand même" in rôles["tracker"]
        assert "aucune durée n'est perdue" in rôles["choice"]

    def test_le_role_du_panneau_de_choix_annonce_ses_deux_apports(self) -> None:
        # Identifier les noms coupés, et savoir quelle branche a été prise. Le
        # second est ce qu'aucune autre zone ne sait donner.
        rôle = {clé: texte for clé, _nom, texte in ZONE_ROLES}["choice"]
        assert "préfixe de région" in rôle
        assert "branches" in rôle
        assert "ESTIMÉE" in rôle

    def test_l_aide_du_panneau_de_choix_n_invente_ni_image_ni_lecture(self) -> None:
        """Régression attendue : aucune capture de ce panneau n'existe.

        Les deux autres entrées d'aide montrent de VRAIES captures, avec leurs
        défauts, et c'est écrit dans l'en-tête de `help.py` : un dessin propre
        ferait viser une cible qui n'existe pas et donnerait au joueur
        l'impression que sa capture à lui est ratée.

        La même règle interdit d'en fabriquer une ici, et interdit d'inventer
        les lignes que la reconnaissance en tirerait, puisque personne n'a
        jamais lu ce panneau. L'entrée est donc rendue sans image et sans
        exemple de lecture, et le texte dit pourquoi.
        """
        _titre, fichier, texte, lignes = EXAMPLES["choice"]

        assert fichier is None
        assert lignes == ()
        assert "AUCUNE CAPTURE" in texte

    def test_les_deux_zones_mesurees_gardent_leur_vraie_capture(self) -> None:
        # L'entrée sans image est une exception, pas la nouvelle règle.
        for clé in ("banner", "tracker"):
            _titre, fichier, _texte, lignes = EXAMPLES[clé]
            assert fichier is not None
            assert lignes


class TestCouleurDeConfiance:
    def test_le_vert_demande_au_moins_cinq_mesures(self) -> None:
        assert confidence_colour(5) == COLORS["sur"]
        assert confidence_colour(40) == COLORS["sur"]

    def test_l_orange_signale_le_peu_de_mesures(self) -> None:
        # La base contient onze mesures d'un seul joueur : presque tout sera
        # orange, et c'est exactement ce qu'il faut montrer.
        assert confidence_colour(1) == COLORS["moyen"]
        assert confidence_colour(4) == COLORS["moyen"]

    def test_une_quete_jamais_mesuree_est_grise_et_non_rouge(self) -> None:
        """Régression : peindre l'absence en rouge la fait passer pour une panne.

        Un temps qui n'existe pas n'est pas un mauvais temps. C'est une
        invitation à être le premier à le mesurer, et c'est le cas de la quasi
        totalité des 3 924 quêtes principales aujourd'hui.

        Le rouge est réservé à ce qui va mal. Une couleur neutre dit « personne
        n'est passé par là », ce qui est la vérité.
        """
        assert confidence_colour(None) == COLORS["absent"]
        assert confidence_colour(0) == COLORS["absent"]
        assert confidence_colour(None) != COLORS["accent"]

    def test_un_compte_negatif_est_traite_comme_une_absence(self) -> None:
        # Ne devrait pas arriver, mais un serveur qui renverrait une valeur
        # aberrante ne doit pas produire une couleur rassurante.
        assert confidence_colour(-3) == COLORS["absent"]


class TestConflits:
    def test_rien_a_dire_quand_la_fenetre_ne_couvre_rien(self) -> None:
        assert describe_conflict([], ZONES) is None

    def test_nomme_la_zone_couverte(self) -> None:
        """Régression : « une zone est couverte » ne dit pas quoi faire.

        Le bandeau et le panneau de suivi n'ont ni les mêmes conséquences ni le
        même remède : perdre le bandeau, c'est ne plus rien mesurer du tout ;
        perdre le panneau, c'est seulement ne plus savoir où l'on est au
        démarrage.
        """
        message = describe_conflict([ZONES["le bandeau de quête"]], ZONES) or ""

        assert "le bandeau de quête" in message
        assert "le panneau de suivi" not in message

    def test_nomme_les_deux_quand_les_deux_sont_couvertes(self) -> None:
        message = describe_conflict(list(ZONES.values()), ZONES) or ""
        assert "le bandeau de quête" in message
        assert "le panneau de suivi" in message

    def test_previent_que_la_transparence_ne_sauve_rien(self) -> None:
        # C'est le point contre-intuitif : la capture prend ce qui est composé à
        # l'écran, donc une fenêtre à demi transparente donne un mélange, pas le
        # jeu. Quelqu'un qui l'ignore baissera l'opacité et croira avoir réglé
        # le problème.
        message = describe_conflict([ZONES["le bandeau de quête"]], ZONES) or ""
        assert "transparence" in message


class TestScoreSurCent:
    def test_zero_quand_personne_n_a_mesure(self) -> None:
        """0 veut dire « aucune information, aucun temps », comme demandé."""
        assert confidence_score(None) == 0
        assert confidence_score(0) == 0

    def test_cent_quand_tout_est_su(self) -> None:
        # Assez de mesures pour une médiane, et la place dans la chaîne connue.
        assert confidence_score(FULL_SCORE_AT, placed=True) == 100
        assert confidence_score(FULL_SCORE_AT * 3, placed=True) == 100

    def test_monte_avec_le_nombre_de_mesures(self) -> None:
        assert confidence_score(1) < confidence_score(5) < confidence_score(15)

    def test_une_place_incertaine_plafonne_le_score(self) -> None:
        """Régression : un temps parfait masquait une position inconnue.

        Le score répond à « qu'est-ce qui m'attend et quand », et la moitié de
        cette question est « où ça tombe ». Une quête dont on connaît
        parfaitement le temps mais pas la place ne peut donc pas valoir cent.

        Ce n'est pas un cas rare : 82 chaînes sur 349 portent des trous, et le
        jeu compte 19 235 quêtes là où le référentiel en connaît 18 999.

        Le maillon faible commande, jamais la moyenne : une moyenne laisserait
        un temps très bien mesuré compenser une position inconnue.
        """
        assert confidence_score(FULL_SCORE_AT, placed=False) == UNPLACED_CAP
        assert confidence_score(FULL_SCORE_AT, placed=False) < confidence_score(
            FULL_SCORE_AT, placed=True
        )

    def test_une_place_incertaine_n_invente_pas_de_mesures(self) -> None:
        # Le plafond ne remonte jamais un score bas : c'est un plafond, pas un
        # plancher. Une quête sans mesure reste à zéro.
        assert confidence_score(0, placed=False) == 0
        assert confidence_score(1, placed=False) == confidence_score(1, placed=True)


class TestSousChronosLocaux:
    def test_le_protocole_ignore_tout_des_objectifs(self) -> None:
        """Les sous-chronos ne peuvent PAS partir au serveur, par construction.

        Un bandeau d'objectif raté ne produit pas un trou : il fusionne deux
        segments en un et donne un temps trop long, qui a toutes les apparences
        d'une vraie mesure. Là où une quête ratée donne un chiffre incomplet, un
        objectif raté donne un chiffre faux.

        Ils vivent donc entièrement dans la couche d'affichage. Ce test le
        verrouille : ni le lot envoyé ni la ligne de mesure ne portent le
        moindre champ d'objectif. Si quelqu'un en ajoute un, il casse ici, et la
        docstring lui dit pourquoi.
        """
        from dataclasses import fields

        from rubin.protocol import MeasurePayload, SessionPayload

        noms = {f.name for f in fields(MeasurePayload)} | {f.name for f in fields(SessionPayload)}
        interdits = {"objective", "objectives", "split", "splits", "objectif", "objectifs"}

        assert not (noms & interdits), f"un champ d'objectif est apparu : {noms & interdits}"

    def test_le_journal_d_evenements_ne_borne_aucun_objectif(self) -> None:
        # Le sous-chrono est calculé dans l'interface, à partir des instants de
        # capture. `Timeline` n'en sait rien et ne doit rien en savoir : c'est
        # ce qui garantit qu'aucune médiane ne peut être touchée.
        import inspect

        from rubin import timing

        source = inspect.getsource(timing)
        assert "sous_chrono" not in source
        assert "OBJECTIVE_DONE" not in source


class TestChoixAutomatiqueDeZone:
    def test_le_titre_se_reconnait_malgre_les_espaces_avales(self) -> None:
        """Régression : l'égalité stricte ne verrait jamais un titre réel.

        La reconnaissance rend « Objectif dequete accompli », espaces avalés.
        C'est le troisième piège du projet, et il vaut ici comme ailleurs : la
        comparaison se fait sur la forme pliée, sans espaces ni ponctuation.
        """
        from rubin.interface.autozone import contains_title, titles_folded

        assert contains_title([("Objectif dequete accompli", 0.96)], titles_folded())
        assert contains_title([("Nouvelle quete", 0.98)], titles_folded())

    def test_du_decor_ne_passe_pas_pour_un_titre(self) -> None:
        from rubin.interface.autozone import contains_title, titles_folded

        décor = [("de guilde terminees avant la maintenance,", 0.98), ("Xian", 0.97)]
        assert not contains_title(décor, titles_folded())

    def test_les_titres_viennent_des_valeurs_et_non_des_cles(self) -> None:
        """Régression : `TITLES` associe un genre à ses libellés.

        Itérer dessus rend des `BannerKind`, pas du texte, et la première
        comparaison échoue sur une erreur incompréhensible. C'est arrivé.
        """
        from rubin.interface.autozone import titles_folded

        attendus = titles_folded()
        assert "nouvellequete" in attendus
        assert all(isinstance(t, str) for t in attendus)
