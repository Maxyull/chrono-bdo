"""Point d'entrée de l'exécutable.

Un fichier à part plutôt que `-m rubin` : l'empaqueteur a besoin d'un script
réel à analyser, et ce détour permet aussi de traiter ici ce qui ne concerne
que la version empaquetée.
"""

from __future__ import annotations

import ctypes
import multiprocessing
import sys


def _attach_to_parent_console() -> None:
    """Se rattache à la console de qui a lancé l'exécutable, si elle existe.

    L'exécutable est construit sans console propre depuis le 5 août 2026 au
    soir (`console=False` dans `rubin.spec`) : un joueur qui double-clique
    voyait jusque-là une fenêtre noire s'ouvrir à côté de la fenêtre de Rubin,
    sans rien y comprendre, et devait la fermer elle aussi. Rien ne la
    justifiait pour ce chemin-là, la fenêtre graphique dit tout ce qu'il faut.

    Mais `rubin verifier`, `rubin suivre` et `rubin echecs` restent des
    commandes de terminal, et leur texte doit continuer à s'afficher pour qui
    les tape. Sans console propre, un exécutable ainsi construit n'a par
    défaut AUCUNE sortie du tout, pas même dans le terminal qui l'a lancé :
    `AttachConsole` le raccroche à la console de son parent quand elle existe,
    et les flux standard sont rouverts sur elle. Lancé par un double-clic
    depuis l'explorateur, il n'y a pas de console parente : l'appel échoue
    sans bruit, et c'est exactement le silence voulu.
    """
    ATTACH_PARENT_PROCESS = -1
    if not ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        return
    # Les flux ouverts par Python au démarrage pointaient sur une console qui
    # n'existait pas : les rouvrir sur celle qu'on vient de rejoindre est
    # nécessaire, `AttachConsole` seul ne suffit pas à faire réapparaître
    # `print`.
    # `Path.open()` ne convient pas ici : "CONOUT$"/"CONIN$" sont des noms de
    # périphérique Windows, pas des chemins de système de fichiers.
    sys.stdout = open(  # noqa: SIM115, PTH123
        "CONOUT$", "w", encoding="utf-8", errors="replace"
    )
    sys.stderr = open(  # noqa: SIM115, PTH123
        "CONOUT$", "w", encoding="utf-8", errors="replace"
    )
    sys.stdin = open("CONIN$", encoding="utf-8", errors="replace")  # noqa: SIM115, PTH123


if __name__ == "__main__":
    if sys.platform == "win32":
        _attach_to_parent_console()
    # Sans cet appel, un exécutable Windows qui crée un processus relance
    # l'exécutable entier au lieu du processus voulu, indéfiniment. onnxruntime
    # peut en créer, donc l'oubli se paierait par une bombe à retardement au
    # lieu d'une erreur visible.
    multiprocessing.freeze_support()

    from rubin.__main__ import main

    sys.exit(main())
