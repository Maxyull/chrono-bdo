"""Télécharge et installe une mise à jour, en un clic.

`updates.py` a longtemps refusé ce module, et pour une raison qui tenait :
« rien n'est remplacé automatiquement » parce qu'un `.exe` Windows ne peut pas
se réécrire pendant qu'il tourne. C'est toujours vrai, et ce module ne le
contredit pas : il ne remplace rien lui-même. Il télécharge un **second**
programme, l'installateur Inno Setup produit par `empaquetage/rubin.iss`, et
le lance. C'est l'installateur qui sait fermer Rubin proprement (Gestionnaire
de redémarrage de Windows, `CloseApplications=force` dans le `.iss`) et le
relancer une fois les fichiers remplacés.

Demandé par Maxime le 06/08/2026 : un clic doit suffire, sans réinstaller les
droits administrateur à chaque fois. L'installateur s'installe donc par
utilisateur (`PrivilegesRequired=lowest`), jamais dans Program Files, ce qui
est la seule façon d'éviter une invite Windows à chaque mise à jour.

## Pourquoi vérifier l'empreinte avant de lancer quoi que ce soit

`requests` valide déjà le certificat TLS de GitHub, donc le fichier reçu vient
bien de là. Mais un fichier arrivé intact n'est pas forcément le bon fichier :
une construction interrompue, un octet perdu en chemin, ou une release mal
publiée produiraient un binaire corrompu qu'on s'apprêterait à exécuter avec
les mêmes droits que Rubin. L'empreinte, publiée à côté de l'installateur par
`construire.py`, est la même vérification que celle déjà proposée à la main
dans le README pour l'archive zip.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import requests

_log = logging.getLogger(__name__)

_TIMEOUT: Final = 60
_USER_AGENT: Final = "rubin-bdo"

#: Le dépôt qui porte les releases. Les noms de fichiers sont les nôtres,
#: fixés par `empaquetage/construire.py` : l'URL se construit donc sans
#: requête supplémentaire à l'API GitHub, qui a ses propres limites de débit.
REPO: Final = "Maxyull/rubin-bdo"


def installer_url(version: str) -> str:
    """L'adresse de l'installateur d'une version donnée, sur GitHub Releases."""
    return f"https://github.com/{REPO}/releases/download/v{version}/rubin-installateur-{version}.exe"


def download_installer(version: str, destination: Path, timeout: int = _TIMEOUT) -> bool:
    """Télécharge l'installateur et vérifie son empreinte avant de l'écrire.

    Rend `False` sur tout échec (réseau, empreinte qui ne correspond pas),
    ne lève jamais : un téléchargement raté doit rester une ligne d'état,
    jamais une trace qui inquiète pour rien. Rien n'est écrit sur le disque
    tant que l'empreinte n'a pas été vérifiée en mémoire.
    """
    url = installer_url(version)
    en_têtes = {"User-Agent": _USER_AGENT}
    try:
        réponse = requests.get(url, headers=en_têtes, timeout=timeout)
        réponse.raise_for_status()
        empreinte_réponse = requests.get(f"{url}.sha256", headers=en_têtes, timeout=timeout)
        empreinte_réponse.raise_for_status()
    except requests.RequestException:
        return False

    contenu = réponse.content
    # Le fichier .sha256 suit le format `sha256sum` : l'empreinte, deux
    # espaces, le nom du fichier. Seul le premier mot compte ici.
    attendue = empreinte_réponse.text.split()[0].strip().lower() if empreinte_réponse.text else ""
    réelle = hashlib.sha256(contenu).hexdigest()
    if not attendue or réelle != attendue:
        return False

    destination.write_bytes(contenu)
    return True


#: Les cas où Windows NE doit PAS relancer Rubin tout seul, combinés.
#:
#: `RESTART_NO_CRASH` (1), `RESTART_NO_HANG` (2), `RESTART_NO_REBOOT` (8).
#: Reste, en creux, le seul cas qu'on veut : `RESTART_NO_PATCH` **n'y est
#: pas**, donc Windows relance Rubin après une mise à jour, et seulement
#: après.
#:
#: ⚠️ Relancer après un plantage serait le contraire de ce que ce projet
#: fait : une fenêtre qui revient toute seule après une panne cache la panne,
#: et Rubin garde justement ses pannes dans `echecs/erreurs.log` pour qu'elles
#: se voient. Un plantage en boucle relancerait Rubin en boucle.
_NE_PAS_RELANCER_SI: Final = 1 | 2 | 8

#: Windows plafonne la ligne de commande enregistrée à 1024 caractères
#: (`RESTART_MAX_CMD_LINE`). Au-delà, l'appel échoue, et il échouerait en
#: silence si personne ne regardait le code de retour.
_MAX_LIGNE_COMMANDE: Final = 1024


