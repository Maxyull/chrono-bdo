from __future__ import annotations

import pytest

from rubin_bot.api import ChainTime, QuestTime
from rubin_bot.presentation import (
    FRAGILE_SAMPLES,
    chain_message,
    empty_ranking,
    format_duration,
    format_samples,
    never_measured_chain,
    never_measured_quest,
    quest_message,
    ranking_message,
)

QUETE = QuestTime(
    chain=21136,
    position=1,
    median_seconds=252.0,
    samples=11,
    fastest_seconds=182.0,
)

CHAINE = ChainTime(
    chain=21136,
    measured_quests=3,
    median_seconds=252.0,
    quests_per_hour=14.3,
    samples=11,
)


class TestDurees:
    @pytest.mark.parametrize(
        ("secondes", "attendu"),
        [
            (42.0, "42 s"),
            (252.0, "4 min 12 s"),
            (3_600.0, "1 h 00 min"),
            (7_845.0, "2 h 10 min"),
        ],
    )
    def test_ecrit_les_durees_comme_le_client(self, secondes: float, attendu: str) -> None:
        assert format_duration(secondes) == attendu

    def test_accorde_le_mot_mesure(self) -> None:
        assert format_samples(1) == "1 mesure"
        assert format_samples(11) == "11 mesures"


class TestQuete:
    def test_affiche_le_temps_et_ce_sur_quoi_il_repose(self) -> None:
        message = quest_message(QUETE)
        assert "4 min 12 s" in message
        assert "11 mesures" in message

    def test_aucun_temps_ne_s_affiche_sans_son_nombre_de_mesures(self) -> None:
        """Régression : une médiane sur une seule mesure n'est pas une référence.

        La base entière compte aujourd'hui onze mesures, toutes d'un seul
        joueur sur une seule chaîne. Un temps affiché seul se lirait comme une
        valeur établie, alors qu'il vient parfois d'un unique chronométrage.
        Le compte est donc collé au chiffre, dans le même message, et un temps
        fragile porte en plus sa marque.
        """
        unique = QuestTime(
            chain=21136,
            position=2,
            median_seconds=90.0,
            samples=1,
            fastest_seconds=90.0,
        )
        message = quest_message(unique)
        assert "1 mesure" in message
        assert "⚠️" in message
        assert f"moins de {FRAGILE_SAMPLES} mesures" in message

    def test_ne_marque_pas_un_temps_suffisamment_mesure(self) -> None:
        solide = QuestTime(
            chain=21136,
            position=1,
            median_seconds=252.0,
            samples=FRAGILE_SAMPLES,
            fastest_seconds=182.0,
        )
        assert "⚠️" not in quest_message(solide)

    def test_une_quete_jamais_mesuree_le_dit_en_toutes_lettres(self) -> None:
        """Régression : une colonne vide se lit « instantané », pas « inconnu ».

        Le client desktop est déjà passé par là, `__main__.py` écrit
        « jamais mesurée » plutôt qu'un blanc ou un zéro. Le robot doit tenir
        la même ligne : un salon Discord où une quête s'afficherait « 0 s »
        propagerait un chiffre faux à tous ceux qui le lisent.
        """
        message = never_measured_quest(21136, 99)
        assert "jamais mesurée" in message
        assert "0 s" not in message


class TestChaine:
    def test_affiche_le_rythme_et_le_nombre_de_mesures(self) -> None:
        message = chain_message(CHAINE)
        assert "14,3 quêtes par heure" in message
        assert "11 mesures" in message

    def test_n_annonce_jamais_une_duree_totale(self) -> None:
        """Régression : le débit médian annonçait 77 quêtes/heure, la session en a fait 36.

        Une durée totale bâtie sur des médianes ment du simple au double, et
        elle ment en restant plausible. Le message dit explicitement pourquoi
        il n'y en a pas, faute de quoi la prochaine personne l'ajouterait en
        croyant combler un oubli.
        """
        message = chain_message(CHAINE)
        assert "Pas de durée totale" in message
        # Trois quêtes à 252 s de médiane : le total tentant vaut 12 min 36 s.
        # Il ne doit apparaître sous aucune forme.
        assert format_duration(252.0 * CHAINE.measured_quests) not in message
        assert "756" not in message

    def test_une_chaine_jamais_mesuree_le_dit(self) -> None:
        assert "jamais mesurée" in never_measured_chain(3500)


class TestClassement:
    def test_chaque_ligne_porte_son_nombre_de_mesures(self) -> None:
        message = ranking_message([CHAINE], min_samples=3)
        assert "21136" in message
        assert "11 mesures" in message
        assert "à partir de 3 mesures" in message

    def test_un_classement_vide_dit_pourquoi(self) -> None:
        """Régression : aujourd'hui, presque toutes les réponses seront vides.

        Onze mesures d'un seul joueur sur une seule chaîne : un classement
        vide est l'état normal, et un message muet laisserait croire à une
        panne du robot ou du serveur.
        """
        message = empty_ranking(min_samples=3)
        assert "trop maigre" in message
        assert "3 mesures" in message

    def test_le_vide_passe_par_le_message_dedie(self) -> None:
        assert ranking_message([], min_samples=3) == empty_ranking(3)
