"""Capturer maintenant, lire plus tard.

Le défaut de la boucle simple est qu'elle s'arrête de regarder pendant qu'elle
lit. Une reconnaissance prend entre 300 et 1 000 millisecondes, et durant tout
ce temps l'écran n'est pas surveillé. Un bandeau qui apparaît et disparaît dans
cet intervalle est perdu, sans que rien ne le signale. C'est justement quand le
joueur enchaîne vite, donc quand les mesures sont les plus intéressantes, que
le risque est le plus grand.

Ici, deux fils séparés. L'un capture à cadence régulière et ne fait que décider
si l'image mérite d'être lue, ce qui coûte 14 millisecondes. L'autre lit,
tranquillement, avec le retard qu'il veut.

Trois conséquences :

- **plus aucun bandeau raté pendant une lecture**, l'écran est surveillé sans
  interruption ;
- la lecture peut prendre le temps qu'il faut pour être juste, puisque sa durée
  ne coûte plus rien ;
- les images conservées peuvent être **relues plus tard**, quand la
  reconnaissance s'améliore, ou envoyées pour analyse.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from types import TracebackType
from typing import Final

from .capture import GrayFrame
from .reading import BannerReading, TextReader, parse_banner
from .watching import BannerWatcher

#: Cadence de capture. Huit fois par seconde : le bandeau reste affiché
#: plusieurs secondes, et un tour ne coûte que 14 millisecondes.
POLL_INTERVAL: Final = 0.125

#: Nombre maximal d'images en attente de lecture.
#:
#: En pratique la file reste vide : les bandeaux nouveaux se comptent en
#: dizaines par heure, la lecture en dixièmes de seconde. Cette borne n'existe
#: que pour qu'un incident, une reconnaissance qui s'effondre par exemple, ne
#: fasse pas gonfler la mémoire sans fin. Une image en gris pèse 40 Ko, donc
#: cette limite plafonne à 20 Mo.
MAX_PENDING: Final = 500


@dataclass(frozen=True)
class CapturedFrame:
    """Une image jugée digne d'être lue, avec l'instant de sa capture.

    L'instant est celui de la **capture**, pas celui de la lecture. C'est lui
    qui compte : une mesure doit dire quand le bandeau est apparu à l'écran,
    pas quand le logiciel a fini d'y réfléchir.
    """

    image: GrayFrame
    at: float


class DeferredWatcher:
    """Surveille dans un fil, lit dans un autre."""

    def __init__(
        self,
        watcher: BannerWatcher,
        reader: TextReader,
        interval: float = POLL_INTERVAL,
        max_pending: int = MAX_PENDING,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._watcher = watcher
        self._reader = reader
        self._interval = interval
        self._clock = clock
        self._pending: deque[CapturedFrame] = deque(maxlen=max_pending)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: Images perdues faute de place. Doit rester à zéro ; le contraire
        #: signale que la lecture ne suit plus, et le dit plutôt que de le taire.
        self.overflowed = 0

    def _capture_loop(self) -> None:
        while not self._stop.is_set():
            started = self._clock()
            frame = self._watcher.capture_pending()
            if frame is not None:
                with self._lock:
                    if len(self._pending) == self._pending.maxlen:
                        self.overflowed += 1
                    self._pending.append(CapturedFrame(image=frame, at=started))
                self._wake.set()
            # Le sommeil passe par l'événement d'arrêt : la boucle s'interrompt
            # sans attendre la fin du délai en cours.
            self._stop.wait(max(0.0, self._interval - (self._clock() - started)))

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def take_pending(self) -> list[CapturedFrame]:
        """Retire et renvoie les images en attente."""
        with self._lock:
            frames = list(self._pending)
            self._pending.clear()
        return frames

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def readings(self, timeout: float | None = None) -> Iterator[tuple[BannerReading, float]]:
        """Rend les bandeaux lus, avec l'instant de leur **capture**.

        Bloque en attendant qu'une image arrive, puis vide la file. S'arrête
        quand la surveillance s'arrête, sans perdre ce qui restait à lire : les
        dernières images sont lues avant de rendre la main.
        """
        while True:
            if not self._pending:
                self._wake.wait(timeout=timeout)
                self._wake.clear()
            frames = self.take_pending()
            for frame in frames:
                reading = parse_banner(self._reader.read(frame.image))
                if reading is not None:
                    yield reading, frame.at
            if self._stop.is_set() and not self._pending:
                return
            if not frames and timeout is not None:
                return

    def __enter__(self) -> DeferredWatcher:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()