def register_for_restart(arguments: Sequence[str] | None = None) -> bool:
    """Demande à Windows de relancer Rubin après une mise à jour.

    ⚠️ **C'est la pièce qui manquait, et rien ne le disait.** La documentation
    d'Inno Setup est explicite sur `RestartApplications` : « for restart to
    work, the application needs to be using the Windows
    `RegisterApplicationRestart` API function ». Rubin ne l'appelait nulle
    part.

    Le Gestionnaire de redémarrage fermait donc bien Rubin, puisqu'il tient
    des fichiers que l'installateur remplace, mais n'avait **aucune commande
    de relance** à jouer ensuite. Signalé par Maxime le 07/08/2026 : « la mise
    à jour ferme l'app mais ne le relance pas ».

    Le correctif du 06/08 (retirer le `self.close` de Rubin, voir
    `_show_update_launched`) était nécessaire et **pas suffisant** : il a rendu
    la fermeture propre, jamais la relance. Le CHANGELOG de la v0.5.9
    l'annonçait pourtant corrigé, ce qui est une leçon en soi : la moitié
    visible d'un défaut peut se corriger sans que l'autre moitié bouge.

    ⚠️ **La ligne de commande enregistrée ne porte PAS l'exécutable**, Windows
    le préfixe lui-même. Y remettre le chemin ferait relancer
    `rubin.exe rubin.exe`, que l'analyseur d'arguments prendrait pour une
    sous-commande inconnue.

    Ne fait rien hors d'un exécutable empaqueté : en développement,
    `sys.executable` est `python.exe`, et faire relancer l'interpréteur nu par
    Windows n'aurait aucun sens. Rend `True` si l'enregistrement a réussi.
    """
    if not getattr(sys, "frozen", False):
        return False
    # ⚠️ « fenetre » explicitement quand il n'y a pas d'argument, plutôt que
    # de compter sur le défaut de l'analyseur. Ce défaut a déjà été faux une
    # fois : jusqu'à #78, un exécutable lancé sans sous-commande ouvrait
    # `referentiel`, donc un double-clic n'atteignait jamais la fenêtre. Une
    # relance qui rouvrirait autre chose que la fenêtre serait pire que pas
    # de relance du tout, le joueur croyant Rubin reparti.
    ligne = " ".join(arguments if arguments is not None else sys.argv[1:]) or "fenetre"
    if len(ligne) > _MAX_LIGNE_COMMANDE:  # pragma: pas de couverture
        # Rubin n'a que des arguments courts ; le dire plutôt que de laisser
        # l'appel échouer sans trace serait déjà mieux que rien.
        _log.warning("ligne de commande trop longue pour la relance automatique")
        return False
    try:
        import ctypes
        from ctypes import wintypes

        fonction = ctypes.windll.kernel32.RegisterApplicationRestart
        # ⚠️ Les signatures sont déclarées, pas laissées au hasard. Sans
        # `argtypes`, ctypes devine, et il devine mal : en vérifiant ce
        # correctif, une poignée de processus passée sans type a été tronquée
        # sur 32 bits et Windows a rendu `E_HANDLE`, ce qui se lisait
        # « rien n'est enregistré » alors que tout l'était.
        fonction.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        fonction.restype = ctypes.c_long
        resultat = fonction(ligne, _NE_PAS_RELANCER_SI)
    except (AttributeError, OSError) as erreur:  # pragma: pas de couverture
        # Pas Windows, ou une version qui ne connaît pas cette fonction. Une
        # relance automatique est un confort : elle ne doit jamais empêcher
        # Rubin de démarrer.
        _log.warning("relance automatique indisponible : %s", erreur)
        return False
    if resultat != 0:  # pragma: pas de couverture
        _log.warning("Windows a refusé l'enregistrement pour relance : %s", resultat)
        return False
    return True


def launch_installer(installer: Path) -> None:
    """Lance l'installateur en silence, et laisse Windows fermer Rubin.

    `/RESTARTAPPLICATIONS` s'appuie sur `CloseApplications=force` posé dans
    `rubin.iss` : c'est l'installateur, via le Gestionnaire de redémarrage de
    Windows, qui ferme Rubin et le relance une fois les fichiers remplacés.
    Rubin n'a donc pas besoin de s'arrêter lui-même avant d'appeler cette
    fonction, ni d'attendre que l'installation soit finie : le processus est
    lancé détaché, la fonction rend la main tout de suite.

    `/NORESTART` porte sur Windows lui-même, jamais sur Rubin : rien ici ne
    redémarre l'ordinateur.
    """
    subprocess.Popen(  # noqa: S603
        [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/RESTARTAPPLICATIONS",
        ],
        close_fds=True,
    )
