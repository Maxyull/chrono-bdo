from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from faux_serveur import faux_serveur
from rubin_bot.api import RubinApi
from rubin_bot.commands import answer_chain, answer_quest, answer_ranking
from rubin_bot.presentation import UNAVAILABLE
from test_api import CHAINE_21136, QUETE_21136_1


def repondre(reponse: Callable[[RubinApi], Awaitable[str]], base_url: str) -> str:
    """Fabrique un client, exécute la réponse, et referme la session."""

    async def aller() -> str:
        api = RubinApi(base_url=base_url)
        try:
            return await reponse(api)
        finally:
            await api.aclose()

    return asyncio.run(aller())


class TestReponses:
    def test_repond_le_temps_d_une_quete(self) -> None:
        with faux_serveur({"/v1/quetes/21136/1": (200, QUETE_21136_1)}) as base:
            reponse = repondre(lambda api: answer_quest(api, 21136, 1), base)
        assert "4 min 12 s" in reponse
        assert "11 mesures" in reponse

    def test_repond_le_debit_d_une_chaine(self) -> None:
        with faux_serveur({"/v1/chaines/21136": (200, CHAINE_21136)}) as base:
            reponse = repondre(lambda api: answer_chain(api, 21136), base)
        assert "14,3 quêtes par heure" in reponse

    def test_repond_le_classement(self) -> None:
        route = "/v1/chaines?limit=10&min_samples=3"
        corps = {"chaines": [CHAINE_21136], "min_echantillons": 3}
        with faux_serveur({route: (200, corps)}) as base:
            reponse = repondre(lambda api: answer_ranking(api, limit=10, min_samples=3), base)
        assert "Chaînes les plus rapides" in reponse
        assert "11 mesures" in reponse

    def test_dit_jamais_mesuree_sur_une_quete_absente(self) -> None:
        with faux_serveur({}) as base:
            reponse = repondre(lambda api: answer_quest(api, 21136, 99), base)
        assert "jamais mesurée" in reponse


class TestPannes:
    def test_une_panne_reseau_donne_une_phrase_pas_une_trace(self) -> None:
        """Régression : un serveur injoignable ne doit ni tuer le robot ni cracher une trace.

        Le serveur Rubin tourne en systemd derrière Caddy sur un VPS à deux
        giga-octets : il redémarre, il est parfois lent. Si l'exception
        remontait jusqu'à Discord, le joueur verrait « l'application ne répond
        pas », ce qui ne dit ni ce qui s'est passé ni s'il faut réessayer.
        """
        # Port fermé : la connexion est refusée sans attendre.
        reponse = repondre(lambda api: answer_quest(api, 21136, 1), "http://127.0.0.1:1")
        assert reponse == UNAVAILABLE
        assert "Traceback" not in reponse

    def test_une_panne_n_est_pas_confondue_avec_une_absence(self) -> None:
        """Régression : « jamais mesurée » et « serveur en panne » ne sont pas la même chose.

        Le premier est une information sur la quête, le second n'en est pas
        une. Les confondre ferait dire au robot que personne n'a mesuré une
        quête qu'il n'a en réalité pas su interroger, et ce chiffre-là serait
        faux au sens du projet : incomplet est acceptable, faux ne l'est pas.
        """
        panne = repondre(lambda api: answer_chain(api, 21136), "http://127.0.0.1:1")
        with faux_serveur({}) as base:
            absence = repondre(lambda api: answer_chain(api, 21136), base)
        assert panne != absence
        assert "jamais mesurée" not in panne
        assert "jamais mesurée" in absence

    def test_un_classement_en_panne_ne_devient_pas_un_classement_vide(self) -> None:
        reponse = repondre(lambda api: answer_ranking(api, limit=10), "http://127.0.0.1:1")
        assert reponse == UNAVAILABLE


class TestNombresHostiles:
    def test_un_numero_absurde_donne_un_refus_lisible(self) -> None:
        """Régression : les paramètres viennent d'un salon Discord, donc d'inconnus.

        Discord borne déjà les entiers côté client, mais rien n'oblige un
        appelant à passer par son interface. Le refus se produit avant toute
        requête, et se lit en français au lieu de remonter en `ValueError`.
        """
        reponse = repondre(lambda api: answer_chain(api, -1), "http://127.0.0.1:1")
        assert "invalide" in reponse
        assert "Traceback" not in reponse

    def test_une_position_absurde_donne_un_refus_lisible(self) -> None:
        reponse = repondre(lambda api: answer_quest(api, 21136, 10_000), "http://127.0.0.1:1")
        assert "invalide" in reponse
