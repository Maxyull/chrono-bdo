from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rubin.__main__ import DEFAULT_SERVER, _format_duration, _print_upcoming, build_parser, main
from rubin.failures import FailureStore
from rubin.reading import BannerKind
from rubin.reference import Catalog, QuestId
from rubin.references import ReferenceClient
from rubin.timing import Event, Timeline


class TestFormatDuration:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "0 s"),
            (42.5, "42 s"),
            (60, "1 min 00 s"),
            (95, "1 min 35 s"),
            (3600, "1 h 00 min"),
            (7325, "2 h 02 min"),
        ],
    )
    def test_ecrit_une_duree_lisible(self, seconds: float, expected: str) -> None:
        assert _format_duration(seconds) == expected


class TestParser:
    def test_connait_les_deux_commandes(self) -> None:
        parser = build_parser()
        assert parser.parse_args(["referentiel"]).handler is not None
        assert parser.parse_args(["suivre"]).handler is not None

    def test_suivre_prend_le_francais_par_defaut(self) -> None:
        assert build_parser().parse_args(["suivre"]).language == "fr"

    def test_suivre_accepte_l_anglais(self) -> None:
        # Un joueur francophone peut très bien jouer sur le client anglais :
        # la langue du jeu ne se déduit pas de celle de l'utilisateur.
        assert build_parser().parse_args(["suivre", "--langue", "en"]).language == "en"

    def test_suivre_accepte_une_echelle_d_interface(self) -> None:
        assert build_parser().parse_args(["suivre", "--echelle", "1.25"]).ui_scale == 1.25

    def test_refuse_une_langue_inconnue(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["suivre", "--langue", "de"])

    def test_suivre_montre_cinq_quetes_a_venir_par_defaut(self) -> None:
        assert build_parser().parse_args(["suivre"]).upcoming == 5

    def test_suivre_accepte_de_n_en_montrer_aucune(self) -> None:
        assert build_parser().parse_args(["suivre", "--suivantes", "0"]).upcoming == 0

    def test_connait_la_commande_fenetre(self) -> None:
        args = build_parser().parse_args(["fenetre"])
        assert args.handler is not None
        assert args.language == "fr"

    def test_la_fenetre_accepte_le_client_anglais(self) -> None:
        # La ligne de commande reste disponible sans interface graphique : elle
        # sert sur une machine qui n'en a pas, et elle permet de rendre compte
        # d'un défaut en collant du texte plutôt qu'une capture d'écran.
        assert build_parser().parse_args(["fenetre", "--langue", "en"]).language == "en"

    def test_echecs_vise_github_par_defaut(self) -> None:
        # La destination la plus contrainte, mais la seule où le fichier reste
        # attaché au rapport qui le décrit.
        args = build_parser().parse_args(["echecs"])
        assert args.destination == "github"
        assert args.archive is False

    def test_echecs_accepte_les_hebergeurs_plus_larges(self) -> None:
        args = build_parser().parse_args(["echecs", "--archiver", "--vers", "pixeldrain"])
        assert args.archive is True
        assert args.destination == "pixeldrain"

    def test_echecs_refuse_un_hebergeur_inconnu(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["echecs", "--vers", "wetransfer"])


