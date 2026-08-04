from __future__ import annotations

import pytest

from chrono.__main__ import _format_duration, build_parser, main


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


class TestMain:
    def test_sans_jeu_lance_suivre_echoue_proprement(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Le cas le plus courant d'un premier lancement : le jeu n'est pas
        # ouvert. Il faut un message qui dise quoi faire, pas une trace.
        monkeypatch.setattr("chrono.__main__.find_game_window", lambda: None)
        assert main(["suivre"]) == 1
        assert "Black Desert" in capsys.readouterr().err
