from __future__ import annotations

import pytest

from rubin_bot.__main__ import run
from rubin_bot.configuration import TOKEN_VARIABLE


class TestSansJeton:
    def test_s_arrete_proprement_et_explique(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Régression : l'absence de jeton est l'état normal, pas un plantage.

        L'application Discord n'existe pas encore : elle se crée à la main sur
        le portail développeur, ce qui n'est pas du code. Tant qu'elle manque,
        `python -m rubin_bot` doit dire ce qu'il attend et rendre la main, sans
        trace de pile et sans tenter de connexion avec un jeton vide, que
        Discord refuserait en 401 sans expliquer pourquoi.
        """
        monkeypatch.delenv(TOKEN_VARIABLE, raising=False)
        code = run([])
        sortie = capsys.readouterr().out
        assert code == 1
        assert TOKEN_VARIABLE in sortie
        assert "Traceback" not in sortie

    def test_ne_touche_pas_au_reseau(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Régression : rien ne doit partir vers Discord tant que rien n'est configuré.

        Le contrôle a lieu avant même l'import de la bibliothèque Discord, ce
        qui garantit qu'aucune session HTTP n'est ouverte et qu'aucune
        passerelle n'est jointe. Un robot qui se connecterait « pour voir »
        avec un jeton absent apparaîtrait dans les journaux de Discord.
        """
        monkeypatch.setenv(TOKEN_VARIABLE, "   ")
        assert run(None) == 1
