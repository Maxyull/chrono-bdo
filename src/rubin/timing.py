"""Du bandeau lu à la durée mesurée.

Ce module n'est pas un chronomètre au sens habituel, avec un bouton départ et
un bouton arrêt. C'est un **journal d'événements** qui reconstruit les durées
après coup, et la différence est délibérée.

Un chronomètre suppose qu'on voie toujours le départ et l'arrivée. Or le
bandeau de fin se rate : quand un joueur enchaîne vite, il peut passer sans
avoir été capturé. Un chronomètre resterait alors bloqué sur une quête
terminée, et fausserait tout ce qui suit.

Le journal, lui, note ce qu'il voit et en tire ce qu'il peut. Voir démarrer la
quête 21136/2 prouve que 21136/1 vient de s'achever, puisque l'identifiant
d'une quête est une paire chaîne/position. La mesure est alors marquée comme
déduite plutôt qu'exacte, et reste exploitable.

Cette déduction est même la plus utile des deux. Ce qui intéresse un joueur qui
veut abattre des milliers de quêtes, ce n'est pas le temps d'exécution pur,
c'est le débit : accepté vers accepté suivant, trajet compris.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum

from .reading import BannerKind, BannerReading
from .reference import Catalog, QuestId


class Quality(Enum):
    """Ce qui a réellement été observé pour établir une durée."""

    #: Les deux bandeaux ont été vus. Durée d'exécution de la quête seule.
    EXACT = "exacte"
    #: La fin a été manquée, mais le départ de la quête suivante de la même
    #: chaîne l'implique. La durée inclut le passage à la quête suivante.
    DEDUCED = "deduite"


@dataclass(frozen=True)
class Event:
    """Un bandeau lu, horodaté et rapproché du référentiel."""

    at: float
    kind: BannerKind
    quest_name: str
    confidence: float
    #: `None` quand le nom n'a pas pu être rapproché d'une quête connue, ce qui
    #: arrive pour 18 % des quêtes principales dont le nom est partagé.
    quest_id: QuestId | None = None


@dataclass(frozen=True)
class Measure:
    """Une durée établie pour une quête."""

    quest_id: QuestId
    seconds: float
    quality: Quality
    started_at: float
    ended_at: float
    confidence: float


@dataclass
class _Pending:
    """Une quête commencée dont on attend la fin."""

    quest_id: QuestId
    at: float
    confidence: float


@dataclass
class Timeline:
    """Le journal des événements d'une session, et les durées qu'il produit.

    `catalog` sert à rapprocher un nom lu d'un identifiant. Sans identifiant,
    l'événement est conservé dans le journal mais ne produit aucune mesure :
    on préfère un trou dans les données à une durée attribuée au hasard.
    """

    catalog: Catalog
    language: str = "fr"
    clock: Callable[[], float] = time.monotonic
    events: list[Event] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    _pending: _Pending | None = field(default=None, init=False, repr=False)
    #: Mesures écartées faute d'identifiant ou de continuité, pour rendre
    #: compte de ce qui a été perdu plutôt que de le taire.
    dropped: int = 0

    def record(self, reading: BannerReading, at: float | None = None) -> Measure | None:
        """Enregistre un bandeau lu, et renvoie la mesure qu'il clôt, s'il en clôt une."""
        moment = self.clock() if at is None else at
        # La chaîne en cours sert de contexte : c'est elle qui permet de
        # trancher quand un nom désigne plusieurs quêtes, ce qui arrive pour
        # 18 % des quêtes principales.
        quest_id = self.catalog.resolve_lines(
            reading.name_lines or (reading.quest_name,),
            self.language,
            chain=self.current_chain,
            after_position=self.current_position,
        )
        event = Event(
            at=moment,
            kind=reading.kind,
            quest_name=reading.quest_name,
            confidence=reading.confidence,
            quest_id=quest_id,
        )
        self.events.append(event)

        if reading.kind is BannerKind.COMPLETED:
            return self._close_exact(event)
        if reading.kind is BannerKind.ACCEPTED:
            return self._open(event)
        # Les bandeaux d'objectif racontent ce qui se passe pendant la quête.
        # Ils sont conservés pour l'analyse, mais ne bornent aucune durée.
        return None

    def _open(self, event: Event) -> Measure | None:
        """Ouvre une mesure, en clôturant la précédente si elle s'enchaîne."""
        deduced = self._deduce(event)
        self._pending = (
            _Pending(event.quest_id, event.at, event.confidence)
            if event.quest_id is not None
            else None
        )
        if event.quest_id is None:
            self.dropped += 1
        return deduced

    def _deduce(self, event: Event) -> Measure | None:
        """Clôt la quête en cours quand la nouvelle la suit dans sa chaîne."""
        pending, self._pending = self._pending, None
        if pending is None or event.quest_id is None:
            if pending is not None:
                self.dropped += 1
            return None

        follows = (
            event.quest_id.chain == pending.quest_id.chain
            and event.quest_id.position == pending.quest_id.position + 1
        )
        if not follows:
            # Le joueur a changé de chaîne, ou plusieurs quêtes ont passé sans
            # être vues. Rien ne permet de savoir ce qui s'est passé entre les
            # deux, donc rien n'est mesuré.
            self.dropped += 1
            return None

        measure = Measure(
            quest_id=pending.quest_id,
            seconds=event.at - pending.at,
            quality=Quality.DEDUCED,
            started_at=pending.at,
            ended_at=event.at,
            confidence=min(pending.confidence, event.confidence),
        )
        self.measures.append(measure)
        return measure

    def _close_exact(self, event: Event) -> Measure | None:
        pending = self._pending
        if pending is None or event.quest_id is None or event.quest_id != pending.quest_id:
            # Une fin qui ne correspond à aucun départ connu : le logiciel a
            # démarré au milieu d'une quête, ou le départ a été manqué. Il n'y
            # a pas d'instant de départ, donc pas de durée.
            if pending is not None and event.quest_id != pending.quest_id:
                self.dropped += 1
                self._pending = None
            return None

        self._pending = None
        measure = Measure(
            quest_id=pending.quest_id,
            seconds=event.at - pending.at,
            quality=Quality.EXACT,
            started_at=pending.at,
            ended_at=event.at,
            confidence=min(pending.confidence, event.confidence),
        )
        self.measures.append(measure)
        return measure

    def feed(self, readings: Iterator[BannerReading]) -> Iterator[Measure]:
        """Enchaîne les lectures et rend les mesures au fil de l'eau."""
        for reading in readings:
            measure = self.record(reading)
            if measure is not None:
                yield measure

    @property
    def current_chain(self) -> int | None:
        """La chaîne dans laquelle le joueur se trouve, autant qu'on le sache.

        Celle de la quête en cours si elle est connue, sinon celle du dernier
        événement identifié. Le second cas compte : entre deux quêtes, aucune
        n'est ouverte, et c'est précisément le moment où le bandeau de la
        suivante apparaît.
        """
        if self._pending is not None:
            return self._pending.quest_id.chain
        for event in reversed(self.events):
            if event.quest_id is not None:
                return event.quest_id.chain
        return None

    @property
    def current_position(self) -> int | None:
        """Position de la dernière quête identifiée dans sa chaîne.

        Sert à départager les homonymes d'une même chaîne, en retenant celle
        qui suit immédiatement.
        """
        if self._pending is not None:
            return self._pending.quest_id.position
        for event in reversed(self.events):
            if event.quest_id is not None:
                return event.quest_id.position
        return None

    @property
    def pending_quest(self) -> QuestId | None:
        """La quête en cours de mesure, s'il y en a une."""
        return self._pending.quest_id if self._pending else None

    @property
    def pending_since(self) -> float | None:
        """L'instant où la quête en cours a été acceptée, s'il y en a une.

        Une propriété plutôt qu'un accès à `_pending` depuis l'affichage : la
        forme interne du journal n'est l'affaire de personne d'autre, et une
        fenêtre qui lirait un attribut privé se casserait le jour où il change,
        sans qu'aucun test du journal ne le voie.

        ⚠️ **C'est un instant en temps monotone**, celui de `clock`, qui vaut
        `time.monotonic` par défaut. Ce n'est pas une heure du jour : le
        soustraire d'un `time.time()` donnerait un écart de plusieurs
        milliards de secondes, et rien ne lèverait d'erreur.

        `None` a un sens fort ici, et pas seulement « pas encore commencé » :
        aucune quête n'est ouverte, donc rien n'est chronométré. C'est
        exactement ce qu'un joueur doit voir quand un bandeau de départ a été
        ignoré, cas aujourd'hui parfaitement silencieux.
        """
        return self._pending.at if self._pending else None

    def total_seconds(self) -> float:
        return sum(m.seconds for m in self.measures)
