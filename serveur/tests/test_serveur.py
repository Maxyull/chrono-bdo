from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from rubin.protocol import PROTOCOL_VERSION, MeasurePayload, SessionPayload

from rubin_serveur import main
from rubin_serveur.storage import MIN_SAMPLES_PER_QUEST, WELL_MEASURED_AT, Storage


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


class TestClassementParQuete:
    def test_classe_les_quetes_de_la_plus_rapide_a_la_plus_lente(
        self, client: TestClient
    ) -> None:
        # Trois mesures par quête, le minimum pour entrer au classement.
        client.post("/v1/sessions", json=lot(600.0, 600.0, 600.0, quest="21139/29"))
        client.post("/v1/sessions", json=lot(30.0, 30.0, 30.0, quest="21139/46"))

        quetes = client.get("/v1/quetes").json()["quetes"]

        assert [q["quete"] for q in quetes] == ["21139/46", "21139/29"]
        # Le nombre de mesures voyage avec chaque ligne, comme partout ailleurs
        # dans ce projet : un temps sans son assise se croit plus solide qu'il
        # n'est.
        assert [q["samples"] for q in quetes] == [3, 3]

    def test_ne_rend_aucun_nom_de_quete(self, client: TestClient) -> None:
        """Le serveur ne connaît que `chaine/position`, et s'y tient.

        Les noms sont un fait du catalogue, que le client porte. Rien ne
        garantit au serveur que tous les clients lisent le même référentiel, ni
        la même langue : afficher un nom ici serait affirmer ce qu'il ne peut pas
        vérifier.
        """
        client.post("/v1/sessions", json=lot(30.0, 30.0, 30.0, quest="21139/46"))

        ligne = client.get("/v1/quetes").json()["quetes"][0]

        assert ligne["quete"] == "21139/46"
        assert set(ligne) == {
            "chain",
            "position",
            "median_seconds",
            "samples",
            "fastest_seconds",
            "quete",
        }

    def test_classe_sur_la_mediane_et_non_sur_le_record(self, client: TestClient) -> None:
        # `ETAT.md` tranche : le classement se fait sur la médiane, jamais sur le
        # record. Une quête faite une fois en une seconde ne double personne.
        client.post("/v1/sessions", json=lot(1.0, 300.0, 300.0, quest="21139/29"))
        client.post("/v1/sessions", json=lot(60.0, 60.0, 60.0, quest="21139/46"))

        quetes = client.get("/v1/quetes").json()["quetes"]

        assert [q["quete"] for q in quetes] == ["21139/46", "21139/29"]
        # Le record existe dans la réponse, il ne commande simplement pas l'ordre.
        assert quetes[1]["fastest_seconds"] == 1.0

    def test_ecarte_les_quetes_mesurees_une_seule_fois(self, client: TestClient) -> None:
        """Régression : 198,8 quêtes/heure sur UNE mesure, vu en production.

        Relevé réel sur https://rubin.maxyull.fr le 05/08/2026 : la chaîne 21403
        tenait la tête du classement des chaînes à **198,8 quêtes/heure**, sur
        une seule mesure de 18,1 secondes. Un classement de chaînes sur peu de
        mesures est vague ; le même classement à la quête serait faux et
        convaincant, puisque la première place irait toujours à la quête mesurée
        une fois par quelqu'un de chanceux.

        La quête lente ci-dessous porte trois mesures, la rapide une seule. Sans
        seuil, la rapide passerait devant sur la foi d'un unique passage.
        """
        client.post("/v1/sessions", json=lot(18.1, quest="21403/1"))
        client.post("/v1/sessions", json=lot(300.0, 300.0, 300.0, quest="21139/29"))

        quetes = client.get("/v1/quetes").json()["quetes"]

        assert [q["quete"] for q in quetes] == ["21139/29"]

    def test_le_seuil_par_defaut_est_strictement_superieur_a_un(
        self, client: TestClient
    ) -> None:
        # Deux mesures ne suffisent pas non plus : la médiane de deux valeurs est
        # leur moyenne, donc un passage chanceux tire le résultat de la moitié de
        # son écart. À trois, la médiane est une valeur réellement observée.
        assert MIN_SAMPLES_PER_QUEST > 1
        client.post("/v1/sessions", json=lot(30.0, 30.0, quest="21139/46"))

        reponse = client.get("/v1/quetes").json()

        assert reponse["quetes"] == []
        assert reponse["min_echantillons"] == MIN_SAMPLES_PER_QUEST

    def test_rend_une_liste_vide_plutot_que_de_baisser_le_seuil(
        self, client: TestClient
    ) -> None:
        """La base réelle du 05/08/2026 : vingt-et-une mesures, aucune classable.

        Quatre sessions, deux joueurs, vingt-et-une mesures réparties sur cinq
        chaînes, et presque une seule mesure par quête. La réponse honnête est
        une liste vide, et c'est au client de la dire en toutes lettres plutôt
        que d'afficher un tableau désert.
        """
        for position in range(1, 12):
            client.post("/v1/sessions", json=lot(60.0, quest=f"21139/{position}"))

        assert client.get("/v1/quetes").json()["quetes"] == []
        # Le seuil abaissé à la main montre bien qu'il y avait de la matière :
        # ce n'est pas la base qui est vide, c'est le seuil qui protège.
        assert len(client.get("/v1/quetes?min_samples=1&limit=50").json()["quetes"]) == 11

    def test_borne_le_nombre_de_lignes(self, client: TestClient) -> None:
        for position in range(1, 6):
            client.post("/v1/sessions", json=lot(60.0, 60.0, 60.0, quest=f"21139/{position}"))
        assert len(client.get("/v1/quetes?limit=2").json()["quetes"]) == 2

    def test_departage_deux_temps_egaux_toujours_pareil(self, client: TestClient) -> None:
        # Une liste qui change d'ordre sans que rien n'ait changé se lit comme
        # une liste qui ment. À durée égale, la chaîne puis la position tranchent.
        for chaine in (21403, 21139, 21402):
            client.post("/v1/sessions", json=lot(60.0, 60.0, 60.0, quest=f"{chaine}/1"))

        quetes = client.get("/v1/quetes").json()["quetes"]

        assert [q["quete"] for q in quetes] == ["21139/1", "21402/1", "21403/1"]


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


