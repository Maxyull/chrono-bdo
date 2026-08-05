"""Consultation des temps de référence publiés par le serveur.

Sert à répondre, pendant la partie, à la seule question qui vaille sur le
moment : est-ce que je viens d'aller plus vite ou moins vite que les autres.

Trois règles gouvernent ce module, et elles découlent toutes du fait qu'il
travaille pendant qu'on joue.

**Rien ne doit jamais gêner la mesure.** Un serveur injoignable, lent ou
incohérent ne peut pas faire disparaître un chronométrage ni interrompre une
session : toute erreur devient une absence de référence, ce qui n'ôte rien à ce
qui a été mesuré.

**Chaque quête n'est demandée qu'une fois.** Les réponses sont gardées en
mémoire, y compris les absences : une quête que personne n'a jamais mesurée le
restera pendant la session, et redemander à chaque passage ne ferait
qu'ajouter de la latence pour la même réponse vide.

**Rien n'est demandé depuis le fil de capture.** Les appels ont lieu dans le
fil de lecture, qui a déjà le droit d'être lent. L'écran reste surveillé
pendant ce temps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import requests

from .reference import QuestId

_TIMEOUT: Final = 5
_USER_AGENT: Final = "chrono-bdo"


@dataclass(frozen=True)
class QuestReference:
    """Ce que les autres joueurs ont mesuré sur une quête."""

    median_seconds: float
    samples: int
    fastest_seconds: float

    def compare(self, seconds: float) -> str:
        """Écart à la médiane, en toutes lettres.

        Un écart relatif plutôt qu'absolu : trente secondes de plus ne veulent
        pas dire la même chose sur une quête d'une minute et sur une quête d'un
        quart d'heure.
        """
        if self.median_seconds <= 0:
            return ""
        ratio = (seconds - self.median_seconds) / self.median_seconds
        if abs(ratio) < 0.05:
            return "dans la moyenne"
        return f"{abs(ratio) * 100:.0f}% {'plus lent' if ratio > 0 else 'plus rapide'}"


@dataclass(frozen=True)
class ChainReference:
    """Ce que les autres joueurs ont mesuré sur une chaîne entière."""

    measured_quests: int
    median_seconds: float
    quests_per_hour: float
    measured_total_seconds: float
    samples: int


class ReferenceClient:
    """Lit les références sur le serveur, sans jamais faire échouer l'appelant."""

    def __init__(self, base_url: str | None, timeout: int = _TIMEOUT) -> None:
        self._base = base_url.rstrip("/") if base_url else None
        self._timeout = timeout
        # Les absences sont mises en cache comme les présences : une quête que
        # personne n'a mesurée le restera pendant toute la session.
        self._quests: dict[QuestId, QuestReference | None] = {}
        self._chains: dict[int, ChainReference | None] = {}
        #: Nombre d'appels qui n'ont pas abouti. Utile pour dire à la fin que
        #: les références manquaient, plutôt que de laisser croire qu'aucune
        #: quête n'avait jamais été mesurée.
        self.failures = 0

    @property
    def enabled(self) -> bool:
        return self._base is not None

    def _get(self, path: str) -> dict[str, Any] | None:
        if self._base is None:
            return None
        try:
            response = requests.get(
                self._base + path,
                headers={"User-Agent": _USER_AGENT},
                timeout=self._timeout,
            )
        except requests.RequestException:
            self.failures += 1
            return None
        if response.status_code == 404:
            return None  # quête jamais mesurée : une absence, pas une panne
        if response.status_code >= 400:
            self.failures += 1
            return None
        try:
            body: dict[str, Any] = response.json()
        except ValueError:
            self.failures += 1
            return None
        return body

    def quest(self, quest_id: QuestId) -> QuestReference | None:
        if quest_id in self._quests:
            return self._quests[quest_id]
        body = self._get(f"/v1/quetes/{quest_id.chain}/{quest_id.position}")
        reference = (
            QuestReference(
                median_seconds=float(body.get("median_seconds", 0)),
                samples=int(body.get("samples", 0)),
                fastest_seconds=float(body.get("fastest_seconds", 0)),
            )
            if body
            else None
        )
        self._quests[quest_id] = reference
        return reference

    def chain(self, number: int) -> ChainReference | None:
        if number in self._chains:
            return self._chains[number]
        body = self._get(f"/v1/chaines/{number}")
        reference = (
            ChainReference(
                measured_quests=int(body.get("measured_quests", 0)),
                median_seconds=float(body.get("median_seconds", 0)),
                quests_per_hour=float(body.get("quests_per_hour", 0)),
                measured_total_seconds=float(body.get("measured_total_seconds", 0)),
                samples=int(body.get("samples", 0)),
            )
            if body
            else None
        )
        self._chains[number] = reference
        return reference
