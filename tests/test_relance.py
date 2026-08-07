"""La relance après une mise à jour en un clic.

⚠️ **Signalé par Maxime le 07/08/2026 : « la mise a jour ferme l'app mais ne
le relance pas ».** Le CHANGELOG de la v0.5.9 annonçait pourtant ce défaut
corrigé, et la v0.6.4.0 a cru le corriger une seconde fois.

Deux tentatives, deux fois insuffisantes :

1. le 06/08, retirer le `self.close` de Rubin. Nécessaire, le Gestionnaire de
   redémarrage ne relançant que ce qu'il a lui-même fermé, mais pas suffisant ;
2. le 07/08 au matin, appeler `RegisterApplicationRestart`, que la
   documentation d'Inno Setup exige pour `RestartApplications`. L'appel
   réussissait, vérifié sur le binaire distribué, et **rien ne prouvait que le
   Gestionnaire de redémarrage relancerait pour autant**.

La troisième est la bonne, et elle vient de `butin-bdo` : **ne plus dépendre
du Gestionnaire de redémarrage pour rouvrir**. Il ferme, une ligne explicite
de la section `[Run]` rouvre. « Un mécanisme qu'on peut lire, tester et voir
échouer, au lieu d'un comportement du système qu'on espère. »

Butin a rencontré le même défaut le même jour et l'a tranché le premier. Ces
tests gardent l'alignement des deux logiciels, et surtout l'invariant qui
compte : **les deux mécanismes ne doivent jamais être actifs ensemble**, sinon
deux Rubin s'ouvrent, donc deux fils de capture sur la même session, donc la
même quête envoyée deux fois au serveur.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rubin import autoupdate

RECETTE = Path(__file__).resolve().parents[1] / "empaquetage" / "rubin.iss"


def recette() -> str:
    return RECETTE.read_text(encoding="utf-8")


def directives() -> str:
    """La recette privée de ses commentaires.

    Même précaution que `test_empaquetage.py`, et pour la même raison : un
    commentaire qui cite une directive ferait passer un test qui la cherche,
    alors qu'elle n'est plus posée. Ce piège a déjà mordu une fois aujourd'hui.
    """
    return "\n".join(
        ligne
        for ligne in recette().splitlines()
        if not ligne.lstrip().startswith((";", "{", "}"))
    )


class TestUnSeulMecanismeDeRelance:
    def test_le_gestionnaire_de_redemarrage_ne_relance_plus(self) -> None:
        """Régression : il valait `yes`, et la relance reposait entièrement sur
        lui. Constaté par Maxime, Rubin ne revenait pas."""
        assert "RestartApplications=no" in directives()

    def test_la_section_run_rouvre_explicitement(self) -> None:
        assert "Check: RelancementDemande" in directives()

    def test_les_deux_ne_sont_jamais_actifs_ensemble(self) -> None:
        """⚠️ L'invariant qui compte. Le Gestionnaire de redémarrage et la
        section `[Run]` rouvriraient chacun leur exemplaire, et deux Rubin en
        parallèle voudraient dire deux fils de capture sur la même session,
        donc la même quête envoyée deux fois au serveur.

        C'est le seul test de ce fichier dont l'échec produirait des données
        FAUSSES et pas seulement une gêne."""
        texte = directives()
        gestionnaire = "RestartApplications=yes" in texte
        section_run = "Check: RelancementDemande" in texte
        assert not (gestionnaire and section_run), (
            "les deux mécanismes de relance sont actifs : deux Rubin "
            "s'ouvriraient, donc deux fils de capture sur la même session"
        )

    def test_la_fermeture_reste_au_gestionnaire_de_redemarrage(self) -> None:
        """Il ferme toujours, lui : sans quoi l'installateur ne pourrait pas
        écrire par-dessus un exécutable en cours d'exécution."""
        assert "CloseApplications=force" in directives()

    def test_le_code_de_verification_du_commutateur_existe(self) -> None:
        """⚠️ Inno Setup n'a PAS de `CmdLineParamExists` : la session butin-bdo
        s'y est cassé les dents, ISCC refusant net « Unknown identifier ». Le
        parcours de `ParamStr` est l'idiome, et il faut l'écrire soi-même."""
        texte = recette()
        assert "function RelancementDemande" in texte
        assert "ParamStr" in texte
        # Cherché dans les DIRECTIVES et non dans le fichier entier : le
        # commentaire au-dessus cite ce nom exprès, pour mettre en garde.
        assert "CmdLineParamExists" not in directives()


class TestCommutateursDeLancement:
    def _arguments(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        vus: list[list[str]] = []
        monkeypatch.setattr(
            autoupdate.subprocess, "Popen", lambda args, **_k: vus.append(args) or None
        )
        autoupdate.launch_installer(Path("C:/faux/installateur.exe"))
        return vus[0]

    def test_demande_la_relance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert "/RELANCER" in self._arguments(monkeypatch)

    def test_ne_demande_plus_le_gestionnaire_de_redemarrage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression : `/RESTARTAPPLICATIONS` avec `RestartApplications=no`
        serait sans effet, mais laisserait croire en lisant le code que la
        relance est gérée là."""
        assert "/RESTARTAPPLICATIONS" not in self._arguments(monkeypatch)

    def test_reste_silencieux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Le « un clic » demandé par Maxime : aucune fenêtre d'installateur,
        # aucune invite.
        arguments = self._arguments(monkeypatch)
        assert "/VERYSILENT" in arguments
        assert "/SUPPRESSMSGBOXES" in arguments

    def test_ne_redemarre_jamais_lordinateur(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`/NORESTART` porte sur Windows, jamais sur Rubin."""
        assert "/NORESTART" in self._arguments(monkeypatch)
