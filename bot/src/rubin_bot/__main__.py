"""Point d'entrée du robot.

Sans jeton, il dit ce qui manque et s'arrête proprement : ni trace de pile, ni
connexion tentée avec un jeton vide. C'est l'état attendu tant que
l'application Discord n'a pas été créée sur le portail développeur, ce qui
n'est pas du code et ne se fait pas ici.
"""

from __future__ import annotations

import logging
import sys

from .configuration import MISSING_TOKEN, Configuration


def run(argv: list[str] | None = None) -> int:
    """Démarre le robot, ou explique pourquoi il ne démarre pas.

    Rend 0 quand la passerelle s'est fermée normalement, 1 quand la
    configuration manque ou que Discord a refusé le jeton. Un code non nul
    plutôt que zéro : un service qui ne fait rien en annonçant que tout va bien
    est un service dont personne ne remarque la panne.
    """
    del argv  # aucune option : tout se règle par l'environnement
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    configuration = Configuration.from_env()
    if not configuration.ready:
        print(MISSING_TOKEN)
        return 1

    # L'import est différé pour que le message ci-dessus reste affichable même
    # si la bibliothèque Discord manque, ce qui est le cas d'un environnement
    # où seules les vérifications tournent.
    from .bot import build_bot

    bot = build_bot(configuration.base_url, configuration.timeout)
    try:
        # `token` est vérifié non vide par `ready` juste au-dessus.
        bot.run(configuration.token or "", log_handler=None)
    except Exception as error:
        logging.getLogger("rubin_bot").error("le robot s'est arrêté : %s", error)
        return 1
    return 0


if __name__ == "__main__":  # pragma: pas de couverture
    sys.exit(run())
