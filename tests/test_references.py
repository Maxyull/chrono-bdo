from __future__ import annotations

from typing import Any

import pytest
import requests

from rubin.reference import QuestId
from rubin.references import (
    MIN_SAMPLES_PER_QUEST,
    ChainReference,
    Coverage,
    QuestReference,
    RankedQuest,
    ReferenceClient,
    ServerHealth,
)


class FakeResponse:
    def __init__(self, status: int, body: Any = None) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("pas de JSON")
        return self._body


def client_with(monkeypatch: pytest.MonkeyPatch, responses: list[Any]) -> ReferenceClient:
    """Client dont chaque appel réseau rend la réponse suivante de la liste."""
    calls = iter(responses)

    def fake_get(*_args: Any, **_kwargs: Any) -> Any:
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(requests, "get", fake_get)
    return ReferenceClient("https://exemple.test")


class TestComparaison:
    def test_dit_de_combien_on_est_plus_rapide(self) -> None:
        # Un écart relatif et non absolu : trente secondes de plus ne veulent
        # pas dire la même chose sur une quête d'une minute et sur une d'un
        # quart d'heure.
        reference = QuestReference(median_seconds=100.0, samples=10, fastest_seconds=50.0)
        assert reference.compare(50.0) == "50% plus rapide"
        assert reference.compare(150.0) == "50% plus lent"

    def test_ne_chicane_pas_sur_un_ecart_negligeable(self) -> None:
        reference = QuestReference(median_seconds=100.0, samples=10, fastest_seconds=50.0)
        assert reference.compare(102.0) == "dans la moyenne"

    def test_ne_divise_pas_par_une_mediane_nulle(self) -> None:
        assert QuestReference(0.0, 1, 0.0).compare(42.0) == ""


