from __future__ import annotations

from typing import Any

import pytest
import requests

from chrono.reference import QuestId
from chrono.references import ChainReference, QuestReference, ReferenceClient


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
