from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rubin.__main__ import _format_duration, build_parser, main
from rubin.failures import FailureStore


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
