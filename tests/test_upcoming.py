"""Ce qui vient après la quête en cours.

Les trois chaînes employées ici sont de **vraies** chaînes du jeu, présentes
dans le jeu de test, et chacune illustre un cas distinct :

- `21136` est contiguë, positions 1, 2 et 3 : le cas normal ;
- `21130` porte un trou, positions 1, 2 puis **147** : le cas de 82 chaînes sur
  349 ;
- `21142` ne contient que des embranchements, positions 1 et 5, toutes deux
  marquées `[Carrefour]` : le cas de 69 quêtes réparties sur 38 chaînes.
"""

from __future__ import annotations

import pytest

from rubin.reference import Catalog, QuestId
from rubin.references import QuestReference, ReferenceClient
from rubin.upcoming import DEFAULT_COUNT, crossroads_ahead, upcoming

#: Chaîne contiguë, celle des captures qui ont servi à concevoir le logiciel.
CONTIGUE = 21136
#: Chaîne à trou : après la position 2 vient la 147.
A_TROU = 21130
#: Chaîne dont les deux quêtes connues sont des branches d'un choix.
CARREFOURS = 21142


class _ReferencesFigees(ReferenceClient):
    """Un serveur de références qui répond ce qu'on lui a dit, sans réseau."""

    def __init__(self, connues: dict[QuestId, QuestReference]) -> None:
        super().__init__(None)
        self._connues = connues

    def quest(self, quest_id: QuestId) -> QuestReference | None:
        return self._connues.get(quest_id)


class TestSuiteNormale:
    def test_montre_les_quetes_qui_suivent_dans_l_ordre(self, catalog: Catalog) -> None:
        suivantes = upcoming(catalog, CONTIGUE, after_position=1)

        assert [item.quest.id.position for item in suivantes] == [2, 3]
        assert suivantes[0].quest.name == "[Calpheon] Cris stridents des harpies"

    def test_exclut_la_quete_en_cours(self, catalog: Catalog) -> None:
        # On montre ce qui vient après, pas ce qu'on est en train de faire.
        suivantes = upcoming(catalog, CONTIGUE, after_position=2)
        assert [item.quest.id.position for item in suivantes] == [3]

    def test_ne_rend_rien_en_fin_de_chaine(self, catalog: Catalog) -> None:
        # Cas normal, pas une anomalie : il n'y a plus rien à faire ici.
        assert upcoming(catalog, CONTIGUE, after_position=3) == []

    def test_ne_rend_rien_sur_une_chaine_inconnue(self, catalog: Catalog) -> None:
        assert upcoming(catalog, 999_999, after_position=1) == []

    def test_borne_le_nombre_affiche(self, catalog: Catalog) -> None:
        assert len(upcoming(catalog, CONTIGUE, after_position=0, count=1)) == 1

    def test_zero_demande_ne_rend_rien(self, catalog: Catalog) -> None:
        assert upcoming(catalog, CONTIGUE, after_position=0, count=0) == []

    def test_un_compte_negatif_ne_rend_rien(self, catalog: Catalog) -> None:
        # Un `--suivantes -1` ne doit pas se comporter comme un découpage
        # Python, qui retirerait la dernière quête au lieu de n'en rendre aucune.
        assert upcoming(catalog, CONTIGUE, after_position=0, count=-1) == []


class TestTrousDeNumerotation:
    def test_saute_le_trou_au_lieu_de_s_arreter(self, catalog: Catalog) -> None:
        """Régression : la suite disparaissait dès le premier trou.

        Supposer que la quête suivante porte la position juste après ferait
        disparaître la suite de **82 chaînes sur 349**. Dans la chaîne 21130,
        après la position 2 vient la 147 : chercher la 3 ne rend rien, et le
        joueur se retrouve devant une liste vide au milieu d'une chaîne qui
        continue.

        C'est l'inverse du choix fait pour la déduction d'une fin manquée, dans
        `timing.py`, et la différence est délibérée. Déduire exige la
        contiguïté, parce qu'un trou peut cacher une quête réellement faite dont
        on inclurait le temps par erreur. Afficher n'exige rien : montrer la
        suite connue n'invente aucun chiffre.
        """
        suivantes = upcoming(catalog, A_TROU, after_position=2)

        assert [item.quest.id.position for item in suivantes] == [147]
        assert suivantes[0].quest.name == "[Serendia] Statue du dragon noir"

    def test_signale_le_trou_au_lieu_de_l_enjamber_en_silence(self, catalog: Catalog) -> None:
        """Régression : afficher 2 puis 147 laissait croire qu'elles se suivent.

        Deux causes se mélangent dans un trou, et elles n'ont pas les mêmes
        conséquences pour le joueur : soit la quête a été retirée du jeu, soit
        elle existe et manque à notre référentiel, qui connaît 18 999 quêtes
        quand le jeu en compte 19 235. Dans le second cas, le joueur verra à
        l'écran une quête que cette liste ne montre pas.

        On ne sait pas distinguer les deux, donc on annonce le trou.
        """
        suivantes = upcoming(catalog, A_TROU, after_position=2)

        assert suivantes[0].gap_before == 144  # de la position 3 à la 146

    def test_ne_signale_aucun_trou_sur_une_chaine_contigue(self, catalog: Catalog) -> None:
        suivantes = upcoming(catalog, CONTIGUE, after_position=1)
        assert [item.gap_before for item in suivantes] == [0, 0]

    def test_compte_le_trou_depuis_la_quete_precedente_de_la_liste(
        self, catalog: Catalog
    ) -> None:
        # Et non depuis la position de départ : sinon le second trou d'une
        # même liste serait compté depuis le point de départ et gonflerait.
        suivantes = upcoming(catalog, A_TROU, after_position=0)
        assert [(item.quest.id.position, item.gap_before) for item in suivantes] == [
            (1, 0),
            (2, 0),
            (147, 144),
        ]


