"""Ce que l'interface affiche, éprouvé sans écran.

Rien ici ne touche à Tk : ce sont des états qui entrent et des chaînes qui
sortent. Une fenêtre mal dessinée se voit ; un temps mal formaté ou un compte de
mesures oublié se croit.
"""

from __future__ import annotations

import pytest

from rubin.capture import Rect, banner_region, tracker_region
from rubin.interface import (
    FRAGILE_BELOW,
    ZoneState,
    describe_conflict,
    describe_reading,
    describe_zone,
    format_duration,
    format_gap,
    format_reference,
    format_upcoming_line,
)
from rubin.reference import Quest, QuestId
from rubin.references import QuestReference
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
