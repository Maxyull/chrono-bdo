"""Le moteur de mesure, derrière le bouton Démarrer.

La fenêtre sans ce fichier était un tableau de bord sans moteur : elle savait
tout afficher et ne mesurait rien, parce que rien ne lançait jamais la boucle.
Constaté à l'usage, une quête terminée ne produisait ni temps ni liste.

## Pourquoi un bouton, et pas un démarrage automatique

Parce que **capturer l'écran de quelqu'un doit être un geste qu'il fait**. Un
logiciel qui se met à photographier l'écran dès son ouverture décide à la place
de son utilisateur, et le fait qu'il n'en garde presque rien n'y change rien.

Le bouton dit aussi quelque chose d'utile au logiciel : « je commence les
quêtes ». Une session ouverte pendant qu'on est au marché mesurerait des
attentes, pas des quêtes.

## Le fil ne touche jamais à l'affichage

Il dépose dans une file que la boucle de Tk vide depuis le bon fil. Un appel
direct à un composant depuis ici produirait des blocages qui n'arrivent qu'une
fois sur cent, donc jamais pendant qu'on regarde.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..capture import ScreenCapture, banner_region, find_game_window
from ..deferred import DeferredWatcher
from ..failures import FailureStore
from ..protocol import PlayerIdentity, build_session
from ..reading import RapidOcrReader
from ..reference import Catalog
from ..reference.source import catalog_date
from ..references import ReferenceClient
from ..settings import Settings
from ..timing import Quality, Timeline
from ..upload import save_session, send_session
from ..watching import BannerWatcher


@dataclass(frozen=True)
class Progress:
    """Ce que le moteur sait dire de la session en cours."""

    measured: int = 0
    exact: int = 0
    failed: int = 0
    elapsed: float = 0.0

    @property
    def deduced(self) -> int:
        return self.measured - self.exact


class MeasuringSession:
    """Mesure dans un fil séparé, et rend compte par une file de messages.

    `publish` est appelée depuis le fil de mesure : elle doit se contenter de
    déposer, jamais de dessiner.
    """

    def __init__(
        self,
        home: Path,
        catalog: Catalog,
        settings: Settings,
        publish: Callable[[str, Any], None],
        server: str | None = None,
    ) -> None:
        self._home = home
        self._catalog = catalog
        self._settings = settings
        self._publish = publish
        self._server = server
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.timeline: Timeline | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Lance la mesure. Rend `False` si le jeu est introuvable.

        Le jeu est cherché **au démarrage et non à l'ouverture de la fenêtre** :
        on ouvre souvent le logiciel avant de lancer le jeu, et refuser à ce
        moment-là obligerait à tout relancer dans le bon ordre.
        """
        if self.running:
            return True
        if find_game_window() is None:
            self._publish("etat", "jeu introuvable. Lancez Black Desert, puis réessayez.")
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout: float = 4.0) -> None:
        """Demande l'arrêt et attend que le fil ait fini son bilan."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ------------------------------------------------------------------ le fil

    def _run(self) -> None:
        window = find_game_window()
        if window is None:  # pragma: pas de couverture
            return
        langue = self._settings.language
        timeline = Timeline(catalog=self._catalog, language=langue)
        self.timeline = timeline
        references = ReferenceClient(self._server)
        failures = FailureStore(self._home / "echecs")
        failures.purge()
        # La purge a lieu au démarrage et non à l'arrêt : une session se termine
        # souvent par une fermeture brutale, et un ménage placé à la fin ne
        # serait jamais fait.

        zone = self._settings.banner or banner_region(window, ui_scale=self._settings.ui_scale)
        self._publish("etat", f"mesure en cours, zone {zone.width}x{zone.height}")
        self._publish("demarre", True)
        début = time.monotonic()
        dernière: tuple[int | None, int | None] = (None, None)

        try:
            reader = RapidOcrReader()
            with ScreenCapture(zone) as capture:
                watcher = BannerWatcher(capture, reader)
                with DeferredWatcher(
                    watcher,
                    reader,
                    interval=self._settings.poll_interval,
                    failures=failures,
                ) as deferred:
                    while not self._stop.is_set():
                        for reading, at in deferred.readings(timeout=0.5):
                            # L'instant retenu est celui de la capture, jamais
                            # celui de la lecture : sinon chaque mesure serait
                            # allongée de la durée de sa propre reconnaissance.
                            mesure = timeline.record(reading, at=at)
                            # Tout bandeau vu est annoncé, même ceux qui ne
                            # bornent aucune durée. Un bandeau d'objectif ne
                            # produit pas de mesure, et c'est voulu : il se
                            # passe PENDANT une quête. Mais se taire dessus
                            # laissait croire que rien n'était vu, alors que la
                            # lecture marchait parfaitement. Le silence ne
                            # distingue pas « je ne vois rien » de « je vois,
                            # ça ne se mesure pas ».
                            self._publish("vu", (reading, langue))
                            if mesure is not None:
                                self._publish("mesure", (mesure, langue))
                            ici = (timeline.current_chain, timeline.current_position)
                            if ici != dernière and ici[0] is not None:
                                self._publish("position", (ici[0], ici[1], references))
                                dernière = ici
                            self._publish(
                                "progres",
                                Progress(
                                    measured=len(timeline.measures),
                                    exact=sum(
                                        1
                                        for m in timeline.measures
                                        if m.quality is Quality.EXACT
                                    ),
                                    failed=deferred.failed,
                                    elapsed=time.monotonic() - début,
                                ),
                            )
                        if self._stop.is_set():
                            break
        except Exception as erreur:  # pragma: pas de couverture
            # Une panne ne doit pas emporter la fenêtre avec elle, ni faire
            # perdre ce qui a déjà été mesuré.
            self._publish("etat", f"mesure interrompue : {erreur}")
        finally:
            self._finish(timeline, time.monotonic() - début)
            self._publish("demarre", False)

    def _finish(self, timeline: Timeline, elapsed: float) -> None:
        """Écrit le lot sur le disque, et l'envoie si un serveur a été demandé.

        L'écriture a toujours lieu, l'envoi jamais tout seul. Une session
        mesurée puis perdue parce que le réseau a hoqueté serait irrattrapable :
        la partie, elle, ne se rejoue pas.
        """
        if not timeline.measures:
            self._publish("etat", f"arrêtée, aucune quête mesurée en {int(elapsed)} s")
            return
        try:
            identity = PlayerIdentity.load_or_create(self._home / "identite")
            lot = build_session(
                timeline,
                player=identity.value,
                catalog_date=catalog_date(self._settings.language),
                language=self._settings.language,
            )
            écrit = save_session(
                lot, self._home / "sessions" / f"session-{int(time.time())}.json"
            )
        except Exception as erreur:  # pragma: pas de couverture
            self._publish("etat", f"mesures gardées en mémoire, écriture impossible : {erreur}")
            return

        message = f"arrêtée, {len(timeline.measures)} quêtes mesurées, lot écrit dans {écrit}"
        if self._server:
            résultat = send_session(lot, self._server)
            message += (
                f" — envoyé, {résultat.stored} enregistrées"
                if résultat.ok
                else f" — envoi impossible, le lot est conservé ({résultat.detail})"
            )
        self._publish("etat", message)
