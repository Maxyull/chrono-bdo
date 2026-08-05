"""Point d'entrée de l'exécutable.

Un fichier à part plutôt que `-m chrono` : l'empaqueteur a besoin d'un script
réel à analyser, et ce détour permet aussi de traiter ici ce qui ne concerne
que la version empaquetée.
"""

from __future__ import annotations

import multiprocessing
import sys

from chrono.__main__ import main

if __name__ == "__main__":
    # Sans cet appel, un exécutable Windows qui crée un processus relance
    # l'exécutable entier au lieu du processus voulu, indéfiniment. onnxruntime
    # peut en créer, donc l'oubli se paierait par une bombe à retardement au
    # lieu d'une erreur visible.
    multiprocessing.freeze_support()
    sys.exit(main())
