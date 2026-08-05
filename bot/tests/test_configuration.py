from __future__ import annotations

from rubin_bot.api import DEFAULT_BASE_URL, DEFAULT_TIMEOUT
from rubin_bot.configuration import (
    MISSING_TOKEN,
    SERVER_VARIABLE,
    TIMEOUT_VARIABLE,
    TOKEN_VARIABLE,
    Configuration,
)


class TestJeton:
    def test_sans_jeton_le_robot_n_est_pas_pret(self) -> None:
        configuration = Configuration.from_env({})
        assert configuration.token is None
        assert not configuration.ready

    def test_un_jeton_vide_vaut_un_jeton_absent(self) -> None:
        """Régression : une variable posée mais vide ne doit pas passer pour configurée.

        Une ligne `RUBIN_BOT_JETON=` dans un fichier d'environnement systemd
        est le résultat courant d'un déploiement fait avant que le jeton
        n'existe. Traitée comme un jeton, elle ferait tenter une connexion que
        Discord refuse en 401, et le journal parlerait d'authentification là
        où il n'y a qu'une variable oubliée.
        """
        for brut in ("", "   ", "\n"):
            configuration = Configuration.from_env({TOKEN_VARIABLE: brut})
            assert not configuration.ready

    def test_le_message_d_absence_dit_quoi_faire(self) -> None:
        assert TOKEN_VARIABLE in MISSING_TOKEN
        assert "discord.com/developers" in MISSING_TOKEN
        assert "secrets" in MISSING_TOKEN

    def test_le_jeton_n_apparait_pas_dans_le_message(self) -> None:
        """Régression : rien de ce qu'on affiche ne doit pouvoir contenir un jeton.

        Le message d'absence part sur la sortie standard, donc dans le journal
        systemd, qui n'est pas un endroit pour un secret. Il est constant, sans
        interpolation possible, et ce test le fige.
        """
        assert "{" not in MISSING_TOKEN.replace("{}", "")
        assert "jeton-secret" not in MISSING_TOKEN

    def test_lit_le_jeton_pose_dans_l_environnement(self) -> None:
        configuration = Configuration.from_env({TOKEN_VARIABLE: " valeur-factice "})
        assert configuration.token == "valeur-factice"
        assert configuration.ready


class TestServeur:
    def test_le_defaut_est_le_serveur_public(self) -> None:
        assert Configuration.from_env({}).base_url == DEFAULT_BASE_URL

    def test_accepte_une_instance_de_developpement(self) -> None:
        configuration = Configuration.from_env({SERVER_VARIABLE: "http://127.0.0.1:8000/"})
        assert configuration.base_url == "http://127.0.0.1:8000"

    def test_ecarte_un_schema_exotique(self) -> None:
        """Régression : le robot n'a aucune raison de lire un fichier local.

        Une adresse mal saisie doit retomber sur le serveur public plutôt que
        d'échouer à chaque commande, et un `file://` posé par erreur ou par
        malice ne doit pas devenir une lecture de disque.
        """
        for brut in ("file:///etc/passwd", "ftp://ailleurs", "n'importe quoi", "https://"):
            assert Configuration.from_env({SERVER_VARIABLE: brut}).base_url == DEFAULT_BASE_URL


class TestDelai:
    def test_le_defaut_est_pose(self) -> None:
        assert Configuration.from_env({}).timeout == DEFAULT_TIMEOUT

    def test_accepte_un_delai_plausible(self) -> None:
        assert Configuration.from_env({TIMEOUT_VARIABLE: "2.5"}).timeout == 2.5

    def test_ecarte_un_delai_absurde(self) -> None:
        # Zéro couperait tous les appels, et une heure n'est plus un délai.
        for brut in ("0", "-1", "3600", "beaucoup"):
            assert Configuration.from_env({TIMEOUT_VARIABLE: brut}).timeout == DEFAULT_TIMEOUT