class TestMain:
    def test_sans_jeu_lance_suivre_echoue_proprement(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Le cas le plus courant d'un premier lancement : le jeu n'est pas
        # ouvert. Il faut un message qui dise quoi faire, pas une trace.
        monkeypatch.setattr("rubin.__main__.find_game_window", lambda: None)
        assert main(["suivre"]) == 1
        assert "Black Desert" in capsys.readouterr().err

    def test_la_liste_a_venir_annonce_le_trou_et_les_carrefours(
        self, capsys: pytest.CaptureFixture[str], catalog: Catalog
    ) -> None:
        """Régression : la liste affichait une suite qu'on ne peut pas suivre.

        Deux défauts d'affichage, tous deux sur de vraies chaînes du jeu. Dans
        la 21130, la position 147 suit la 2 : l'afficher sans rien dire laisse
        croire qu'elles s'enchaînent. Dans la 21142, les deux quêtes connues
        sont des branches d'un choix : les lister l'une sous l'autre donne un
        programme que personne ne peut suivre.
        """
        timeline = Timeline(catalog=catalog, language="fr")
        references = ReferenceClient(None)

        # Chaîne à trou : après la 2 vient la 147.
        timeline.events.append(
            Event(at=0.0, kind=BannerKind.ACCEPTED, quest_name="", confidence=1.0,
                  quest_id=QuestId(21130, 2))
        )
        _print_upcoming(timeline, catalog, references, "fr", 5)
        sortie = capsys.readouterr().out
        assert "144 positions inconnues" in sortie
        assert "jamais mesurée" in sortie

        # Chaîne d'embranchements : les deux quêtes sont des branches.
        timeline.events.append(
            Event(at=0.0, kind=BannerKind.ACCEPTED, quest_name="", confidence=1.0,
                  quest_id=QuestId(21142, 0))
        )
        _print_upcoming(timeline, catalog, references, "fr", 5)
        sortie = capsys.readouterr().out
        assert "branches d'un choix" in sortie

    def test_la_liste_a_venir_se_tait_quand_on_ignore_ou_on_est(
        self, capsys: pytest.CaptureFixture[str], catalog: Catalog
    ) -> None:
        # Une liste tirée d'une position inconnue serait une liste au hasard,
        # ce qui est pire que pas de liste du tout.
        timeline = Timeline(catalog=catalog, language="fr")
        _print_upcoming(timeline, catalog, ReferenceClient(None), "fr", 5)
        assert capsys.readouterr().out == ""

    def test_echecs_sur_un_dossier_vide_ne_propose_rien_a_envoyer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        # Zéro échec est le cas normal d'une installation qui marche : il ne
        # doit ni inquiéter, ni proposer d'envoyer un fichier vide.
        monkeypatch.setattr("rubin.__main__._home", lambda: tmp_path)
        assert main(["echecs"]) == 0
        sortie = capsys.readouterr().out
        assert "aucune lecture ratée" in sortie
        assert "archive" not in sortie

    def test_echecs_archive_et_annonce_le_plafond_de_la_destination(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Régression : une archive fabriquée sans savoir où elle ira.

        La première version écrivait un zip et listait des destinations sans
        rapport avec sa taille. Or les plafonds vont de 25 Mo chez GitHub à
        20 Go chez pixeldrain : une archive trop lourde pour la destination
        visée n'est refusée qu'au moment du dépôt, une fois le fichier prêt et
        le joueur devant un message d'erreur qui ne vient pas de nous.

        Le plafond visé est donc annoncé avec l'archive, en kilo-octets.
        """
        monkeypatch.setattr("rubin.__main__._home", lambda: tmp_path)
        store = FailureStore(tmp_path / "echecs")
        with Image.open(Path(__file__).parent / "data" / "banner_present.png") as image:
            store.keep(np.asarray(image.convert("L"), dtype=np.uint8), [])

        assert main(["echecs", "--archiver", "--vers", "catbox"]) == 0

        sortie = capsys.readouterr().out
        assert "archive écrite" in sortie
        assert f"{204800} Ko" in sortie  # le plafond annoncé par catbox.moe
        assert list((tmp_path / "echecs").glob("*.zip"))


class TestCommandeParDefaut:
    """Ce qui se lance quand aucune sous-commande n'est donnée.

    C'est exactement ce qui arrive quand un joueur double-clique sur
    l'exécutable : `sys.argv` ne contient rien d'autre que son propre nom.
    """

    def test_sans_argument_le_parseur_ne_choisit_aucun_gestionnaire(self) -> None:
        # `handler` n'existe même pas sur l'espace de noms : il n'est posé que
        # par la sous-commande choisie, via `set_defaults`. C'est `main()` qui
        # décide quoi faire de cette absence, avec `getattr(..., None)`.
        assert getattr(build_parser().parse_args([]), "handler", None) is None

    def test_regression_le_defaut_etait_le_referentiel_en_ligne_de_commande(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression : un joueur qui double-clique ne voyait jamais la fenêtre.

        Avant ce correctif, `main()` sans sous-commande retombait sur
        `referentiel`, un reste de l'époque où seule la ligne de commande
        existait. La 0.5.0 a beau publier la fenêtre dans l'exécutable, un
        joueur qui double-cliquait sans avoir lu la moindre instruction
        n'atteignait jamais la fenêtre. Demandé par Maxime le 5 août 2026 au
        soir : « il faut pas que le joueur ait à envoyer des commandes ».
        """
        appels: list[object] = []
        monkeypatch.setattr(
            "rubin.__main__.command_interface",
            lambda args: appels.append(args) or 0,
        )

        résultat = main([])

        assert résultat == 0
        assert len(appels) == 1


class TestServeurParDefautDeLaFenetre:
    """`rubin fenetre` se connecte au serveur communautaire sans qu'on le demande.

    Décision de Maxime le 5 août 2026 au soir, juste après la publication de
    la 0.5.1 : « il faut pas que le joueur ait à envoyer des commandes ».
    """

    def test_fenetre_sans_argument_se_connecte_deja(self) -> None:
        assert build_parser().parse_args(["fenetre"]).server == DEFAULT_SERVER

    def test_envoyer_reste_utilisable_pour_viser_un_autre_serveur(self) -> None:
        # Le défaut change, pas la possibilité de le remplacer : un autre
        # serveur, de test par exemple, doit rester atteignable.
        args = build_parser().parse_args(["fenetre", "--envoyer", "http://localhost:9"])
        assert args.server == "http://localhost:9"

    def test_regression_suivre_garde_son_propre_defaut_sans_envoi(self) -> None:
        """Régression : `suivre` ne doit PAS hériter du serveur par défaut.

        Cette commande sert aussi à mesurer sans rien envoyer, sur une machine
        sans interface graphique : c'est le seul chemin qui permet encore de
        jouer sans se connecter à quoi que ce soit. Lui donner le même défaut
        que `fenetre` referait, en ligne de commande, exactement ce que ce
        changement corrige côté fenêtre : une décision prise à la place de
        qui ne l'a pas demandée.
        """
        assert build_parser().parse_args(["suivre"]).server is None
