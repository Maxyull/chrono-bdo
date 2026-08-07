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


def launch_installer(installer: Path) -> None:
    """Lance l'installateur en silence, et laisse Windows fermer Rubin.

    ⛔ **Ne ferme pas Rubin, volontairement.** `CloseApplications=force`,
    posé dans `rubin.iss`, fait fermer l'application par le Gestionnaire de
    redémarrage de Windows. Se fermer avant qu'il ait enregistré le processus
    l'empêche de faire ce travail proprement.

    ⛔ **`/RELANCER` remplace `/RESTARTAPPLICATIONS` depuis le 07/08/2026.**
    Constaté par Maxime en cliquant pour de vrai : Rubin ne revenait pas après
    une mise à jour. La relance reposait entièrement sur le Gestionnaire de
    redémarrage, et il ne l'a pas faite. Vu du joueur, une mise à jour qui fait
    disparaître le logiciel pour de bon est pire que pas de mise à jour.

    La réouverture est désormais une ligne explicite de la section `[Run]` de
    l'installateur, conditionnée à ce commutateur. Un mécanisme qu'on peut
    lire, tester et voir échouer, au lieu d'un comportement du système qu'on
    espère.

    ⚠️ **Les deux ne doivent jamais coexister** : le Gestionnaire de
    redémarrage et la section `[Run]` rouvriraient chacun leur exemplaire, et
    deux Rubin en parallèle voudraient dire deux fils de capture sur la même
    session, donc la même quête envoyée deux fois au serveur.

    ⭐ Butin, le logiciel jumeau, a rencontré le même défaut le même jour et l'a
    tranché ainsi le premier. Rubin s'aligne sur lui plutôt que d'entretenir
    deux mécanismes différents pour un seul problème.

    `/NORESTART` porte sur Windows lui-même, jamais sur Rubin : rien ici ne
    redémarre l'ordinateur.
    """
    subprocess.Popen(  # noqa: S603
        [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/RELANCER",
        ],
        close_fds=True,
    )
