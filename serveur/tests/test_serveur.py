from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from rubin.protocol import PROTOCOL_VERSION, MeasurePayload, SessionPayload

from rubin_serveur import main
from rubin_serveur.storage import Storage


@pytest.fixture(autouse=True)
def base_vierge() -> None:
    # Chaque test part d'une base neuve : des mesures qui survivraient d'un
    # test à l'autre fausseraient les médianes, donc les vérifications.
    main.storage = Storage("sqlite+pysqlite:///:memory:")


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


def lot(*durees: float, player: str = "joueur1", quest: str = "21136/1") -> dict:
    return {
        "player": player,
        "language": "fr",
        "catalog_date": "2026-08-05",
        "protocol": PROTOCOL_VERSION,
        "client": "0.1.0",
        "dropped": 0,
        "measures": [
            {"quest": quest, "seconds": d, "quality": "exacte", "confidence": 0.97} for d in durees
        ],
    }


class TestSante:
    def test_repond_sans_compte(self, client: TestClient) -> None:
        # La lecture est publique : imposer une inscription pour voir un temps
        # médian n'ajouterait aucune sécurité et retirerait la moitié des
        # lecteurs.
        reponse = client.get("/sante")
        assert reponse.status_code == 200
        assert reponse.json()["protocole"] == PROTOCOL_VERSION


class TestEnvoi:
    def test_accepte_un_lot_valide(self, client: TestClient) -> None:
        reponse = client.post("/v1/sessions", json=lot(42.0, 51.0))
        assert reponse.status_code == 201
        assert reponse.json() == {"enregistrees": 2, "refusees": 0}

    def test_refuse_les_durees_invraisemblables(self, client: TestClient) -> None:
        """Régression : le serveur ne croit aucun client, y compris le sien.

        Le client filtre déjà, mais un temps mesuré chez un joueur est une
        affirmation, pas une observation. Rien n'empêche quiconque d'en
        fabriquer, et une mesure fausse entre dans les médianes sans jamais en
        ressortir.
        """
        reponse = client.post("/v1/sessions", json=lot(0.1, 42.0, 999999.0))
        assert reponse.json() == {"enregistrees": 1, "refusees": 2}

    def test_refuse_un_protocole_trop_ancien(self, client: TestClient) -> None:
        envoi = lot(42.0)
        envoi["protocol"] = PROTOCOL_VERSION - 5
        reponse = client.post("/v1/sessions", json=envoi)
        assert reponse.status_code == 409
        assert "mettez le logiciel à jour" in reponse.json()["detail"]

    def test_refuse_un_protocole_venu_du_futur(self, client: TestClient) -> None:
        envoi = lot(42.0)
        envoi["protocol"] = PROTOCOL_VERSION + 1
        assert client.post("/v1/sessions", json=envoi).status_code == 409

    def test_refuse_un_lot_demesure(self, client: TestClient) -> None:
        # Une session très longue produit quelques centaines de mesures. Un
        # millier, c'est un envoi fabriqué ou un logiciel qui a mal tourné.
        reponse = client.post("/v1/sessions", json=lot(*([42.0] * 1001)))
        assert reponse.status_code == 413

    def test_refuse_un_lot_illisible(self, client: TestClient) -> None:
        assert client.post("/v1/sessions", json={"n_importe": "quoi"}).status_code == 422

    def test_ecarte_un_identifiant_de_quete_malforme(self, client: TestClient) -> None:
        reponse = client.post("/v1/sessions", json=lot(42.0, quest="pas-un-identifiant"))
        assert reponse.json()["enregistrees"] == 0


class TestStatistiques:
    def test_classe_sur_la_mediane_et_non_sur_le_record(self, client: TestClient) -> None:
        """Régression : un record se falsifie, une médiane beaucoup moins.

        Un joueur qui déclare une quête faite en une seconde s'empare d'un
        record en un seul envoi. Il ne déplace pas la médiane de dizaines de
        mesures honnêtes. Et la médiane est de toute façon le chiffre utile :
        il s'agit de prévoir une durée, pas de couronner un champion.
        """
        client.post("/v1/sessions", json=lot(40.0, 50.0, 60.0, 1.0))
        stats = client.get("/v1/quetes/21136/1").json()
        assert stats["median_seconds"] == 45.0
        assert stats["fastest_seconds"] == 1.0
        assert stats["samples"] == 4

    def test_ne_rend_rien_pour_une_quete_jamais_mesuree(self, client: TestClient) -> None:
        assert client.get("/v1/quetes/9999/1").status_code == 404

    def test_donne_le_debit_d_une_chaine(self, client: TestClient) -> None:
        client.post("/v1/sessions", json=lot(60.0, quest="21136/1"))
        client.post("/v1/sessions", json=lot(60.0, quest="21136/2"))
        stats = client.get("/v1/chaines/21136").json()
        assert stats["measured_quests"] == 2
        assert stats["quests_per_hour"] == 60.0

    def test_classe_les_chaines_par_debit(self, client: TestClient) -> None:
        client.post("/v1/sessions", json=lot(10.0, 10.0, 10.0, quest="100/1"))
        client.post("/v1/sessions", json=lot(600.0, 600.0, 600.0, quest="200/1"))
        chaines = client.get("/v1/chaines?min_samples=1").json()["chaines"]
        assert [c["chain"] for c in chaines] == [100, 200]

    def test_ecarte_les_chaines_trop_peu_mesurees(self, client: TestClient) -> None:
        # Une médiane sur un seul échantillon n'est pas une médiane, et une
        # telle ligne en tête décrédibiliserait tout le classement.
        client.post("/v1/sessions", json=lot(10.0, quest="100/1"))
        assert client.get("/v1/chaines?min_samples=5").json()["chaines"] == []


