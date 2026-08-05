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
_USER_AGENT: Final = "rubin-bdo"


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


@dataclass(frozen=True)
class Coverage:
    """Combien de quêtes le serveur voit bien mesurées, et combien peu.

    ⚠️ **Les quêtes jamais mesurées n'y sont pas, et ce n'est pas un oubli.**
    Le serveur ne connaît que les quêtes dont il a reçu au moins une mesure. Le
    nombre de quêtes principales, lui, est un fait du catalogue, que ce client
    porte et que le serveur n'a jamais vu : rien ne lui garantit d'ailleurs que
    tous les clients lisent le même. La soustraction appartient donc à ce
    côté-ci, et se fait dans `interface.presentation.format_coverage`.

    Réclamer ce chiffre au serveur reviendrait à lui faire affirmer ce qu'il ne
    peut pas vérifier, et un chiffre faux entre dans les affichages sans jamais
    en ressortir.
    """

    #: Quêtes portant au moins `threshold` mesures. Les vertes de l'interface.
    well_measured: int
    #: Quêtes mesurées, mais moins que `threshold`. Les oranges.
    lightly_measured: int
    #: Le seuil qui sépare les deux, tel que le serveur l'applique. Lu et non
    #: supposé : le jour où il bouge côté serveur, l'affichage suit.
    threshold: int
    #: Somme des deux tranches, c'est-à-dire tout ce que le serveur connaît.
    measured_quests: int


class ReferenceClient:
    """Lit les références sur le serveur, sans jamais faire échouer l'appelant."""

    def __init__(self, base_url: str | None, timeout: int = _TIMEOUT) -> None:
        self._base = base_url.rstrip("/") if base_url else None
        self._timeout = timeout
        # Les absences sont mises en cache comme les présences : une quête que
        # personne n'a mesurée le restera pendant toute la session.
        self._quests: dict[QuestId, QuestReference | None] = {}
        self._chains: dict[int, ChainReference | None] = {}
        self._coverage: Coverage | None = None
        self._coverage_asked = False
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

    def coverage(self) -> Coverage | None:
        """Combien de quêtes sont bien mesurées et peu mesurées, sur le serveur.

        Comme `quest` et `chain`, elle **ne lève jamais**. Un serveur
        injoignable, lent ou incohérent rend `None`, c'est-à-dire une absence
        d'information, jamais une panne de la fenêtre. Un compteur qui
        emporterait l'affichage avec lui coûterait bien plus cher que le
        compteur ne rapporte.

        ⚠️ `None` ne se remplace pas par des zéros à l'affichage. « 0 verte, 0
        orange, 3 924 grises » se lirait comme « personne n'a jamais rien
        mesuré », ce qui est une affirmation, et une fausse.

        La réponse est gardée en mémoire, absence comprise, comme le reste du
        module. Rien ne peut bouger en cours de session de toute façon : les
        mesures ne partent au serveur qu'à son arrêt.
        """
        if self._coverage_asked:
            return self._coverage
        body = self._get("/v1/couverture")
        self._coverage_asked = True
        self._coverage = (
            Coverage(
                well_measured=int(body.get("well_measured", 0)),
                lightly_measured=int(body.get("lightly_measured", 0)),
                threshold=int(body.get("threshold", 0)),
                measured_quests=int(body.get("measured_quests", 0)),
            )
            if body
            else None
        )
        return self._coverage
