from __future__ import annotations

from typing import Any

import pytest
import requests

from rubin import discord
from rubin.discord import DiscordAccount, fetch_account


class FakeResponse:
    def __init__(self, status: int, body: Any = None) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("pas de JSON")
        return self._body


class TestFetchAccount:
    def test_lit_le_pseudonyme_rattache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            discord.requests,
            "get",
            lambda *a, **k: FakeResponse(200, {"rattache": True, "nom": "maxyull"}),
        )

        assert fetch_account("https://rubin.maxyull.fr", "a" * 32) == DiscordAccount(
            linked=True, name="maxyull"
        )

    def test_envoie_lidentifiant_en_parametre_et_non_dans_le_chemin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L'identifiant anonyme tient lieu de mot de passe (voir la docstring
        de `/v1/discord/connexion`). Dans le chemin, il finirait recopié tel
        quel dans les journaux d'accès du serveur ET du mandataire."""
        vus: list[dict[str, Any]] = []

        def faux_get(url: str, **kwargs: Any) -> FakeResponse:
            vus.append({"url": url, **kwargs})
            return FakeResponse(200, {"rattache": False, "nom": None})

        monkeypatch.setattr(discord.requests, "get", faux_get)

        fetch_account("https://rubin.maxyull.fr", "a" * 32)

        assert vus[0]["url"] == "https://rubin.maxyull.fr/v1/discord/compte"
        assert vus[0]["params"] == {"player": "a" * 32}

    def test_un_serveur_muet_rend_on_ne_sait_pas_et_non_non_rattache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression, le cœur de ce module : « on ne sait pas » et « pas
        rattaché » ne sont PAS la même réponse.

        Cas réel du 06/08/2026 : le compte de Maxime était rattaché depuis des
        heures, le serveur avait rendu `{"rattache":true,"nom":"maxyull"}`. Si
        une panne de réseau se lisait « pas encore connecté », la fenêtre
        l'enverrait refaire un rattachement déjà fait, avec la certitude
        tranquille de quelqu'un qui n'a rien vérifié.

        C'est le principe du projet appliqué à l'affichage : rater une
        information donne un écran incomplet, en inventer une donne un écran
        faux.
        """

        def injoignable(*_a: Any, **_k: Any) -> FakeResponse:
            raise requests.ConnectionError("réseau coupé")

        monkeypatch.setattr(discord.requests, "get", injoignable)

        assert fetch_account("https://rubin.maxyull.fr", "a" * 32) is None

    def test_un_point_dentree_absent_rend_on_ne_sait_pas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression jumelle, cas réel du 05/08/2026 consigné dans `ETAT.md` :
        `rubin.maxyull.fr` répondait parfaitement mais rendait 404 sur un point
        d'entrée qu'une version antérieure n'avait pas. Un serveur d'avant
        cette route est exactement ce cas, et il ne dit rien du rattachement."""
        monkeypatch.setattr(
            discord.requests, "get", lambda *a, **k: FakeResponse(404)
        )

        assert fetch_account("https://rubin.maxyull.fr", "a" * 32) is None

    def test_une_reponse_illisible_rend_on_ne_sait_pas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Un mandataire qui rend une page HTML avec un code 200 : le corps
        # n'est pas du JSON, ou pas un objet. Ni l'un ni l'autre ne dit quoi
        # que ce soit du rattachement.
        monkeypatch.setattr(
            discord.requests, "get", lambda *a, **k: FakeResponse(200, ["pas un objet"])
        )

        assert fetch_account("https://rubin.maxyull.fr", "a" * 32) is None

    def test_ne_demande_rien_sans_serveur(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Lancé sans --envoyer : il n'y a personne à qui poser la question.
        def interdit(*_a: Any, **_k: Any) -> FakeResponse:
            raise AssertionError("aucune requête ne doit partir sans serveur")

        monkeypatch.setattr(discord.requests, "get", interdit)

        assert fetch_account(None, "a" * 32) is None
        assert fetch_account("https://rubin.maxyull.fr", "") is None


class TestDisplayName:
    def test_rend_le_nom_quand_il_y_en_a_un(self) -> None:
        assert DiscordAccount(linked=True, name="maxyull").display_name == "maxyull"

    def test_ne_rend_rien_quand_le_compte_nest_pas_rattache(self) -> None:
        assert DiscordAccount(linked=False, name=None).display_name is None

    def test_un_rattachement_sans_nom_ne_rend_pas_de_nom(self) -> None:
        """Le serveur annonce un rattachement mais ne donne aucun pseudonyme :
        il n'y a rien à écrire, et « connecté comme  » avec un blanc à la fin
        se lirait comme un défaut d'affichage."""
        assert DiscordAccount(linked=True, name=None).display_name is None