class TestStockage:
    def test_compte_les_joueurs_distincts(self) -> None:
        stockage = Storage("sqlite+pysqlite:///:memory:")
        for nom in ("a", "a", "b"):
            stockage.store(
                SessionPayload(
                    player=nom,
                    language="fr",
                    catalog_date="2026-08-05",
                    measures=(MeasurePayload("1/1", 42.0, "exacte", 0.9),),
                )
            )
        assert stockage.counts() == {
            "sessions": 3,
            "measures": 3,
            "players": 2,
            # Personne n'a rattaché de compte Discord : contribuer n'en demande
            # aucun, et la plupart des contributeurs resteront anonymes.
            "linked": 0,
        }


class TestTempsTotal:
    def test_somme_les_medianes_plutot_que_de_les_moyenner(self, client: TestClient) -> None:
        """Régression : le débit médian ne sert pas à prévoir une durée.

        Mesuré sur une session réelle de huit quêtes : le débit au rythme
        médian annonçait 77 quêtes par heure, là où la session en avait
        réellement produit 36. La médiane écrase les quêtes longues, or il
        faudra bien les faire. Les deux chiffres sont justes et répondent à
        deux questions différentes ; les confondre ferait sous-estimer de
        moitié le temps d'une chaîne.
        """
        for position, duree in ((1, 10.0), (2, 10.0), (3, 10.0), (4, 600.0)):
            client.post("/v1/sessions", json=lot(duree, quest=f"300/{position}"))
        stats = client.get("/v1/chaines/300").json()

        # Le total dit la vérité : il faudra bien faire la quête de dix minutes.
        assert stats["measured_total_seconds"] == pytest.approx(630.0)

        # Le débit médian, lui, l'ignore : au rythme de la quête médiane, ces
        # quatre quêtes sembleraient tenir en moins d'une minute, soit dix fois
        # moins que la réalité.
        au_rythme_median = 4 * 3600 / stats["quests_per_hour"]
        assert au_rythme_median < stats["measured_total_seconds"] / 10


class TestVersion:
    def test_annonce_la_version_et_le_lien(self, client: TestClient) -> None:
        corps = client.get("/v1/version").json()
        assert corps["protocole"] == PROTOCOL_VERSION
        assert corps["telechargement"].startswith("https://")

    def test_repond_sans_condition(self, client: TestClient) -> None:
        """Régression : un client trop vieux doit pouvoir l'apprendre.

        Si cette adresse exigeait un protocole à jour, un logiciel devenu trop
        ancien pour envoyer ses mesures serait aussi incapable de découvrir
        qu'il est trop ancien, et resterait bloqué sans le savoir.
        """
        assert client.get("/v1/version").status_code == 200


class TestDiscord:
    def test_signe_et_relit_un_etat(self) -> None:
        from rubin_serveur.discord import read_state, sign_state

        assert read_state(sign_state("joueur42", "secret"), "secret") == "joueur42"

    def test_refuse_un_etat_falsifie(self) -> None:
        """Régression : sans signature, on peut voler les temps d'un autre.

        Discord renvoie l'état tel quel au retour. Non signé, n'importe qui
        pourrait forger un retour rattachant son propre compte Discord au
        numéro d'un autre contributeur, et s'attribuer ses mesures.
        """
        from rubin_serveur.discord import read_state, sign_state

        vrai = sign_state("joueur42", "secret")
        falsifie = "victime." + vrai.partition(".")[2]
        assert read_state(falsifie, "secret") is None

    def test_refuse_un_etat_sans_signature(self) -> None:
        from rubin_serveur.discord import read_state

        assert read_state("joueur42", "secret") is None
        assert read_state("", "secret") is None

    def test_ne_se_configure_pas_sans_identifiants(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Absente n'est pas une erreur : le serveur doit tourner sans connexion
        # Discord et le dire, plutôt que de refuser de démarrer.
        from rubin_serveur.discord import DiscordConfig

        monkeypatch.delenv("RUBIN_DISCORD_ID", raising=False)
        monkeypatch.delenv("RUBIN_DISCORD_SECRET", raising=False)
        assert DiscordConfig.from_env() is None

    def test_ne_demande_que_l_identite(self) -> None:
        # Ni courriel, ni serveurs fréquentés, ni liste d'amis : ce qu'on ne
        # demande pas ne peut pas fuiter.
        from rubin_serveur.discord import SCOPE, DiscordConfig, authorize_url

        config = DiscordConfig("id", "secret", "https://exemple.test/retour", "etat")
        url = authorize_url(config, "joueur42")
        assert SCOPE == "identify"
        assert "scope=identify" in url
        assert "email" not in url

    def test_rattache_un_compte_et_le_retrouve(self) -> None:
        stockage = Storage("sqlite+pysqlite:///:memory:")
        assert stockage.display_name("joueur42") is None
        stockage.link_discord("joueur42", "9876", "Maxyull")
        assert stockage.display_name("joueur42") == "Maxyull"

    def test_met_a_jour_un_rattachement_existant(self) -> None:
        # Les pseudonymes Discord changent : on garde le dernier connu plutôt
        # que d'afficher indéfiniment un nom que la personne n'utilise plus.
        stockage = Storage("sqlite+pysqlite:///:memory:")
        stockage.link_discord("joueur42", "9876", "Ancien")
        stockage.link_discord("joueur42", "9876", "Nouveau")
        assert stockage.display_name("joueur42") == "Nouveau"