class TestEmbranchements:
    def test_marque_les_branches_d_un_choix(self, catalog: Catalog) -> None:
        """Régression : les branches étaient présentées comme une suite à faire.

        69 quêtes principales, sur 38 chaînes, sont des branches d'un choix : le
        jeu en propose deux, le joueur en prend une et abandonne l'autre.
        Afficher « puis celle-ci, puis celle-là » donne un programme que
        personne ne peut suivre, et fait croire qu'il reste plus de travail
        qu'il n'y en a réellement.

        Le référentiel dit lesquelles sont des branches, mais **pas lesquelles
        s'excluent entre elles** : deux carrefours indépendants dans une même
        chaîne y sont indiscernables d'un seul choix à quatre branches. On les
        marque donc sans prétendre dire laquelle prendre.
        """
        suivantes = upcoming(catalog, CARREFOURS, after_position=0)

        assert [item.quest.id.position for item in suivantes] == [1, 5]
        assert all(item.is_crossroad for item in suivantes)
        assert crossroads_ahead(suivantes) == 2

    def test_ne_marque_rien_sur_une_chaine_sans_carrefour(self, catalog: Catalog) -> None:
        suivantes = upcoming(catalog, CONTIGUE, after_position=0)
        assert crossroads_ahead(suivantes) == 0
        assert not any(item.is_crossroad for item in suivantes)


class TestTempsDeReference:
    def test_rapporte_le_temps_connu_d_une_quete(self, catalog: Catalog) -> None:
        references = _ReferencesFigees(
            {QuestId(CONTIGUE, 2): QuestReference(252.0, samples=14, fastest_seconds=201.0)}
        )

        suivantes = upcoming(catalog, CONTIGUE, after_position=1, references=references)

        assert suivantes[0].is_measured
        assert suivantes[0].reference is not None
        assert suivantes[0].reference.median_seconds == 252.0
        assert suivantes[0].reference.samples == 14

    def test_une_quete_jamais_mesuree_reste_sans_temps(self, catalog: Catalog) -> None:
        # `None` veut dire « inconnu », jamais « instantané ». La distinction se
        # perdrait si on rendait un zéro ou une durée par défaut.
        references = _ReferencesFigees({})

        suivantes = upcoming(catalog, CONTIGUE, after_position=1, references=references)

        assert not suivantes[0].is_measured
        assert suivantes[0].reference is None

    def test_sans_client_de_references_rien_n_est_demande(self, catalog: Catalog) -> None:
        # Jouer sans serveur reste possible, et n'ôte rien à la liste elle-même.
        suivantes = upcoming(catalog, CONTIGUE, after_position=1)
        assert suivantes
        assert all(item.reference is None for item in suivantes)


class TestReglages:
    def test_le_defaut_tient_dans_un_coin_d_ecran(self) -> None:
        # Chaque quête inconnue du cache coûte un appel au serveur : en montrer
        # trente allongerait l'affichage sans que personne les lise.
        assert DEFAULT_COUNT == 5

    @pytest.mark.parametrize("langue", ["fr", "en"])
    def test_marche_dans_les_deux_langues(self, catalog: Catalog, langue: str) -> None:
        # L'identifiant est indépendant de la langue, donc la suite l'est aussi.
        suivantes = upcoming(catalog, CONTIGUE, after_position=1, language=langue)
        assert [item.quest.id.position for item in suivantes] == [2, 3]
