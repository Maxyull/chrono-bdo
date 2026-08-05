from __future__ import annotations

import pytest

from rubin.reading import BannerKind, BannerReading
from rubin.reference import Catalog, QuestId
from rubin.timing import Quality, Timeline

# Noms réels de la chaîne 21136, dans leur ordre de chaîne.
JERON = "[Calpheon] Jeron, la tacticienne"  # 21136/1
HARPIES = "[Calpheon] Cris stridents des harpies"  # 21136/2
COUP_DE_MAIN = "[Calpheon] Coup de main tant désiré"  # 21136/3
AUTRE_CHAINE = "[Serendia] Statue du dragon noir"  # 21130/147


def lecture(kind: BannerKind, nom: str, score: float = 0.97) -> BannerReading:
    return BannerReading(kind=kind, quest_name=nom, confidence=score)


@pytest.fixture
def timeline(catalog: Catalog) -> Timeline:
    return Timeline(catalog=catalog)


class TestMesureExacte:
    def test_mesure_une_quete_dont_on_voit_le_debut_et_la_fin(self, timeline: Timeline) -> None:
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=100.0)
        mesure = timeline.record(lecture(BannerKind.COMPLETED, JERON), at=142.5)
        assert mesure is not None
        assert mesure.quest_id == QuestId(21136, 1)
        assert mesure.seconds == pytest.approx(42.5)
        assert mesure.quality is Quality.EXACT

    def test_retient_le_score_le_plus_faible_des_deux_bandeaux(self, timeline: Timeline) -> None:
        timeline.record(lecture(BannerKind.ACCEPTED, JERON, 0.99), at=0.0)
        mesure = timeline.record(lecture(BannerKind.COMPLETED, JERON, 0.86), at=10.0)
        assert mesure is not None
        assert mesure.confidence == pytest.approx(0.86)

    def test_ignore_les_bandeaux_d_objectif(self, timeline: Timeline) -> None:
        # Ils racontent ce qui se passe pendant la quête, ils ne la bornent pas.
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        assert timeline.record(lecture(BannerKind.PARTIAL, JERON), at=5.0) is None
        assert timeline.record(lecture(BannerKind.OBJECTIVE_DONE, JERON), at=8.0) is None
        mesure = timeline.record(lecture(BannerKind.COMPLETED, JERON), at=20.0)
        assert mesure is not None
        assert mesure.seconds == pytest.approx(20.0)
        # Les quatre événements restent au journal pour l'analyse.
        assert len(timeline.events) == 4


class TestMesureDeduite:
    def test_deduit_la_fin_manquee_par_la_chaine(self, timeline: Timeline) -> None:
        """Régression : le bandeau de fin se rate quand on enchaîne vite.

        C'est le cas que le jeu impose. Voir démarrer 21136/2 prouve que
        21136/1 vient de s'achever, puisqu'une quête est identifiée par une
        paire chaîne/position. Sans cette déduction, un chronomètre resterait
        bloqué sur une quête terminée et fausserait tout ce qui suit.
        """
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        mesure = timeline.record(lecture(BannerKind.ACCEPTED, HARPIES), at=63.0)
        assert mesure is not None
        assert mesure.quest_id == QuestId(21136, 1)
        assert mesure.seconds == pytest.approx(63.0)
        assert mesure.quality is Quality.DEDUCED

    def test_enchaine_plusieurs_deductions(self, timeline: Timeline) -> None:
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        timeline.record(lecture(BannerKind.ACCEPTED, HARPIES), at=30.0)
        timeline.record(lecture(BannerKind.ACCEPTED, COUP_DE_MAIN), at=95.0)
        assert [m.quest_id.position for m in timeline.measures] == [1, 2]
        assert [m.seconds for m in timeline.measures] == pytest.approx([30.0, 65.0])

    def test_ne_deduit_rien_entre_deux_chaines_differentes(self, timeline: Timeline) -> None:
        # Rien ne dit ce qui s'est passé entre les deux : le joueur a pu faire
        # dix quêtes ailleurs. Mieux vaut un trou qu'une durée inventée.
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        assert timeline.record(lecture(BannerKind.ACCEPTED, AUTRE_CHAINE), at=500.0) is None
        assert timeline.measures == []
        assert timeline.dropped == 1

    def test_ne_deduit_rien_si_des_positions_manquent(self, timeline: Timeline) -> None:
        # 21136/1 puis 21136/3 : la deuxième quête a été faite sans être vue,
        # donc la durée de la première est inconnue.
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        assert timeline.record(lecture(BannerKind.ACCEPTED, COUP_DE_MAIN), at=90.0) is None
        assert timeline.measures == []


class TestCasDouteux:
    def test_ignore_une_fin_sans_debut(self, timeline: Timeline) -> None:
        # Le logiciel a démarré au milieu d'une quête : il n'y a pas d'instant
        # de départ, donc pas de durée.
        assert timeline.record(lecture(BannerKind.COMPLETED, JERON), at=10.0) is None
        assert timeline.measures == []

    def test_ignore_une_fin_qui_ne_correspond_pas_au_debut(self, timeline: Timeline) -> None:
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        assert timeline.record(lecture(BannerKind.COMPLETED, AUTRE_CHAINE), at=40.0) is None
        assert timeline.measures == []
        assert timeline.dropped == 1

    def test_ne_mesure_pas_une_quete_non_resolue(self, timeline: Timeline) -> None:
        # 18 % des quêtes principales partagent leur nom : le catalogue refuse
        # de trancher, et le journal ne mesure donc rien.
        inconnue = lecture(BannerKind.ACCEPTED, "[Calpheon] Quête qui n'existe pas")
        assert timeline.record(inconnue, at=0.0) is None
        assert timeline.record(lecture(BannerKind.COMPLETED, JERON), at=30.0) is None
        assert timeline.measures == []

    def test_garde_au_journal_ce_qu_il_ne_mesure_pas(self, timeline: Timeline) -> None:
        # Ce qui n'est pas mesurable aujourd'hui reste analysable plus tard.
        timeline.record(lecture(BannerKind.ACCEPTED, "[X] Inconnue"), at=0.0)
        assert len(timeline.events) == 1
        assert timeline.events[0].quest_id is None


class TestEtat:
    def test_expose_la_quete_en_cours(self, timeline: Timeline) -> None:
        assert timeline.pending_quest is None
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        assert timeline.pending_quest == QuestId(21136, 1)
        timeline.record(lecture(BannerKind.COMPLETED, JERON), at=10.0)
        assert timeline.pending_quest is None

    def test_additionne_les_durees(self, timeline: Timeline) -> None:
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        timeline.record(lecture(BannerKind.COMPLETED, JERON), at=20.0)
        timeline.record(lecture(BannerKind.ACCEPTED, HARPIES), at=25.0)
        timeline.record(lecture(BannerKind.COMPLETED, HARPIES), at=55.0)
        assert timeline.total_seconds() == pytest.approx(50.0)

    def test_utilise_son_horloge_quand_l_instant_n_est_pas_donne(
        self, catalog: Catalog
    ) -> None:
        instants = iter([1000.0, 1075.0])
        timeline = Timeline(catalog=catalog, clock=lambda: next(instants))
        timeline.record(lecture(BannerKind.ACCEPTED, JERON))
        mesure = timeline.record(lecture(BannerKind.COMPLETED, JERON))
        assert mesure is not None
        assert mesure.seconds == pytest.approx(75.0)
