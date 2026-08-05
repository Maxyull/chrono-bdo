from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import pytest

from faux_serveur import faux_serveur
from rubin_bot.api import (
    MAX_CHAIN,
    MAX_POSITION,
    InvalidQuestNumber,
    RubinApi,
    ServerUnavailable,
)

T = TypeVar("T")

#: Réponses réelles du serveur, recopiées de `rubin_serveur.storage` : la
#: chaîne 21136 est celle sur laquelle les onze mesures de la base ont été
#: prises, et 21136/1 est « [Calpheon] Jeron, la tacticienne ».
QUETE_21136_1 = {
    "chain": 21136,
    "position": 1,
    "median_seconds": 252.0,
    "samples": 11,
    "fastest_seconds": 182.0,
    "quete": "21136/1",
}

CHAINE_21136 = {
    "chain": 21136,
    "measured_quests": 3,
    "median_seconds": 252.0,
    "quests_per_hour": 14.3,
    "samples": 11,
    "measured_total_seconds": 900.0,
    "unmeasured_quests": None,
}


def executer(fabrique: Callable[[RubinApi], Awaitable[T]], base_url: str, **options: Any) -> T:
    """Ouvre un client, exécute une coroutine, et referme la session."""

    async def aller() -> T:
        api = RubinApi(base_url=base_url, **options)
        try:
            return await fabrique(api)
        finally:
            await api.aclose()

    return asyncio.run(aller())


class TestQuete:
    def test_lit_le_temps_d_une_quete(self) -> None:
        with faux_serveur({"/v1/quetes/21136/1": (200, QUETE_21136_1)}) as base:
            quete = executer(lambda api: api.quest(21136, 1), base)
        assert quete is not None
        assert quete.median_seconds == 252.0
        assert quete.samples == 11
        assert quete.fastest_seconds == 182.0

    def test_une_quete_jamais_mesuree_rend_none(self) -> None:
        with faux_serveur({}) as base:
            assert executer(lambda api: api.quest(21136, 99), base) is None

    def test_un_champ_manquant_est_une_panne_pas_un_zero(self) -> None:
        """Régression : une réponse tronquée ne doit pas devenir un temps de zéro.

        Le principe du projet est que rater une mesure donne un chiffre
        incomplet, tandis qu'en inventer une donne un chiffre faux. Si le
        serveur rendait un objet sans `median_seconds`, un `.get(clé, 0)`
        complaisant afficherait « 0 s », c'est-à-dire une quête instantanée,
        et ce chiffre-là entrerait dans la tête des joueurs sans jamais en
        ressortir. On préfère dire que le serveur n'a pas répondu.
        """
        tronquee = {"chain": 21136, "position": 1, "samples": 11}
        with faux_serveur({"/v1/quetes/21136/1": (200, tronquee)}) as base, pytest.raises(
            ServerUnavailable
        ):
            executer(lambda api: api.quest(21136, 1), base)


class TestChaine:
    def test_lit_le_debit_d_une_chaine(self) -> None:
        with faux_serveur({"/v1/chaines/21136": (200, CHAINE_21136)}) as base:
            chaine = executer(lambda api: api.chain(21136), base)
        assert chaine is not None
        assert chaine.quests_per_hour == 14.3
        assert chaine.measured_quests == 3

    def test_ne_retient_jamais_la_somme_des_medianes(self) -> None:
        """Régression : `measured_total_seconds` ne doit exister nulle part ici.

        Le serveur le publie, et c'est le champ le plus dangereux de toute
        l'API : sur une session réelle, le rythme médian annonçait 77 quêtes
        par heure là où la session en avait produit 36. Un total bâti dessus
        ment du simple au double, en restant plausible et précis. La seule
        protection qui tienne dans le temps est de ne pas le lire du tout : ce
        test casse le jour où quelqu'un l'ajoute au modèle « pour l'avoir sous
        la main ».
        """
        with faux_serveur({"/v1/chaines/21136": (200, CHAINE_21136)}) as base:
            chaine = executer(lambda api: api.chain(21136), base)
        assert chaine is not None
        assert not hasattr(chaine, "measured_total_seconds")

    def test_une_chaine_jamais_mesuree_rend_none(self) -> None:
        with faux_serveur({}) as base:
            assert executer(lambda api: api.chain(3500), base) is None


