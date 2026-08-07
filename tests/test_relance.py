"""La relance automatique après une mise à jour.

⚠️ **Signalé par Maxime le 07/08/2026 : « la mise à jour ferme l'app mais ne
le relance pas ».** Le CHANGELOG de la v0.5.9 annonçait pourtant ce défaut
corrigé.

Il ne l'était qu'à moitié. Le correctif du 06/08 avait retiré le `self.close`
de Rubin, ce qui était nécessaire : le Gestionnaire de redémarrage ne relance
que les applications **qu'il a lui-même fermées**, et un Rubin déjà éteint
n'est plus rien à relancer. Mais il manquait l'autre moitié, écrite noir sur
blanc dans la documentation d'Inno Setup à propos de `RestartApplications` :

    « for restart to work, the application needs to be using the Windows
      RegisterApplicationRestart API function »

Rubin ne l'appelait nulle part. Windows le fermait, et n'avait aucune commande
de relance à jouer ensuite.

**La leçon : la moitié visible d'un défaut peut se corriger sans que l'autre
moitié bouge**, et le CHANGELOG déclarait la chose réglée sur la foi de la
moitié corrigée.

Aucun de ces tests n'appelle la vraie fonction Windows : elle a été éprouvée à
part, en enregistrant puis en RELISANT ce que Windows avait retenu
(`GetApplicationRestartSettings` rend « introuvable » avant, `S_OK` avec la
ligne « fenetre » et les drapeaux 11 après).
"""

from __future__ import annotations

from typing import Any

import pytest

from rubin import autoupdate


class _NoyauFactice:
    """Le `kernel32` réduit à la fonction qu'on appelle."""

    def __init__(self, resultat: int = 0) -> None:
        self.appels: list[tuple[str, int]] = []
        self._resultat = resultat
        self.argtypes: Any = None
        self.restype: Any = None

    @property
    def RegisterApplicationRestart(self) -> _NoyauFactice:
        return self

    def __call__(self, ligne: str, drapeaux: int) -> int:
        self.appels.append((ligne, drapeaux))
        return self._resultat


@pytest.fixture
def noyau(monkeypatch: pytest.MonkeyPatch) -> _NoyauFactice:
    import ctypes

    faux = _NoyauFactice()
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": faux})())
    monkeypatch.setattr(autoupdate.sys, "frozen", True, raising=False)
    return faux


class TestEnregistrementPourRelance:
    def test_ne_fait_rien_hors_dun_executable_empaquete(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """En développement, `sys.executable` est `python.exe` : faire relancer
        l'interpréteur nu par Windows n'aurait aucun sens."""
        monkeypatch.delattr(autoupdate.sys, "frozen", raising=False)
        assert autoupdate.register_for_restart([]) is False

    def test_enregistre_la_fenetre_quand_il_ny_a_pas_darguments(
        self, noyau: _NoyauFactice
    ) -> None:
        """Régression : « fenetre » est écrit EXPLICITEMENT plutôt que laissé
        au défaut de l'analyseur d'arguments. Ce défaut a déjà été faux une
        fois, jusqu'à #78 : un exécutable lancé sans sous-commande ouvrait
        `referentiel`, donc un double-clic n'atteignait jamais la fenêtre.

        Une relance qui rouvrirait autre chose que la fenêtre serait pire que
        pas de relance : le joueur croirait Rubin reparti."""
        assert autoupdate.register_for_restart([]) is True
        assert noyau.appels[0][0] == "fenetre"

    def test_conserve_les_arguments_du_lancement(self, noyau: _NoyauFactice) -> None:
        # Un joueur lancé avec une option doit la retrouver après la mise à
        # jour, sinon Rubin repart autrement configuré sans le dire.
        autoupdate.register_for_restart(["fenetre", "--langue", "en"])
        assert noyau.appels[0][0] == "fenetre --langue en"

    def test_ne_remet_jamais_lexecutable_dans_la_ligne(self, noyau: _NoyauFactice) -> None:
        """⚠️ Windows préfixe lui-même le chemin de l'exécutable. L'y remettre
        ferait relancer `rubin.exe rubin.exe`, que l'analyseur prendrait pour
        une sous-commande inconnue."""
        autoupdate.register_for_restart(["fenetre"])
        assert ".exe" not in noyau.appels[0][0]

    def test_demande_la_relance_apres_une_mise_a_jour(self, noyau: _NoyauFactice) -> None:
        """C'est le seul cas qu'on veut, et il se dit EN CREUX : le drapeau
        `RESTART_NO_PATCH` (4) doit être absent."""
        autoupdate.register_for_restart([])
        _ligne, drapeaux = noyau.appels[0]
        assert drapeaux & 4 == 0, "RESTART_NO_PATCH est posé : aucune relance après mise à jour"

    def test_refuse_la_relance_apres_un_plantage(self, noyau: _NoyauFactice) -> None:
        """Une fenêtre qui revient toute seule après une panne cache la panne,
        et Rubin garde justement ses pannes dans `echecs/erreurs.log` pour
        qu'elles se voient. Un plantage en boucle relancerait en boucle."""
        autoupdate.register_for_restart([])
        _ligne, drapeaux = noyau.appels[0]
        assert drapeaux & 1, "RESTART_NO_CRASH manque"
        assert drapeaux & 2, "RESTART_NO_HANG manque"
        assert drapeaux & 8, "RESTART_NO_REBOOT manque"

    def test_un_refus_de_windows_est_rendu_sans_lever(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Une relance automatique est un confort : elle ne doit jamais
        empêcher Rubin de démarrer, puisque cet appel a lieu dans le
        constructeur de la fenêtre."""
        import ctypes

        faux = _NoyauFactice(resultat=-2147024809)
        monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": faux})())
        monkeypatch.setattr(autoupdate.sys, "frozen", True, raising=False)

        assert autoupdate.register_for_restart([]) is False