class TestReferenceClient:
    def test_ne_fait_rien_sans_serveur(self) -> None:
        client = ReferenceClient(None)
        assert not client.enabled
        assert client.quest(QuestId(1, 1)) is None

    def test_lit_une_reference_de_quete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = {"median_seconds": 90.0, "samples": 11, "fastest_seconds": 9.0}
        client = client_with(monkeypatch, [FakeResponse(200, body)])
        reference = client.quest(QuestId(21139, 46))
        assert reference == QuestReference(90.0, 11, 9.0)

    def test_ne_demande_qu_une_fois_la_meme_quete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = {"median_seconds": 90.0, "samples": 11, "fastest_seconds": 9.0}
        client = client_with(monkeypatch, [FakeResponse(200, body)])
        client.quest(QuestId(21139, 46))
        # Un second appel réseau lèverait StopIteration : la liste est épuisée.
        assert client.quest(QuestId(21139, 46)) is not None

    def test_retient_aussi_les_absences(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Régression : une quête jamais mesurée était redemandée sans fin.

        Le serveur répond 404, ce qui est une absence et non une panne. Sans
        mise en cache de cette absence, chaque passage sur la même quête
        relançait un appel pour obtenir la même réponse vide, en ajoutant sa
        latence à chaque fois.
        """
        client = client_with(monkeypatch, [FakeResponse(404)])
        assert client.quest(QuestId(9999, 1)) is None
        assert client.quest(QuestId(9999, 1)) is None  # aucun second appel
        assert client.failures == 0  # une absence n'est pas un échec

    def test_un_serveur_injoignable_devient_une_absence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Rien ne doit gêner la mesure : une panne réseau ôte la référence, pas
        # le chronométrage.
        client = client_with(monkeypatch, [requests.ConnectionError("coupé")])
        assert client.quest(QuestId(1, 1)) is None
        assert client.failures == 1

    def test_une_reponse_illisible_devient_une_absence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = client_with(monkeypatch, [FakeResponse(200, None)])
        assert client.quest(QuestId(1, 1)) is None
        assert client.failures == 1

    def test_lit_une_reference_de_chaine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = {
            "measured_quests": 11,
            "median_seconds": 90.0,
            "quests_per_hour": 40.0,
            "measured_total_seconds": 1212.0,
            "samples": 11,
        }
        client = client_with(monkeypatch, [FakeResponse(200, body)])
        assert client.chain(21139) == ChainReference(11, 90.0, 40.0, 1212.0, 11)


#: La réponse réelle de https://rubin.maxyull.fr/v1/couverture au 05/08/2026,
#: sur une base qui contient onze mesures d'un seul joueur.
COUVERTURE = {
    "well_measured": 0,
    "lightly_measured": 11,
    "threshold": 5,
    "measured_quests": 11,
}


class TestCouverture:
    def test_lit_la_couverture(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = client_with(monkeypatch, [FakeResponse(200, COUVERTURE)])
        assert client.coverage() == Coverage(
            well_measured=0, lightly_measured=11, threshold=5, measured_quests=11
        )

    def test_ne_la_demande_qu_une_fois(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = client_with(monkeypatch, [FakeResponse(200, COUVERTURE)])
        client.coverage()
        # Un second appel réseau lèverait StopIteration : la liste est épuisée.
        # L'affichage relit ce compteur, il ne doit pas retourner sur le réseau.
        assert client.coverage() is not None

    def test_ne_leve_jamais_quand_le_serveur_est_injoignable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression : un compteur ne doit pas emporter la fenêtre avec lui.

        C'est la règle du module, et elle vaut ici plus qu'ailleurs : la
        couverture est un décor, la mesure est la fonction. Un serveur
        injoignable, lent ou incohérent rend une absence d'information, jamais
        une exception qui remonterait dans la boucle de la fenêtre.

        Le cas est le quotidien du logiciel : `rubin fenetre` se lance sans
        `--envoyer` la plupart du temps, et le VPS n'est pas toujours joignable.
        """
        client = client_with(monkeypatch, [requests.ConnectionError("coupé")])
        assert client.coverage() is None
        assert client.failures == 1

    def test_une_reponse_illisible_devient_une_absence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = client_with(monkeypatch, [FakeResponse(200, None)])
        assert client.coverage() is None

    def test_ne_demande_rien_sans_serveur(self) -> None:
        assert ReferenceClient(None).coverage() is None

    def test_comble_les_champs_absents_sans_broncher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Un serveur d'une version antérieure, qui ne rendrait pas encore le
        # seuil. Mieux vaut un zéro lisible qu'une exception de clé.
        client = client_with(monkeypatch, [FakeResponse(200, {"lightly_measured": 11})])
        assert client.coverage() == Coverage(
            well_measured=0, lightly_measured=11, threshold=0, measured_quests=0
        )


#: La réponse réelle de https://rubin.maxyull.fr/sante au 05/08/2026.
SANTE = {
    "etat": "ok",
    "protocole": 1,
    "sessions": 4,
    "measures": 21,
    "players": 2,
    "linked": 0,
}


class TestClassementParQuete:
    def test_lit_les_lignes_du_classement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        corps = {
            "quetes": [
                {
                    "chain": 21139,
                    "position": 46,
                    "median_seconds": 90.0,
                    "samples": 11,
                    "fastest_seconds": 9.0,
                    "quete": "21139/46",
                }
            ],
            "min_echantillons": 3,
        }
        client = client_with(monkeypatch, [FakeResponse(200, corps)])

        classement = client.fastest_quests()

        assert classement == (RankedQuest(21139, 46, 90.0, 11),)
        assert classement[0].quest_id == QuestId(21139, 46)

    def test_une_liste_vide_n_est_pas_une_absence_de_reponse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression : les deux se ressemblent et ne disent pas la même chose.

        Cas réel du 05/08/2026, et c'est l'état du jour : la base contient
        vingt-et-une mesures, presque toutes uniques par quête, donc **aucune**
        n'atteint le seuil de trois. Le serveur rend une liste vide, ce qui est
        une réponse, et la fenêtre doit dire « aucune quête n'a encore assez de
        mesures ».

        Le même jour, le serveur en production ne connaissait pas encore cette
        adresse et rendait 404, ce qui est une absence de réponse, et la fenêtre
        doit dire « le serveur ne l'a pas donné ». Confondre les deux ferait
        affirmer que personne n'a assez mesuré alors qu'on n'en sait rien.
        """
        vide = client_with(monkeypatch, [FakeResponse(200, {"quetes": [], "min_echantillons": 3})])
        assert vide.fastest_quests() == ()

        périmé = client_with(monkeypatch, [FakeResponse(404)])
        assert périmé.fastest_quests() is None

    def test_demande_le_seuil_strictement_superieur_a_un(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vu: list[str] = []

        def faux_get(url: str, **_kwargs: Any) -> Any:
            vu.append(url)
            return FakeResponse(200, {"quetes": []})

        monkeypatch.setattr(requests, "get", faux_get)
        ReferenceClient("https://exemple.test").fastest_quests()

        assert MIN_SAMPLES_PER_QUEST > 1
        assert f"min_samples={MIN_SAMPLES_PER_QUEST}" in vu[0]

    def test_ecarte_une_ligne_malformee_sans_perdre_les_autres(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Ne lève jamais : une ligne écartée coûte une ligne, une exception
        # coûterait le classement entier et le fil qui l'a demandé.
        corps = {
            "quetes": [
                {"chain": "pas un nombre", "position": 1, "median_seconds": 10.0},
                {"chain": 21139, "position": 46, "median_seconds": 90.0, "samples": 11},
            ]
        }
        client = client_with(monkeypatch, [FakeResponse(200, corps)])
        assert client.fastest_quests() == (RankedQuest(21139, 46, 90.0, 11),)

    def test_ne_demande_qu_une_fois_le_meme_classement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = client_with(monkeypatch, [FakeResponse(200, {"quetes": []})])
        client.fastest_quests()
        # Un second appel réseau lèverait StopIteration : la liste est épuisée.
        assert client.fastest_quests() == ()

    def test_un_serveur_injoignable_devient_une_absence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = client_with(monkeypatch, [requests.ConnectionError("coupé")])
        assert client.fastest_quests() is None
        assert client.failures == 1

    def test_ne_demande_rien_sans_serveur(self) -> None:
        assert ReferenceClient(None).fastest_quests() is None


class TestEtatDuServeur:
    def test_lit_la_sante(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = client_with(monkeypatch, [FakeResponse(200, SANTE)])
        assert client.health() == ServerHealth(
            protocol=1, sessions=4, measures=21, players=2
        )

    def test_un_point_d_entree_manquant_n_est_pas_une_panne_de_connexion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression : le serveur joignable mais périmé, vu le 05/08/2026.

        `rubin.maxyull.fr` répondait parfaitement, mais rendait 404 sur
        `/v1/couverture` parce qu'il tournait sur une version antérieure au
        point d'entrée. Annoncer « le serveur n'a pas répondu » aurait envoyé
        chercher l'erreur exactement du mauvais côté, alors que le remède était
        un redéploiement.

        Le témoin de connexion ne regarde donc que `/sante`, qui existe depuis
        le premier jour : le serveur reste **connecté**, et c'est chaque
        compteur qui dit séparément qu'il n'a pas eu sa réponse.
        """
        client = client_with(
            monkeypatch, [FakeResponse(200, SANTE), FakeResponse(404), FakeResponse(404)]
        )

        assert client.health() is not None  # connecté
        assert client.coverage() is None  # mais ce compteur-là n'a rien
        assert client.fastest_quests() is None  # et celui-ci non plus
        assert client.failures == 0  # aucune panne à signaler

    def test_ne_leve_jamais_quand_le_serveur_est_injoignable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = client_with(monkeypatch, [requests.ConnectionError("coupé")])
        assert client.health() is None

    def test_ne_la_demande_qu_une_fois(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = client_with(monkeypatch, [FakeResponse(200, SANTE)])
        client.health()
        assert client.health() is not None

    def test_ne_demande_rien_sans_serveur(self) -> None:
        assert ReferenceClient(None).health() is None

    def test_comble_les_champs_absents_sans_broncher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = client_with(monkeypatch, [FakeResponse(200, {"etat": "ok"})])
        assert client.health() == ServerHealth(0, 0, 0, 0)

    def test_mesure_la_latence_de_sante(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Demandé par Maxime le 06/08/2026, pour l'afficher à côté de
        « connecté » dans la fenêtre, sans le lien du serveur.
        """
        client = client_with(monkeypatch, [FakeResponse(200, SANTE)])

        santé = client.health()

        assert santé is not None
        assert santé.latency_ms >= 0.0