class TestClassement:
    def test_lit_le_classement(self) -> None:
        route = "/v1/chaines?limit=10&min_samples=3"
        with faux_serveur({route: (200, {"chaines": [CHAINE_21136], "min_echantillons": 3})}) as b:
            chaines = executer(lambda api: api.ranking(limit=10, min_samples=3), b)
        assert [c.chain for c in chaines] == [21136]

    def test_un_classement_vide_est_une_reponse_valable(self) -> None:
        route = "/v1/chaines?limit=10&min_samples=3"
        with faux_serveur({route: (200, {"chaines": [], "min_echantillons": 3})}) as base:
            assert executer(lambda api: api.ranking(limit=10, min_samples=3), base) == []

    def test_borne_la_taille_demandee(self) -> None:
        # Un message Discord tient dans deux mille caractères : la demande est
        # ramenée au maximum affichable avant même de partir.
        route = "/v1/chaines?limit=25&min_samples=3"
        with faux_serveur({route: (200, {"chaines": [], "min_echantillons": 3})}) as base:
            assert executer(lambda api: api.ranking(limit=10_000, min_samples=3), base) == []


class TestPannes:
    def test_un_serveur_injoignable_leve_une_panne(self) -> None:
        # Port fermé : la connexion est refusée immédiatement.
        with pytest.raises(ServerUnavailable):
            executer(lambda api: api.quest(21136, 1), "http://127.0.0.1:1", timeout=1.0)

    def test_un_serveur_lent_est_coupe_par_le_delai(self) -> None:
        """Régression : un serveur qui accepte puis se tait ne doit pas figer le robot.

        Sans délai d'attente, la commande Discord resterait sur « réfléchit... »
        pour toujours, et le joueur n'apprendrait jamais pourquoi. Le port est
        ouvert et la réponse arrive, mais trop tard : c'est le cas qu'aucun
        test de connexion refusée ne couvre.
        """
        routes = {"/v1/quetes/21136/1": (200, QUETE_21136_1)}
        with faux_serveur(routes, delai=1.5) as base, pytest.raises(ServerUnavailable):
            executer(lambda api: api.quest(21136, 1), base, timeout=0.3)

    def test_une_erreur_serveur_leve_une_panne(self) -> None:
        routes = {"/v1/chaines/21136": (500, {"detail": "boum"})}
        with faux_serveur(routes) as base, pytest.raises(ServerUnavailable):
            executer(lambda api: api.chain(21136), base)

    def test_du_json_illisible_leve_une_panne(self) -> None:
        routes = {"/v1/chaines/21136": (200, "<html>maintenance</html>")}
        with faux_serveur(routes) as base, pytest.raises(ServerUnavailable):
            executer(lambda api: api.chain(21136), base)

    def test_un_classement_introuvable_est_une_panne_pas_un_vide(self) -> None:
        # 404 sur le classement veut dire que l'adresse a changé, pas qu'il n'y
        # a aucune chaîne : le dire évite d'annoncer une base vide à tort.
        with faux_serveur({}) as base, pytest.raises(ServerUnavailable):
            executer(lambda api: api.ranking(limit=10, min_samples=3), base)


class TestValidation:
    @pytest.mark.parametrize("chaine", [0, -1, MAX_CHAIN + 1])
    def test_refuse_un_numero_de_chaine_hors_bornes(self, chaine: int) -> None:
        with pytest.raises(InvalidQuestNumber):
            executer(lambda api: api.chain(chaine), "http://127.0.0.1:1")

    @pytest.mark.parametrize("position", [0, -3, MAX_POSITION + 1])
    def test_refuse_une_position_hors_bornes(self, position: int) -> None:
        with pytest.raises(InvalidQuestNumber):
            executer(lambda api: api.quest(21136, position), "http://127.0.0.1:1")

    def test_valide_avant_d_ouvrir_la_moindre_connexion(self) -> None:
        """Régression : les nombres viennent d'un salon Discord, donc de n'importe qui.

        La validation a lieu avant l'appel réseau, sur une adresse dont le port
        est fermé : si le contrôle passait après, le test échouerait sur une
        panne réseau au lieu de la valeur refusée. C'est la garantie que rien
        d'inspiré par un inconnu n'atteint une URL sans avoir été borné.
        """
        with pytest.raises(InvalidQuestNumber):
            executer(lambda api: api.quest(-42, 1), "http://127.0.0.1:1")