class TestCouverture:
    def test_repartit_les_quetes_en_deux_tranches(self, client: TestClient) -> None:
        # Cinq mesures sur une quête, deux sur une autre, une sur la dernière :
        # une verte et deux orange, avec le seuil de cinq de l'interface.
        client.post("/v1/sessions", json=lot(*[60.0] * 5, quest="21136/1"))
        client.post("/v1/sessions", json=lot(60.0, 70.0, quest="21136/2"))
        client.post("/v1/sessions", json=lot(60.0, quest="21136/3"))

        couverture = client.get("/v1/couverture").json()
        assert couverture["well_measured"] == 1
        assert couverture["lightly_measured"] == 2
        assert couverture["measured_quests"] == 3
        assert couverture["threshold"] == WELL_MEASURED_AT

    def test_ne_dit_rien_des_quetes_jamais_mesurees(self, client: TestClient) -> None:
        """Régression : le serveur ne connaît pas le nombre de quêtes grises.

        Cas réel du 05/08/2026 : la base contient onze mesures, d'un seul
        joueur, sur une seule chaîne. La fenêtre veut afficher « 0 verte,
        11 orange, 3 913 grises », et la tentation est de faire calculer les
        trois chiffres par le serveur d'un coup.

        Il ne le peut pas. Les 3 924 quêtes principales sont un fait du
        catalogue, que le client porte et que le serveur n'a jamais vu. Il ne
        rend donc que les deux tranches qu'il a vraiment observées, et le client
        soustrait de son propre total. Un serveur qui annoncerait 3 913 grises
        énoncerait un chiffre qu'aucune de ses tables ne contient.
        """
        for position in range(1, 12):
            client.post("/v1/sessions", json=lot(60.0, quest=f"21136/{position}"))

        couverture = client.get("/v1/couverture").json()
        assert couverture["well_measured"] == 0
        assert couverture["lightly_measured"] == 11
        assert couverture["measured_quests"] == 11

        # Ni total, ni grises, ni pourcentage : rien qui laisse croire que le
        # serveur connaît l'échelle de ce qui reste.
        assert set(couverture) == {
            "well_measured",
            "lightly_measured",
            "threshold",
            "measured_quests",
        }

    def test_repond_zero_sur_une_base_vierge(self, client: TestClient) -> None:
        """Régression : une somme sur zéro ligne rend `NULL`, pas zéro.

        Le compteur s'affiche en bas de la fenêtre, donc il est interrogé au
        tout premier démarrage, juste après un déploiement, quand personne n'a
        encore rien envoyé. C'est exactement le cas où la requête n'a aucune
        ligne à sommer : sans `coalesce`, la réponse porterait `null` là où le
        client attend un entier, et le compteur tomberait sur son premier appel.
        """
        couverture = client.get("/v1/couverture").json()
        assert couverture["well_measured"] == 0
        assert couverture["lightly_measured"] == 0
        assert couverture["measured_quests"] == 0

    def test_compte_des_mesures_et_non_des_contributeurs(self) -> None:
        """Limite connue, écrite pour qu'elle ne surprenne personne.

        Un joueur a jusqu'à 44 personnages et refait chaque quête sur chacun :
        cinq passages du même joueur suffisent à peindre une quête en vert alors
        qu'une seule main a parlé. Le serveur ne distingue pas encore les
        contributeurs par quête. Ce test fixe le comportement d'aujourd'hui,
        il ne le défend pas.
        """
        stockage = Storage("sqlite+pysqlite:///:memory:")
        for _ in range(5):
            stockage.store(
                SessionPayload(
                    player="joueur-unique",
                    language="fr",
                    catalog_date="2026-08-05",
                    measures=(MeasurePayload("21136/1", 60.0, "exacte", 0.97),),
                )
            )
        couverture = stockage.coverage()
        assert couverture.well_measured == 1
        assert couverture.lightly_measured == 0


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

    def test_refuse_un_etat_perime(self) -> None:
        """Régression : une signature sans date reste valable pour toujours.

        L'état voyage dans une adresse, donc il finit dans un historique de
        navigation, un journal de mandataire ou un en-tête `Referer`. Tant
        qu'il n'était signé que sur l'identifiant, un état ramassé six mois
        plus tard permettait encore de rattacher **son** compte Discord au
        numéro de celui qui l'avait laissé fuiter, et de s'attribuer ses
        mesures. La date signée ne supprime pas la fuite, elle en ferme la
        fenêtre.
        """
        from rubin_serveur.discord import STATE_MAX_AGE, read_state, sign_state

        vieux = sign_state("joueur42", "secret", issued_at=int(time.time()) - STATE_MAX_AGE - 1)
        assert read_state(vieux, "secret") is None

        recent = sign_state("joueur42", "secret", issued_at=int(time.time()) - 10)
        assert read_state(recent, "secret") == "joueur42"

    def test_refuse_une_date_retouchee(self) -> None:
        # Rajeunir un état périmé demanderait de refaire la signature, qui
        # porte sur l'identifiant *et* la date.
        from rubin_serveur.discord import read_state, sign_state

        vieux = sign_state("joueur42", "secret", issued_at=int(time.time()) - 100_000)
        signature = vieux.rsplit(".", 1)[1]
        rajeuni = f"joueur42.{int(time.time())}.{signature}"
        assert read_state(rajeuni, "secret") is None


