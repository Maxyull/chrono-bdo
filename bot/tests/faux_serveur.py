"""Un vrai serveur HTTP, tenu par les tests.

Un objet simulé aurait vérifié que le code appelle ce qu'on croit qu'il
appelle, pas qu'il sait lire une réponse. Ici, la requête part réellement, avec
son en-tête, son code de statut et son corps : les tests couvrent donc aussi
l'analyse de la réponse et le délai d'attente, qui sont précisément les
endroits où un client HTTP se trompe.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@contextmanager
def faux_serveur(
    routes: dict[str, tuple[int, Any]],
    delai: float = 0.0,
) -> Iterator[str]:
    """Sert `routes` le temps du bloc, et rend son adresse de base.

    Les clés sont des chemins complets, paramètres compris, tels que le client
    les fabrique. Les valeurs sont un code de statut et un corps, qui est rendu
    en JSON sauf s'il s'agit déjà d'une chaîne, ce qui permet de servir du JSON
    volontairement invalide.
    """

    class Gestionnaire(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            if delai:
                time.sleep(delai)
            statut, corps = routes.get(self.path, (404, {"detail": "inconnu"}))
            charge = corps if isinstance(corps, str) else json.dumps(corps)
            octets = charge.encode("utf-8")
            self.send_response(statut)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(octets)))
            self.end_headers()
            self.wfile.write(octets)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Silence : la sortie des tests n'a pas à porter un journal HTTP."""

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{serveur.server_address[1]}"
    finally:
        serveur.shutdown()
        serveur.server_close()
        fil.join(timeout=5)
