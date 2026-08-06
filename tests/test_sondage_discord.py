"""Le sondage qui apprend à la fenêtre qu'un rattachement Discord a abouti.

Le rattachement se termine **hors du logiciel** : Rubin ouvre une page, le
joueur autorise, Discord le renvoie vers le serveur, et rien ne revient vers
la fenêtre. Sans ce sondage, elle reste sur « autorisez Rubin dans votre
navigateur, puis revenez ici » pour toujours, y compris quand tout a marché.
C'est ce qui est arrivé à Maxime le 06/08/2026, sur un compte pourtant
rattaché.

Une boucle qui se replanifie elle-même a deux façons de mal finir, et les
deux sont testées ici : ne jamais s'arrêter, ou s'arrêter trop tôt. La
première laisse une requête toutes les trois secondes pour l'éternité, sur
un geste que le joueur a peut-être abandonné ; la seconde ramène le défaut
d'origine.

Aucune fenêtre n'est ouverte, même idiome que
`test_interface_app_threading.py` : `root.after` est remplacé par une file
qu'on vide à la main, ce qui rend le temps observable au lieu d'attendre.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from rubin.discord import DiscordAccount
from rubin.interface.app import DISCORD_POLL_LIMIT_MS, DISCORD_POLL_MS, RubinApp


class _RacineFactice:
    """Un `tk.Tk` dont `after` empile au lieu d'attendre."""

    def __init__(self) -> None:
        self.planifies: list[tuple[int, Callable[[], None]]] = []

    def after(self, delai: int, rappel: Callable[[], None]) -> str:
        self.planifies.append((delai, rappel))
        return "id"

    def derouler(self, tours: int) -> None:
        """Fait passer le temps, `tours` fois, sans en attendre une seconde."""
        for _ in range(tours):
            if not self.planifies:
                return
            _delai, rappel = self.planifies.pop(0)
            rappel()


class _EtiquetteFactice:
    def __init__(self) -> None:
        self.textes: list[str] = []

    def config(self, text: str, foreground: str) -> None:
        self.textes.append(text)


class _Porteur:
    """Le strict nécessaire que les deux méthodes lisent et écrivent."""

    def __init__(self) -> None:
        self.root = _RacineFactice()
        self._stop = threading.Event()
        self._discord_attente = True
        self._discord_etat = _EtiquetteFactice()
        self.demandes = 0

    def _ask_discord_account(self) -> None:
        self.demandes += 1

    def _poll_discord_account(self, remaining_ms: int = DISCORD_POLL_LIMIT_MS) -> None:
        return RubinApp._poll_discord_account(self, remaining_ms)  # type: ignore[arg-type]

    def _show_discord_account(self, account: Any) -> None:
        return RubinApp._show_discord_account(self, account)  # type: ignore[arg-type]


class TestArretDuSondage:
    def test_sarrete_des_que_le_compte_est_rattache(self) -> None:
        """Le cas normal : le joueur autorise, la réponse suivante dit
        « rattaché », et plus rien n'est demandé. Sans cet arrêt, la fenêtre
        continuerait d'interroger le serveur toutes les trois secondes pendant
        trois minutes après avoir déjà obtenu sa réponse."""
        porteur = _Porteur()
        porteur._poll_discord_account()
        porteur.root.derouler(2)
        assert porteur.demandes == 3

        porteur._show_discord_account(DiscordAccount(linked=True, name="maxyull"))
        porteur.root.derouler(5)

        assert porteur.demandes == 3
        assert porteur._discord_attente is False

    def test_sarrete_au_dela_de_la_limite(self) -> None:
        """Régression : une boucle qui se replanifie elle-même sans borne
        interrogerait le serveur toutes les trois secondes pour toujours, sur
        un geste que le joueur a peut-être abandonné en fermant son onglet."""
        porteur = _Porteur()

        porteur._poll_discord_account(remaining_ms=DISCORD_POLL_MS)
        porteur.root.derouler(50)

        assert porteur._discord_attente is False
        assert porteur.demandes == 2
        assert porteur.root.planifies == []

    def test_la_fermeture_de_la_fenetre_arrete_le_sondage(self) -> None:
        """Un rappel planifié qui survit à la fermeture toucherait des
        composants détruits."""
        porteur = _Porteur()
        porteur._poll_discord_account()
        porteur._stop.set()

        porteur.root.derouler(5)

        assert porteur.demandes == 1

    def test_ne_demarre_pas_si_on_nattend_rien(self) -> None:
        # Au lancement, `_ask_discord_account` est appelée une fois, sans
        # sondage : personne n'a cliqué, il n'y a rien à attendre.
        porteur = _Porteur()
        porteur._discord_attente = False

        porteur._poll_discord_account()

        assert porteur.demandes == 0
        assert porteur.root.planifies == []


class TestEtiquetteDuCompte:
    def test_ecrit_le_pseudonyme_une_fois_rattache(self) -> None:
        porteur = _Porteur()

        porteur._show_discord_account(DiscordAccount(linked=True, name="maxyull"))

        assert porteur._discord_etat.textes == ["connecté comme maxyull"]

    def test_un_serveur_muet_nefface_pas_ce_qui_est_affiche(self) -> None:
        """Régression, le cœur du correctif : « on ne sait pas » ne doit pas
        s'écrire « pas encore connecté ». Une panne de réseau enverrait sinon
        un joueur déjà rattaché refaire un rattachement qui a marché."""
        porteur = _Porteur()

        porteur._show_discord_account(None)

        assert porteur._discord_etat.textes == []
        assert porteur._discord_attente is True

    def test_pendant_lattente_la_consigne_reste(self) -> None:
        """Régression : une seconde après le clic, le serveur répond
        honnêtement « pas rattaché », le joueur étant encore dans son
        navigateur. Écrire « pas encore connecté » à ce moment-là effacerait
        la seule phrase qui lui dit quoi faire."""
        porteur = _Porteur()

        porteur._show_discord_account(DiscordAccount(linked=False, name=None))

        assert porteur._discord_etat.textes == []

    def test_hors_attente_labsence_de_rattachement_se_dit(self) -> None:
        porteur = _Porteur()
        porteur._discord_attente = False

        porteur._show_discord_account(DiscordAccount(linked=False, name=None))

        assert porteur._discord_etat.textes == ["pas encore connecté"]