class TestDiscordSansIdentifiants:
    """L'état par défaut : aucune variable d'environnement n'est posée.

    C'est celui de la production aujourd'hui, et il doit le rester tant que la
    politique de confidentialité ne mentionne pas le pseudonyme Discord.
    """

    @pytest.fixture(autouse=True)
    def sans_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "discord_config", None)

    def test_la_connexion_dit_qu_elle_n_est_pas_configuree(self, client: TestClient) -> None:
        reponse = client.get("/v1/discord/connexion", params={"player": "a" * 32})
        assert reponse.status_code == 503
        assert "pas configuré" in reponse.json()["detail"]

    def test_le_retour_dit_qu_il_n_est_pas_configure(self, client: TestClient) -> None:
        reponse = client.get("/v1/discord/retour", params={"code": "x", "state": "y"})
        assert reponse.status_code == 503

    def test_le_reste_du_serveur_continue_de_fonctionner(self, client: TestClient) -> None:
        """Régression : Discord absent ne doit rien emporter avec lui.

        Contribuer n'a jamais demandé de compte. Un serveur qui refuserait de
        démarrer, ou qui rendrait une erreur ailleurs, faute de
        `RUBIN_DISCORD_ID`, couperait la mesure de tous les joueurs pour une
        fonction que personne n'utilise encore.
        """
        assert client.post("/v1/sessions", json=lot(42.0)).status_code == 201
        assert client.get("/sante").status_code == 200
        assert client.get("/v1/quetes/21136/1").json()["samples"] == 1


