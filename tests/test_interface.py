"""Ce que l'interface affiche, éprouvé sans écran.

Rien ici ne touche à Tk : ce sont des états qui entrent et des chaînes qui
sortent. Une fenêtre mal dessinée se voit ; un temps mal formaté ou un compte de
mesures oublié se croit.
"""

from __future__ import annotations

import pytest

from rubin.capture import Rect, banner_region, tracker_region
from rubin.interface import (
    ALPHABET_QUEST_LIMIT,
    COVERAGE_TAGS,
    DEMO_BANNER,
    DEMO_MARK,
    FRAGILE_BELOW,
    LINK_TAGS,
    LOCK_MARK,
    LOCKED_WHILE_MEASURING,
    RANKING_UNAVAILABLE,
    LettredQuest,
    Watching,
    ZoneState,
    alphabet_cap_warning,
    alphabet_key,
    alphabet_sections,
    demo_active,
    demo_ranking,
    describe_conflict,
    describe_reading,
    describe_zone,
    format_coverage,
    format_current_reference,
    format_duration,
    format_gap,
    format_letter_header,
    format_lettred_quest,
    format_link,
    format_measure_line,
    format_note_placeholder,
    format_other_quests,
    format_personal_best,
    format_quest_times,
    format_ranking,
    format_reference,
    format_running,
    format_search_result,
    format_upcoming_line,
    format_watching,
    lock_label,
    main_quest_total,
    other_quest_total,
    quest_display_name,
    ranking_message,
    running_seconds,
    samples_by_quest,
    search_quests,
    zone_lock_reason,
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
from rubin.references import (
    MIN_SAMPLES_PER_QUEST,
    RANKING_LIMIT,
    Coverage,
    QuestReference,
    RankedQuest,
    ServerHealth,
)
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


class TestMeilleurTempsEnCours:
    """Le meilleur temps connu de la quête EN COURS, pendant qu'on la joue.

    Demandé par Maxime le 05/08/2026, une fois les mesures revenues après la
    panne du jour : voir une référence pendant qu'on joue, pas seulement une
    fois la quête finie.
    """

    def test_une_quete_jamais_mesuree_le_dit_positivement(self) -> None:
        # « Personne encore » plutôt que « pas de temps », pour que ce soit une
        # invitation et non un reproche : c'est la seule mesure qui manque
        # vraiment à ce projet, la base ne contenant que très peu de joueurs.
        texte = format_current_reference(None)

        assert "premier" in texte or "première" in texte

    def test_montre_le_record_pas_la_mediane(self) -> None:
        """Régression : cet affichage-ci classe sur le record, exprès.

        Partout ailleurs le projet interdit le record comme critère de
        classement, un tricheur s'en emparant en un seul envoi. Ici, personne
        n'est classé : on montre une référence à battre pendant qu'on joue, et
        c'est le record qui répond à « en combien de temps ça peut se faire »,
        la médiane répondant à « en combien de temps ça se fait d'habitude ».
        Confondre les deux ici serait montrer la mauvaise réponse à la question
        posée par ce widget précis.
        """
        référence = QuestReference(median_seconds=252.0, samples=8, fastest_seconds=180.0)

        texte = format_current_reference(référence)

        assert "4 min 12 s" not in texte  # la médiane, absente
        assert "3 min 00 s" in texte  # le record, présent
        assert "8 mesures" in texte

    def test_marque_un_record_qui_repose_sur_trop_peu(self) -> None:
        référence = QuestReference(median_seconds=97.5, samples=1, fastest_seconds=97.5)

        texte = format_current_reference(référence)

        assert "1 mesure" in texte
        assert "peu sûr" in texte

    def test_ne_marque_pas_un_record_suffisamment_assis(self) -> None:
        référence = QuestReference(
            median_seconds=252.0, samples=FRAGILE_BELOW, fastest_seconds=201.0
        )

        assert "peu sûr" not in format_current_reference(référence)


class TestRecordPersonnel:
    """Le record PERSONNEL du joueur sur la quête en cours, distinct du meilleur
    temps connu de tout le monde ci-dessus.

    Demandé par Maxime après #72 : « Ton temps : xx / Ton meilleur temps : xx ou
    N/A / Meilleur temps : xx ». C'est une donnée locale, lue dans les sessions
    déjà écrites sur ce poste (voir `history.personal_best`), jamais envoyée ni
    reçue du serveur.
    """

    def test_une_quete_jamais_faite_le_dit_honnetement(self) -> None:
        # Ni un zéro ni une ligne vide, qui se liraient comme « instantané »,
        # l'inverse de la vérité : le même écueil que partout ailleurs dans ce
        # projet pour une quête sans référence.
        texte = format_personal_best(None)

        assert "jamais mesurée" in texte

    def test_affiche_la_duree_du_record(self) -> None:
        texte = format_personal_best(97.0)

        assert "1 min 37 s" in texte
        assert "ton meilleur temps" in texte


class TestNoteDeQuete:
    """La note personnelle d'une quête : le monstre à tuer, l'instance, le
    choix pris, un mot ou un nombre relevé dans le chat. Demandée par Maxime
    le 05/08/2026 au soir. Purement locale, voir `notes.py`.
    """

    def test_invite_a_ecrire_quand_rien_n_est_note(self) -> None:
        texte = format_note_placeholder(has_note=False)

        assert "aucune note" in texte

    def test_dit_qu_une_note_existe_deja(self) -> None:
        texte = format_note_placeholder(has_note=True)

        assert "enregistrée" in texte
        assert "aucune note" not in texte


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


class TestQuetesHorsPerimetre:
    def test_compte_a_part_les_quetes_que_rubin_ne_mesure_pas(
        self, catalog: Catalog
    ) -> None:
        # L'échantillon porte trente-trois quêtes, dont quatorze principales :
        # dix-neuf sont hors périmètre. Sur le vrai catalogue, c'est 18 999
        # moins 3 924, soit 15 075.
        assert main_quest_total(catalog, "fr") == 14
        assert other_quest_total(catalog, "fr") == 19
        assert main_quest_total(catalog, "fr") + other_quest_total(catalog, "fr") == len(
            catalog
        )

    def test_le_denominateur_de_la_couverture_reste_les_principales(
        self, catalog: Catalog
    ) -> None:
        """Régression : mêler les deux totaux donnerait un chiffre faux.

        Rubin ne mesure que les quêtes principales, et c'est délibéré :
        chronométrer une quête répétable n'a aucun sens puisqu'on la refait
        indéfiniment. Compter les 15 075 autres comme « jamais mesurées »
        annoncerait un arriéré de travail qui n'existe pas, et découragerait
        pour rien.

        Les grises se comptent donc sur les 3 924 principales, jamais sur les
        18 999 du catalogue.
        """
        couverture = Coverage(
            well_measured=0, lightly_measured=21, threshold=5, measured_quests=21
        )
        parts = format_coverage(couverture, main_quest_total(catalog, "fr"))
        assert parts is not None
        # Quatorze principales moins vingt-et-une mesurées : le plancher à zéro
        # tient, et surtout le total n'a pas gonflé des dix-neuf autres.
        assert parts[2] == "0 jamais mesurée"

    def test_dit_pourquoi_ces_quetes_ne_sont_pas_comptees(self) -> None:
        texte = format_other_quests(15_075)
        assert texte is not None
        assert texte.startswith("+ 15 075")
        assert "que Rubin ne mesure pas" in texte

    def test_ne_dit_rien_quand_il_n_y_en_a_aucune(self) -> None:
        assert format_other_quests(0) is None


class TestTemoinDeConnexion:
    def test_distingue_les_trois_etats(self) -> None:
        sans = format_link(None, None)
        coupé = format_link("https://rubin.maxyull.fr", None)
        relié = format_link(
            "https://rubin.maxyull.fr",
            ServerHealth(protocol=1, sessions=4, measures=21, players=2),
        )

        # Trois messages distincts, parce qu'ils appellent trois gestes
        # différents : ne rien faire, réparer, ou continuer.
        assert len({sans[0], coupé[0], relié[0]}) == 3
        assert len({sans[1], coupé[1], relié[1]}) == 3

    def test_aucun_serveur_n_est_pas_une_panne(self) -> None:
        texte, balise = format_link(None, None)
        assert "--envoyer" in texte
        assert "injoignable" not in texte
        assert balise == LINK_TAGS["absent"]

    def test_annonce_l_adresse_et_ce_que_le_serveur_a_recu(self) -> None:
        texte, balise = format_link(
            "https://rubin.maxyull.fr",
            ServerHealth(protocol=1, sessions=4, measures=21, players=2),
        )
        assert "https://rubin.maxyull.fr" in texte
        assert "21 mesures" in texte
        assert balise == LINK_TAGS["connecte"]

    def test_un_serveur_perime_reste_connecte(self) -> None:
        """Régression : un point d'entrée manquant n'est pas une panne.

        Cas réel du 05/08/2026 : `rubin.maxyull.fr` répondait parfaitement, mais
        rendait 404 sur `/v1/couverture`, faute d'avoir été redéployé depuis
        l'ajout du compteur. Écrire « serveur injoignable » aurait envoyé
        chercher l'erreur du côté du réseau, alors que le remède était un
        déploiement.

        Le témoin ne lit que `/sante`. Le serveur est donc **connecté**, et
        c'est le compteur, séparément, qui dit qu'il n'a pas eu sa réponse.
        """
        santé = ServerHealth(protocol=1, sessions=4, measures=21, players=2)

        texte, balise = format_link("https://rubin.maxyull.fr", santé)

        assert texte.startswith("connecté")
        assert balise == LINK_TAGS["connecte"]
        # Et pendant ce temps, les deux compteurs disent leur propre absence.
        assert format_coverage(None, 3_924) is None
        assert ranking_message(None) == RANKING_UNAVAILABLE

    def test_les_trois_couleurs_existent_dans_l_habillage(self) -> None:
        # Aucune couleur nouvelle : celles de la légende suffisent, et un
        # quatrième vert voisin du premier ne se distinguerait de rien.
        for balise in LINK_TAGS.values():
            assert balise in COLORS


def _classee(chain: int, position: int, seconds: float, samples: int = 3) -> RankedQuest:
    return RankedQuest(
        chain=chain, position=position, median_seconds=seconds, samples=samples
    )


class TestClassementParQuete:
    def test_le_nom_vient_du_catalogue_et_non_du_serveur(self, catalog: Catalog) -> None:
        """Le serveur ne connaît que `chaine/position`, et c'est voulu.

        Les noms sont un fait du catalogue, que ce client porte : rien ne
        garantit au serveur que tous les clients lisent le même référentiel, ni
        la même langue.
        """
        assert (
            quest_display_name(catalog, QuestId(21136, 2), "fr")
            == "[Calpheon] Cris stridents des harpies"
        )

    def test_une_quete_inconnue_du_catalogue_montre_son_identifiant(
        self, catalog: Catalog
    ) -> None:
        # « 21403/1 » est laid mais vrai, et il se cherche dans le référentiel.
        # Un blanc ne se cherche pas.
        assert quest_display_name(catalog, QuestId(21403, 1), "fr") == "21403/1"
        assert quest_display_name(None, QuestId(21403, 1), "fr") == "21403/1"

    def test_affiche_le_nombre_de_mesures_a_cote_de_chaque_ligne(
        self, catalog: Catalog
    ) -> None:
        lignes = format_ranking(
            [_classee(21136, 2, 90.0, samples=11), _classee(21139, 46, 252.0, samples=3)],
            catalog,
        )

        assert lignes[0].startswith(" 1.")
        assert "1 min 30 s" in lignes[0]
        assert "Cris stridents des harpies" in lignes[0]
        assert "(11 mesures)" in lignes[0]
        assert "(3 mesures)" in lignes[1]

    def test_dit_qu_aucune_quete_n_a_assez_de_mesures(self) -> None:
        """Régression : 198,8 quêtes/heure sur UNE mesure, vu en production.

        Relevé réel sur https://rubin.maxyull.fr le 05/08/2026 : la chaîne 21403
        tenait la tête du classement des chaînes à 198,8 quêtes/heure, sur une
        seule mesure. À la quête, un classement sans seuil trierait le bruit, et
        la première place irait toujours à celle qu'une personne a mesurée une
        fois en ayant eu de la chance.

        Le serveur écarte donc ces lignes, et rend aujourd'hui une liste
        **vide** sur ses vingt-et-une mesures. Un tableau vide et muet se lirait
        comme « aucune quête n'est rapide », ce qui ne veut rien dire : la
        fenêtre dit la vraie raison.
        """
        message = ranking_message(())

        assert message is not None
        assert "assez de mesures" in message
        assert f"{MIN_SAMPLES_PER_QUEST} mesures" in message
        assert format_ranking((), None) == ()

    def test_ne_confond_pas_une_liste_vide_avec_un_serveur_muet(self) -> None:
        # Le même jour, le serveur en production ne connaissait pas encore le
        # point d'entrée et rendait 404. Dire « aucune quête assez mesurée »
        # aurait été une affirmation à la place d'un « je ne sais pas ».
        assert ranking_message(None) == RANKING_UNAVAILABLE
        assert ranking_message(()) != RANKING_UNAVAILABLE

    def test_se_tait_quand_il_y_a_quelque_chose_a_montrer(self) -> None:
        assert ranking_message([_classee(21136, 2, 90.0)]) is None


class TestModeDemonstration:
    def test_chaque_ligne_porte_le_mot_test(self, catalog: Catalog) -> None:
        lignes = demo_ranking(catalog, "fr")

        assert len(lignes) == RANKING_LIMIT
        for ligne in lignes:
            assert DEMO_MARK in ligne
        assert "FABRIQUÉES" in DEMO_BANNER

    def test_s_efface_de_lui_meme_quand_le_vrai_classement_est_plein(self) -> None:
        plein = [_classee(21136, position, 60.0) for position in range(RANKING_LIMIT)]
        partiel = plein[:2]

        assert demo_active(None, wanted=True)
        assert demo_active(partiel, wanted=True)
        assert not demo_active(plein, wanted=True)
        # Et il ne s'allume jamais tout seul : c'est un geste.
        assert not demo_active(None, wanted=False)

    def test_aucune_donnee_fabriquee_ne_peut_atteindre_le_reseau(self) -> None:
        """Verrou : une mesure inventée n'entre jamais dans les médianes.

        C'est le principe fondateur du projet : rater une mesure donne un
        chiffre incomplet, en inventer une donne un chiffre faux, et un chiffre
        faux entre dans les médianes sans jamais en ressortir.

        La proposition initiale était « un faux temps par quête, nommé test, qui
        disparaîtra à dix vraies entrées ». Ce qui disparaît d'un affichage reste
        en base et continue de peser : le garde-fou n'aurait rien gardé.

        La démonstration vit donc entièrement dans la couche d'affichage, et sa
        forme **est** la garantie : elle rend des chaînes de caractères déjà
        mises en forme, jamais des mesures. Ce test le verrouille de trois
        façons. Si quelqu'un branche un jour ces lignes sur le réseau, il casse
        ici, et cette docstring lui dit pourquoi.
        """
        import inspect
        from dataclasses import fields

        from rubin import protocol, upload
        from rubin.protocol import MeasurePayload, SessionPayload

        # 1. Rien de fabriqué n'a de place où se ranger dans un lot.
        noms = {f.name for f in fields(MeasurePayload)} | {
            f.name for f in fields(SessionPayload)
        }
        interdits = {"demo", "demonstration", "fake", "test", "factice", "fabrique"}
        assert not (noms & interdits), f"champ de démonstration : {noms & interdits}"

        # 2. Ni le protocole ni l'envoi ne connaissent la démonstration.
        for module in (protocol, upload):
            source = inspect.getsource(module)
            assert "demo" not in source.lower()
            assert DEMO_MARK not in source

        # 3. Ce que la démonstration produit n'est pas une mesure, mais du
        #    texte : il n'existe à aucun instant un objet qui pourrait se
        #    glisser dans un lot.
        for ligne in demo_ranking(None):
            assert isinstance(ligne, str)


class TestRechercheDeQuete:
    def test_trouve_sans_accents_ni_crochets(self, catalog: Catalog) -> None:
        """La comparaison passe par `fold`, des deux côtés.

        Le catalogue porte « [Calpheon] Ce qui s'est passé jusqu'à présent », et
        personne ne tape cela. C'est la même forme pliée que celle imposée par
        la reconnaissance, qui avale les espaces et la ponctuation.
        """
        trouvées = search_quests(catalog, "ce qui sest passe", "fr")

        assert [q.id for q in trouvées] == [QuestId(21139, 29)]

    def test_ne_cherche_pas_sur_deux_lettres(self, catalog: Catalog) -> None:
        # Deux lettres rendraient des centaines de quêtes, donc une liste
        # inutile, et replieraient le catalogue entier à chaque frappe.
        assert search_quests(catalog, "ca", "fr") == ()

    def test_ne_propose_que_des_quetes_principales(self, catalog: Catalog) -> None:
        """Régression : une recherche qui rend des impasses.

        Rubin ne mesure que les quêtes principales. Proposer les 15 075 autres
        ferait cliquer sur des quêtes qui n'auront jamais de temps, et une
        recherche qui rend des impasses est pire qu'une recherche qui rend peu.
        """
        principales = {
            quest.id for chain in catalog.chains("fr").values() for quest in chain.quests
        }

        for quest in search_quests(catalog, "calpheon", "fr") + search_quests(
            catalog, "les", "fr"
        ):
            assert quest.id in principales

    def test_range_les_resultats_dans_l_ordre_du_jeu(self, catalog: Catalog) -> None:
        trouvées = search_quests(catalog, "calpheon", "fr")
        identifiants = [(q.id.chain, q.id.position) for q in trouvées]
        assert identifiants == sorted(identifiants)

    def test_montre_ou_se_trouve_la_quete(self, catalog: Catalog) -> None:
        quête = search_quests(catalog, "cris stridents", "fr")[0]
        assert (
            format_search_result(quête)
            == "[Calpheon] Cris stridents des harpies   [21136/2]"
        )

    def test_une_quete_jamais_mesuree_le_dit_en_toutes_lettres(
        self, catalog: Catalog
    ) -> None:
        """Régression : une colonne vide se lit comme « instantané ».

        C'est l'inverse de ce qu'on veut dire, et c'est le cas le plus fréquent :
        la base contient vingt-et-une mesures pour 3 924 quêtes principales, donc
        presque toutes les recherches tomberont sur une quête jamais mesurée.
        """
        quête = search_quests(catalog, "cris stridents", "fr")[0]

        texte = format_quest_times(quête, None)

        assert "jamais mesurée" in texte
        assert "0 s" not in texte

    def test_montre_la_mediane_le_record_et_l_assise(self, catalog: Catalog) -> None:
        quête = search_quests(catalog, "cris stridents", "fr")[0]

        texte = format_quest_times(
            quête, QuestReference(median_seconds=252.0, samples=14, fastest_seconds=201.0)
        )

        assert "médiane : 4 min 12 s" in texte
        assert "14 mesures" in texte
        # Le record est rendu à côté de la médiane, jamais à sa place : il
        # renseigne, il ne classe pas.
        assert "3 min 21 s" in texte
        assert "peu sûr" not in texte

    def test_marque_un_temps_qui_repose_sur_trop_peu(self, catalog: Catalog) -> None:
        quête = search_quests(catalog, "cris stridents", "fr")[0]
        texte = format_quest_times(
            quête, QuestReference(median_seconds=97.5, samples=1, fastest_seconds=97.5)
        )
        assert "peu sûr" in texte


class TestSurveillanceVisible:
    """Ce que la boucle de mesure voit, rendu lisible pendant qu'elle tourne.

    `BannerWatcher` comptait déjà ces nombres et personne ne les regardait.
    Toute la valeur est dans le cas où il ne se passe rien : une session qui
    mesure se raconte toute seule dans la liste des quêtes faites, une session
    qui ne mesure pas n'avait, elle, aucun mot pour se décrire.
    """

    def test_donne_les_trois_etages_de_la_chaine_dans_l_ordre(self) -> None:
        texte = format_watching(
            Watching(frames=1368, banners_seen=154, reads=7, elapsed=180.0, since_banner=2.0)
        )

        # L'ordre suit la chaîne : capturer, voir, lire. Le premier nombre resté
        # à zéro désigne l'étage en panne, et c'est tout l'intérêt de la ligne.
        assert texte.index("images") < texte.index("bandeaux vus") < texte.index("lectures")
        assert "1 368 images" in texte
        assert "154 bandeaux vus" in texte
        assert "7 lectures" in texte

    def test_une_session_qui_demarre_ne_crie_pas_encore(self) -> None:
        # Zéro bandeau au bout de dix secondes est le cas normal : le joueur
        # vient d'appuyer sur Démarrer. Un avertissement ici serait du bruit,
        # et un avertissement permanent n'avertit plus de rien.
        texte = format_watching(Watching(frames=80, banners_seen=0, reads=0, elapsed=10.0))

        assert "aucun bandeau" not in texte
        assert "80 images" in texte

    def test_le_silence_prolonge_est_dit_avec_sa_duree(self) -> None:
        texte = format_watching(Watching(frames=7200, banners_seen=0, reads=0, elapsed=900.0))

        assert "aucun bandeau depuis 15 min 00 s" in texte

    def test_les_images_perdues_sont_signalees_a_part(self) -> None:
        # Un débordement veut dire que la lecture ne suit plus la capture, donc
        # que des bandeaux réels ont été jetés. Ça ne se confond pas avec un
        # écran où rien n'apparaît, et ça ne doit pas se taire.
        texte = format_watching(
            Watching(frames=900, banners_seen=40, reads=12, overflowed=3, elapsed=60.0)
        )

        assert "3 images perdues" in texte

    def test_rien_a_afficher_hors_session(self) -> None:
        assert format_watching(None) == ""

    def test_regression_la_fenetre_disait_mesure_en_cours_sans_rien_mesurer(self) -> None:
        """Régression : session du 5 août 2026, 16 h 06, quinze minutes muettes.

        Le cas réel, mesuré des deux côtés. La fenêtre affichait « mesure en
        cours, zone 349x115 », le journal de session ne contenait que son
        en-tête, et le jeu tournait bien : un guet lancé à côté a vu quarante
        bandeaux au-dessus du seuil sur la même zone, dont une paire complète,
        « [Mediah] Intentions inconnues » acceptée à 16 h 08 min 47 s puis
        accomplie à 16 h 09 min 50 s.

        Rien dans l'interface ne permettait de choisir entre les quatre causes
        possibles, et il a fallu écrire cinq programmes de diagnostic hors du
        logiciel pour seulement savoir où chercher. Avec cette ligne, le premier
        nombre resté à zéro l'aurait dit en une seconde.

        Le `since_banner` à `None` est le cœur du cas : aucun bandeau n'a JAMAIS
        été vu, ce qui ne se confond pas avec « vu il y a zéro seconde ». C'est
        `elapsed` qui porte alors le jugement.
        """
        texte = format_watching(
            Watching(frames=7128, banners_seen=0, reads=0, elapsed=891.0, since_banner=None)
        )

        assert "0 bandeaux vus" in texte
        assert "aucun bandeau depuis" in texte
        # Et surtout : la ligne ne peut pas être vide, sans quoi on retombe
        # exactement sur le silence qu'elle existe pour rompre.
        assert texte


class TestZonesVerrouilleesPendantLaMesure:
    """Les commandes de zone, refusées pendant qu'une session tourne.

    Ce n'est pas de la prudence, c'est que ça ne marcherait pas : la zone d'une
    session est calculée à son démarrage, et la retracer en cours de route
    n'aurait aucun effet sur la session vivante.
    """

    def test_les_sept_commandes_qui_ecrivent_ou_lisent_sont_verrouillees(self) -> None:
        # Toutes celles qui écrivent une zone ou lancent une reconnaissance.
        # « adopt » en fait partie depuis #70 : reprendre un ancien tracé écrit
        # une zone comme les autres, pour la session qui, elle, ne changera pas.
        assert set(LOCKED_WHILE_MEASURING) == {
            "read_now",
            "reset",
            "auto",
            "adopt",
            "pick_banner",
            "pick_tracker",
            "pick_choice",
        }

    def test_le_cadenas_est_dans_le_libelle_pas_a_cote(self) -> None:
        # Un bouton seulement grisé se remarque à peine, et le clic sans effet
        # se lit comme un logiciel qui ne répond plus.
        assert lock_label("Tracer le bandeau", locked=True) == f"{LOCK_MARK} Tracer le bandeau"

    def test_le_libelle_redevient_nu_une_fois_la_session_arretee(self) -> None:
        assert lock_label("Tracer le bandeau", locked=False) == "Tracer le bandeau"

    def test_la_raison_dit_l_effet_et_la_sortie(self) -> None:
        raison = zone_lock_reason()

        # Ce qui se passerait vraiment : rien. C'est ça qu'il faut dire, pas
        # « interdit ».
        assert "aucun effet sur la session en cours" in raison
        # Et comment s'en sortir, sinon le verrou est une impasse.
        assert "Arrêtez la session" in raison

    def test_regression_retracer_une_zone_en_cours_de_session_ne_faisait_rien(self) -> None:
        """Régression : la zone est figée au démarrage de la session.

        `MeasuringSession._run` calcule la zone une seule fois puis la confie à
        `ScreenCapture`, qui retient un rectangle en coordonnées d'écran
        absolues. Un tracé fait pendant la mesure était bien enregistré dans les
        réglages, et la session continuait sur l'ancien rectangle.

        C'est le pire cas de ce projet, celui du réglage faux et silencieux : le
        joueur croit avoir corrigé, il a corrigé quelque chose, et l'effet
        n'arrive jamais. Il attribuera ensuite au réglage un silence venu
        d'ailleurs, et cherchera là où il n'y a rien. Vécu le 5 août 2026, où
        j'ai moi-même conseillé de retracer la zone pendant qu'une session
        tournait.

        La raison affichée doit donc parler de la SESSION EN COURS, et pas
        seulement dire que c'est verrouillé.
        """
        raison = zone_lock_reason()

        assert "calculée à son démarrage" in raison
        assert "croiriez avoir corrigé" in raison

    def test_l_onglet_entier_porte_le_cadenas_pas_seulement_ses_boutons(self) -> None:
        """L'étiquette de l'onglet elle-même, pour que le refus se voie fermé.

        Demandé par Maxime : un bouton verrouillé au milieu d'un onglet ouvert
        invite encore à essayer, et laisse croire que le RESTE de l'onglet agit
        sur la session en cours. Ce n'est le cas d'aucune de ses commandes : les
        six écrivent une zone ou lancent une reconnaissance, et la zone de la
        session est figée à son démarrage.
        """
        assert lock_label("Zones", locked=True) == f"{LOCK_MARK} Zones"
        assert lock_label("Zones", locked=False) == "Zones"


class TestImagesRepeteesDansLaLigneDeSurveillance:
    """Le taux de captures répétées, remonté jusqu'à la ligne affichée.

    Suite directe de la séance du 5 août 2026 : la ligne de surveillance de
    #63 disait « 3 266 images, 2 bandeaux vus », mais rien ne disait POURQUOI
    si peu de bandeaux sortaient d'autant d'images. Le compteur de #68 mesure
    la cause la plus probable, une capture qui répète une image déjà prise ;
    cette ligne la rend visible sans qu'il faille aller lire `echecs/`.
    """

    def test_un_taux_de_repetition_bas_ne_dit_rien(self) -> None:
        # Quelques répétitions sont normales : un menu ouvert, un chargement.
        texte = format_watching(
            Watching(frames=1000, banners_seen=20, reads=5, repeated=40, elapsed=60.0)
        )

        assert "répétées" not in texte

    def test_un_taux_de_repetition_soutenu_devient_un_avertissement(self) -> None:
        texte = format_watching(
            Watching(frames=1000, banners_seen=2, reads=0, repeated=600, elapsed=400.0)
        )

        assert "600 images répétées sur 1\u00a0000" in texte

    def test_regression_le_taux_du_5_aout_47_contre_2_bandeaux(self) -> None:
        """Régression : les proportions réelles de la session muette.

        Sept minutes, 3 266 images côté Rubin, 2 bandeaux vus, quand un témoin
        sur la même zone en voyait 47. La cause précise n'a jamais été
        confirmée ce jour-là faute d'avoir eu ce compteur : ce test fige
        seulement que SI le taux avait été soutenu, la ligne l'aurait dit,
        au lieu de laisser deviner entre quatre hypothèses concurrentes.
        """
        texte = format_watching(
            Watching(frames=3266, banners_seen=2, reads=0, repeated=2800, elapsed=420.0)
        )

        assert "⚠" in texte
        assert "images répétées" in texte


class TestZoneEgareeSansTaille:
    """Un tracé qui existe mais ne s'applique à aucune taille de fenêtre.

    #58 a construit la table `zones` de `Settings`, indexée par taille, sans
    jamais la brancher dans l'interface : `app.py` lisait toujours l'ancien
    champ `banner`/`tracker`/`choice`, qui s'appliquait sans condition. Le
    5 août 2026, une zone tracée à y=1224 est ainsi restée active toute une
    matinée, coupant la ligne du titre du bandeau, alors que `zone_for`
    répondait déjà « non » depuis la fusion de #58 : personne ne l'appelait.
    """

    def test_decrit_le_tracé_perdu_avec_le_bon_bouton(self) -> None:
        état = ZoneState("Bandeau", Rect(2211, 1186, 349, 115), chosen=False, stray=True)

        texte = describe_zone(état)

        assert "Reprendre l'ancien tracé" in texte

    def test_une_zone_choisie_ne_se_dit_pas_egaree(self) -> None:
        état = ZoneState("Bandeau", Rect(2211, 1186, 349, 115), chosen=True, stray=False)

        assert "Reprendre" not in describe_zone(état)

    def test_regression_le_cas_du_5_aout_zone_a_y1224_jamais_reprise(self) -> None:
        """Régression : le fichier réel de Maxime, avant qu'il ne soit corrigé.

        `{"zone_bandeau": {"x": 2211, "y": 1224, "largeur": 349, "hauteur": 115}}`,
        sans `zones_par_taille`. `Settings.from_dict` le relit tel quel, dans
        le champ hérité : `zone_for` ne le rend pour AUCUNE taille, c'est le
        comportement voulu depuis #58. Le test fige ce que l'interface doit en
        faire : afficher la zone comme égarée, jamais comme active.
        """
        réglages = Settings.from_dict(
            {"zone_bandeau": {"x": 2211, "y": 1224, "largeur": 349, "hauteur": 115}}
        )
        taille = (2560, 1440)

        assert réglages.zone_for("banner", taille) is None
        assert réglages.unkeyed("banner") == Rect(2211, 1224, 349, 115)

        état = ZoneState(
            "Bandeau",
            Rect(2211, 1186, 349, 115),  # la zone CALCULÉE, celle qui doit s'appliquer
            chosen=réglages.zone_for("banner", taille) is not None,
            stray=réglages.unkeyed("banner") is not None
            and réglages.zone_for("banner", taille) is None,
        )

        assert état.chosen is False
        assert état.stray is True
        assert "Reprendre l'ancien tracé" in describe_zone(état)


class TestLigneDeQueteFaite:
    """La ligne « temps · nom · score », et les bornes cliquables du nom.

    Demandé par Maxime le 05/08/2026 : un visuel plus lisible, avec le nom
    cliquable pour rejoindre sa fiche de temps. Les bornes sont en index de
    caractères, à recopier tel quel dans un index Tk, pour que la zone
    cliquable ne se désynchronise jamais du texte affiché.
    """

    def test_assemble_les_trois_champs_avec_le_bon_separateur(self) -> None:
        ligne, *_bornes = format_measure_line("1 min 05 s", "Les fanatiques", "", 82)

        assert ligne == "1 min 05 s  ·  Les fanatiques  ·  82/100"

    def test_les_bornes_encadrent_exactement_le_nom_et_sa_marque(self) -> None:
        ligne, début, fin = format_measure_line(
            "33 s", "Rapport des ressources", "  (déduite)", 40
        )

        assert ligne[début:fin] == "Rapport des ressources  (déduite)"

    def test_un_nom_vide_donne_des_bornes_egales_pas_negatives(self) -> None:
        # Cas limite pur : jamais rencontré en vrai, mais un calcul qui
        # produirait des bornes inversées casserait l'appelant Tk sans dire
        # pourquoi.
        _ligne, début, fin = format_measure_line("0 s", "", "", 0)

        assert 0 <= début <= fin

    def test_regression_le_score_a_quitte_la_ligne_de_detail(self) -> None:
        """Régression : le score doublait sur les deux lignes avant #71.

        Le premier jet affichait `{score}/100` à la fois sur la ligne
        principale et sur la ligne de détail en dessous. La ligne principale
        est la source de vérité désormais ; le détail ne garde que ce qu'elle
        ne dit pas, le nombre de mesures et l'écart aux autres joueurs.
        """
        ligne, *_bornes = format_measure_line("2 min 00 s", "Les fanatiques", "", 55)

        assert "55/100" in ligne
        assert ligne.count("/100") == 1


def _lq(position: int, title: str, chain: int = 21136, prefix: str | None = "Calpheon") -> Quest:
    """Une quête pour l'arbre alphabétique, `name` et `title` distincts.

    À la différence de `_quete`, qui pose `title == name` par simplicité, ce
    module-ci teste justement la différence entre les deux : `name` porte le
    préfixe de région entre crochets, `title` ne le porte pas.
    """
    nom = f"[{prefix}] {title}" if prefix else title
    return Quest(
        id=QuestId(chain, position), name=nom, prefix=prefix, title=title,
        region=None, kind=1, level=0,
    )


class TestArbreAlphabetique:
    """La liste alphabétique des 3 924 quêtes principales, pastille au bout.

    Demandée par Maxime le 05/08/2026 : voir d'un coup d'œil quelles quêtes
    ont encore besoin d'être timées. `ReferenceClient.fastest_quests` fait
    déjà tout le travail réseau ; ce module-ci se contente de grouper ce
    qu'elle rend, et le seul point délicat est son plafond à 200 lignes.
    """

    def test_alphabet_key_ignore_les_accents(self) -> None:
        assert (
            alphabet_key(_lq(1, "École de commerce"))
            == alphabet_key(_lq(2, "Ecole de commerce"))
            == "E"
        )

    def test_alphabet_key_range_une_apostrophe_de_tete_sous_sa_lettre(self) -> None:
        assert alphabet_key(_lq(1, "L'appel du sang")) == "L"

    def test_alphabet_key_range_un_titre_qui_commence_par_un_chiffre_sous_diese(self) -> None:
        assert alphabet_key(_lq(1, "1000 questions pour un noble")) == "#"

    def test_regression_alphabet_key_ignore_le_prefixe_de_region(self) -> None:
        """Régression : le cinquième piège de `ETAT.md`, sous un autre angle.

        Le panneau de choix coupe le préfixe de région : l'écran affiche
        « [Carrefour] Du côté de Valks » là où le catalogue porte
        « [Calpheon][Carrefour] Du côté de Valks ». Grouper sur `name`, qui
        PORTE ce préfixe entre crochets, aurait rangé la quasi-totalité du
        catalogue sous « # » ou sous « [ », puisque tous les noms
        commencent par un crochet. `alphabet_key` doit partir de `title`,
        débarrassé du préfixe, jamais de `name`.
        """
        quete = _lq(1, "Du côté de Valks", prefix="Calpheon")
        assert quete.name.startswith("[")

        assert alphabet_key(quete) == "D"

    def test_alphabet_sections_trie_a_l_interieur_d_une_lettre(self) -> None:
        catalogue = Catalog({"fr": [_lq(1, "Zoulou"), _lq(2, "Abricot"), _lq(3, "Zamak")]})

        sections = alphabet_sections(catalogue, "fr", {})

        assert [entrée.quest.title for entrée in sections["Z"]] == ["Zamak", "Zoulou"]

    def test_alphabet_sections_zero_mesure_par_defaut(self) -> None:
        quete = _lq(1, "Abricot")
        catalogue = Catalog({"fr": [quete]})

        sections = alphabet_sections(catalogue, "fr", {})

        assert sections["A"] == (LettredQuest(quete, 0),)

    def test_alphabet_sections_reprend_le_compte_fourni_en_masse(self) -> None:
        quete = _lq(1, "Abricot")
        catalogue = Catalog({"fr": [quete]})

        sections = alphabet_sections(catalogue, "fr", {quete.id: 7})

        assert sections["A"][0].samples == 7

    def test_format_letter_header_accorde_le_pluriel(self) -> None:
        une = (LettredQuest(_lq(1, "Abricot"), 3),)
        deux = (LettredQuest(_lq(1, "Abricot"), 0), LettredQuest(_lq(2, "Amande"), 2))

        assert format_letter_header("A", une) == "A   —   1 quête, 1 mesurée"
        assert format_letter_header("A", deux) == "A   —   2 quêtes, 1 mesurée"

    def test_format_lettred_quest_dit_jamais_mesuree(self) -> None:
        assert (
            format_lettred_quest(LettredQuest(_lq(1, "Abricot"), 0))
            == "Abricot   —   jamais mesurée"
        )

    def test_format_lettred_quest_accorde_mesure_au_singulier(self) -> None:
        assert (
            format_lettred_quest(LettredQuest(_lq(1, "Abricot"), 1)) == "Abricot   —   1 mesure"
        )
        assert (
            format_lettred_quest(LettredQuest(_lq(1, "Abricot"), 4)) == "Abricot   —   4 mesures"
        )

    def test_samples_by_quest_vide_quand_le_serveur_n_a_rien_dit(self) -> None:
        assert samples_by_quest(None) == {}

    def test_samples_by_quest_indexe_par_identifiant(self) -> None:
        ligne = RankedQuest(chain=21136, position=1, median_seconds=42.0, samples=9)

        assert samples_by_quest((ligne,)) == {QuestId(21136, 1): 9}

    def test_alphabet_cap_warning_se_tait_sous_le_plafond(self) -> None:
        loin_du_plafond = tuple(
            RankedQuest(chain=1, position=i, median_seconds=1.0, samples=1) for i in range(29)
        )

        assert alphabet_cap_warning(loin_du_plafond) is None

    def test_alphabet_cap_warning_se_tait_quand_le_serveur_n_a_rien_dit(self) -> None:
        assert alphabet_cap_warning(None) is None

    def test_regression_alphabet_cap_warning_au_plafond_de_v1_quetes(self) -> None:
        """Régression : `/v1/quetes` plafonne à 200 lignes, sans le dire.

        `serveur/src/rubin_serveur/main.py` applique
        `limit = max(1, min(limit, 200))` quel que soit ce qu'on demande, et
        trie par temps médian croissant. Si la base compte un jour plus de
        200 quêtes distinctes mesurées, ce sont les plus LENTES qui sortent
        silencieusement du lot renvoyé : une quête réellement mesurée
        apparaîtrait alors « jamais mesurée » dans l'arbre alphabétique,
        exactement le chiffre faux que ce projet refuse d'inventer. La base
        du 05/08/2026, avec 29 quêtes mesurées en tout, est bien trop petite
        pour déclencher ce cas ; ce test le fabrique pour vérifier que le
        garde-fou existe avant que la base ne le rencontre pour de vrai.
        """
        plafonné = tuple(
            RankedQuest(chain=1, position=i, median_seconds=float(i), samples=1)
            for i in range(ALPHABET_QUEST_LIMIT)
        )

        avertissement = alphabet_cap_warning(plafonné)

        assert avertissement is not None
        assert str(ALPHABET_QUEST_LIMIT) in avertissement
