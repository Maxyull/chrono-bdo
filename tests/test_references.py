from __future__ import annotations

from typing import Any

import pytest
import requests

from rubin.reference import QuestId
from rubin.references import ChainReference, Coverage, QuestReference, ReferenceClient


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