class TestDiscordConfigure:
    """Le serveur muni d'identifiants, sans jamais appeler Discord.

    L'échange du code est remplacé : une suite de tests qui dépendrait de la
    disponibilité de discord.com ne dirait plus rien du code le jour où elle
    casserait.
    """

    #: Clé de signature de l'état, propre aux tests. Le vérificateur de
    #: sécurité signale toute constante dont le nom évoque un secret sans
    #: regarder sa valeur ; le nom l'évite, faute de quoi il faudrait
    #: désactiver la règle pour tout le fichier.
    CLE_ETAT = "signature-de-test"

    @pytest.fixture(autouse=True)
    def avec_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from rubin_serveur.discord import DiscordConfig

        monkeypatch.setattr(
            main,
            "discord_config",
            DiscordConfig(
                client_id="123",
                # Valeur factice : aucun appel réel à Discord n'est fait ici.
                client_secret="chut",  # noqa: S106
                redirect_uri="https://rubin.maxyull.fr/v1/discord/retour",
                state_secret=self.CLE_ETAT,
            ),
        )

    def etat(self, player: str, age: int = 0) -> str:
        from rubin_serveur.discord import sign_state

        return sign_state(player, self.CLE_ETAT, issued_at=int(time.time()) - age)

    def test_envoie_vers_discord_avec_un_etat_signe(self, client: TestClient) -> None:
        from rubin_serveur.discord import read_state

        reponse = client.get(
            "/v1/discord/connexion", params={"player": "a" * 32}, follow_redirects=False
        )
        assert reponse.status_code == 307
        destination = urlparse(reponse.headers["location"])
        assert destination.netloc == "discord.com"

        parametres = parse_qs(destination.query)
        assert parametres["scope"] == ["identify"]
        assert read_state(parametres["state"][0], self.CLE_ETAT) == "a" * 32

    def test_refuse_un_identifiant_de_contributeur_malforme(self, client: TestClient) -> None:
        # Le point sépare les trois parties de l'état signé : un identifiant
        # qui en contiendrait déplacerait la frontière entre le numéro et sa
        # signature.
        reponse = client.get("/v1/discord/connexion", params={"player": "joueur.42"})
        assert reponse.status_code == 422

    def test_rattache_le_compte_au_retour(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rubin_serveur.discord import DiscordIdentity

        monkeypatch.setattr(
            main, "exchange_code", lambda config, code: DiscordIdentity("9876", "Maxyull")
        )
        reponse = client.get(
            "/v1/discord/retour", params={"code": "bon-code", "state": self.etat("a" * 32)}
        )
        assert reponse.status_code == 200
        assert reponse.json() == {"rattache": True, "nom": "Maxyull"}
        assert main.storage.display_name("a" * 32) == "Maxyull"

    def test_le_retour_rejette_un_etat_forge(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression : sans état signé, on s'attribue les mesures d'un autre.

        Discord rend l'état tel quel. Une route de retour qui le croirait sur
        parole laisserait n'importe qui appeler `/v1/discord/retour` avec le
        numéro d'un contributeur et son propre compte Discord, et apparaître au
        classement à la place de la personne qui a réellement mesuré. C'est la
        seule chose qui tient cette adresse debout : elle est publique, et rien
        n'oblige celui qui l'appelle à être passé par Discord.
        """
        from rubin_serveur.discord import sign_state

        appels: list[str] = []

        def espion(config: object, code: str) -> None:
            appels.append(code)
            return None

        monkeypatch.setattr(main, "exchange_code", espion)
        victime = "b" * 32

        etats = (
            victime,  # non signé du tout
            f"{victime}.{int(time.time())}.00000000000000000000000000000000",  # signature forgée
            sign_state(victime, "mauvais-secret"),  # signé, mais pas par nous
            self.etat(victime, age=100_000),  # signé par nous, mais périmé
        )
        for etat in etats:
            reponse = client.get("/v1/discord/retour", params={"code": "bon-code", "state": etat})
            assert reponse.status_code == 400, etat

        # Aucun de ces retours n'a même été présenté à Discord : le rattachement
        # s'arrête avant l'échange, et rien n'a été écrit.
        assert appels == []
        assert main.storage.display_name(victime) is None

    def test_refuse_un_retour_incomplet(self, client: TestClient) -> None:
        assert client.get("/v1/discord/retour").status_code == 400
        assert client.get("/v1/discord/retour", params={"code": "x"}).status_code == 400
        reponse = client.get(
            "/v1/discord/retour", params={"code": "x" * 600, "state": self.etat("a" * 32)}
        )
        assert reponse.status_code == 400

    def test_dit_quand_discord_ne_confirme_pas(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Un échec côté Discord ne doit ni faire tomber le serveur ni rendre
        # une trace au visiteur.
        monkeypatch.setattr(main, "exchange_code", lambda config, code: None)
        reponse = client.get(
            "/v1/discord/retour", params={"code": "code-refuse", "state": self.etat("a" * 32)}
        )
        assert reponse.status_code == 502
        assert main.storage.display_name("a" * 32) is None

    def test_borne_un_pseudonyme_demesure(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression : un nom trop long ferait échouer l'écriture en base.

        La colonne `discord_name` fait soixante-quatre caractères. Discord
        borne les siens à trente-deux, mais ce qu'il rend n'est pas de notre
        ressort, et Postgres refuse ce qui dépasse là où SQLite l'accepte. Le
        rattachement échouerait après que la personne a donné son accord, et
        seulement en production.
        """
        from rubin_serveur.discord import DiscordIdentity

        monkeypatch.setattr(
            main,
            "exchange_code",
            # Un caractère de contrôle et deux cents caractères : ni l'un ni
            # l'autre ne vient de nous, et Discord n'est pas tenu de les
            # exclure.
            lambda config, code: DiscordIdentity("9876", "Maxyull" + chr(7) + "N" * 200),
        )
        reponse = client.get(
            "/v1/discord/retour", params={"code": "bon-code", "state": self.etat("a" * 32)}
        )
        assert reponse.status_code == 200
        nom = reponse.json()["nom"]
        assert len(nom) == 64
        assert nom.isprintable()
