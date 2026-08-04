from __future__ import annotations

import pytest

from chrono.reference import KIND_DAILY, KIND_MAIN, Chain, Quest, QuestId


def make_quest(
    chain: int, position: int, region: str | None = None, kind: int = KIND_MAIN
) -> Quest:
    return Quest(
        id=QuestId(chain, position),
        name=f"[Test] quête {position}",
        prefix="Test",
        title=f"quête {position}",
        region=region,
        kind=kind,
        level=1,
    )


class TestQuestId:
    def test_lit_une_paire_chaine_position(self) -> None:
        assert QuestId.parse("21136/1") == QuestId(21136, 1)

    def test_se_reecrit_a_l_identique(self) -> None:
        assert str(QuestId.parse("21130/147")) == "21130/147"

    @pytest.mark.parametrize(
        "brut",
        ["21136", "", "/", "21136/", "/1", "21136/1/2", "abc/1", "21136/x", "2113 6/1"],
    )
    def test_refuse_ce_qui_n_est_pas_une_paire(self, brut: str) -> None:
        # Le référentiel est une source externe : une forme inattendue doit
        # s'arrêter ici plutôt que de devenir un identifiant plausible et faux.
        with pytest.raises(ValueError, match="illisible"):
            QuestId.parse(brut)

    def test_se_trie_par_chaine_puis_position(self) -> None:
        ids = [QuestId(21136, 2), QuestId(8700, 12), QuestId(21136, 1)]
        assert sorted(ids) == [QuestId(8700, 12), QuestId(21136, 1), QuestId(21136, 2)]


class TestQuest:
    def test_reconnait_une_quete_principale(self) -> None:
        assert make_quest(1, 1, kind=KIND_MAIN).is_main

    def test_ecarte_une_quete_repetable(self) -> None:
        # Chronométrer une quête qu'on refait tous les jours n'a pas de sens :
        # il n'y a pas de « fois » à comparer.
        assert not make_quest(1, 1, kind=KIND_DAILY).is_main


class TestChain:
    def test_prend_le_nom_de_sa_premiere_quete(self) -> None:
        chain = Chain(42, (make_quest(42, 1), make_quest(42, 2)))
        assert chain.name == "[Test] quête 1"

    def test_survit_a_une_chaine_vide(self) -> None:
        assert Chain(42, ()).name == "chaîne 42"

    def test_est_contigue_quand_les_positions_vont_de_1_a_n(self) -> None:
        chain = Chain(42, tuple(make_quest(42, n) for n in (1, 2, 3)))
        assert chain.is_contiguous

    def test_n_est_pas_contigue_avec_un_trou(self) -> None:
        # Cas réel : la chaîne 21130 contient une position 147 alors qu'elle
        # compte 123 quêtes. Des quêtes ont été retirées du jeu.
        chain = Chain(42, tuple(make_quest(42, n) for n in (1, 2, 147)))
        assert not chain.is_contiguous

    def test_deduit_la_region_dominante(self) -> None:
        quests = (
            make_quest(42, 1, region="Serendia"),
            make_quest(42, 2, region="Serendia"),
            make_quest(42, 3, region="Calpheon"),
        )
        assert Chain(42, quests).region == "Serendia"

    def test_n_invente_pas_de_region_quand_aucune_n_est_connue(self) -> None:
        chain = Chain(42, (make_quest(42, 1), make_quest(42, 2)))
        assert chain.region is None

    def test_sa_longueur_est_son_nombre_de_quetes(self) -> None:
        assert len(Chain(42, tuple(make_quest(42, n) for n in (1, 2, 3)))) == 3
