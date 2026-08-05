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

#: Nombre de mesures en dessous duquel une quête n'est pas classée.
#:
#: **Recopié du serveur plutôt qu'importé**, comme `WELL_MEASURED_AT` l'est dans
#: l'autre sens : ce client ne dépend pas du paquet du serveur, et il ne peut de
#: toute façon pas connaître le seuil avant de l'avoir demandé. La valeur voyage
#: dans la requête, et la réponse la répète, donc un écart entre les deux se
#: verrait plutôt que de se deviner.
#:
#: Trois, et jamais un : sur une mesure, la « médiane » est cette mesure ; sur
#: deux, c'est leur moyenne, donc un passage chanceux tire le résultat de la
#: moitié de son écart. À partir de trois, la médiane est une valeur réellement
#: observée, qu'aucune mesure isolée ne peut devenir. Relevé en production le
#: 05/08/2026 : une chaîne en tête à 198,8 quêtes/heure sur une seule mesure.
MIN_SAMPLES_PER_QUEST: Final = 3

#: Longueur du classement affiché. Un top dix se lit d'un coup d'œil ; une liste
#: de cinquante demanderait de la chercher, et ce n'est pas ce qu'on vient y
#: faire pendant qu'on joue.
RANKING_LIMIT: Final = 10


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
class RankedQuest:
    """Une ligne du classement des quêtes par temps médian.

    ⚠️ **Aucun nom de quête ici, et ce n'est pas un oubli.** Le serveur ne
    connaît que `chaine/position` : les noms appartiennent au catalogue, que ce
    client porte. La résolution se fait donc à l'affichage, dans
    `interface.presentation`, et jamais côté serveur.
    """

    chain: int
    position: int
    #: La médiane, jamais le record, comme partout dans ce projet.
    median_seconds: float
    #: Sur combien de mesures. Affiché à côté de chaque ligne : un temps sans son
    #: assise se croit plus solide qu'il n'est, et c'est pire à la quête qu'à la
    #: chaîne.
    samples: int

    @property
    def quest_id(self) -> QuestId:
        return QuestId(self.chain, self.position)


@dataclass(frozen=True)
class ServerHealth:
    """Ce que `/sante` rend, quand le serveur répond.

    Sert au témoin de connexion de la fenêtre. Trois états doivent se
    distinguer, parce qu'ils appellent trois gestes différents : aucun serveur
    configuré, serveur configuré mais injoignable, et connecté. Une instance de
    cette classe est le troisième ; `None` ne dit à lui seul rien des deux
    autres, et c'est l'affichage qui les sépare, en sachant si une adresse avait
    été donnée.
    """

    protocol: int
    sessions: int
    measures: int
    players: int


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


def _as_int(value: Any) -> int:
    """Un entier, quoi qu'on lui donne. Zéro plutôt qu'une exception.

    Le serveur est censé rendre des nombres, mais ce module a pour règle de ne
    jamais lever : un champ absent, nul ou rendu en texte par une version
    antérieure ne doit pas emporter la fenêtre pour un compteur d'affichage.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_ranked(row: dict[str, Any]) -> RankedQuest | None:
    """Une ligne du classement, ou `None` si elle est inexploitable.

    Une ligne écartée coûte une ligne ; une exception coûterait tout le
    classement, et par ricochet le fil qui l'a demandé.
    """
    try:
        return RankedQuest(
            chain=int(row["chain"]),
            position=int(row["position"]),
            median_seconds=float(row["median_seconds"]),
            samples=int(row.get("samples", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return None


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
        self._rankings: dict[tuple[int, int], tuple[RankedQuest, ...] | None] = {}
        self._health: ServerHealth | None = None
        self._health_asked = False
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

    def fastest_quests(
        self, limit: int = RANKING_LIMIT, min_samples: int = MIN_SAMPLES_PER_QUEST
    ) -> tuple[RankedQuest, ...] | None:
        """Les quêtes les plus rapides, ou `None` si le serveur n'a rien dit.

        ⚠️ **Une liste vide et `None` ne veulent pas dire la même chose**, et
        c'est le seul point délicat de cette méthode. Une liste vide est une
        réponse : aucune quête n'atteint le seuil, ce qui est l'état du jour
        puisque la base porte vingt-et-une mesures presque toutes uniques.
        `None` est une absence de réponse : serveur injoignable, ou serveur d'une
        version antérieure qui ne connaît pas encore cette adresse, ce qui est
        exactement le cas de la production au moment où ces lignes s'écrivent.
        Les confondre afficherait « aucune quête assez mesurée » sur un serveur
        muet, c'est-à-dire une affirmation à la place d'un « je ne sais pas ».

        Comme le reste du module, elle **ne lève jamais** : une ligne malformée
        est écartée, et le reste de la liste passe. Un classement est un décor,
        la mesure est la fonction.
        """
        key = (limit, min_samples)
        if key in self._rankings:
            return self._rankings[key]
        body = self._get(f"/v1/quetes?limit={limit}&min_samples={min_samples}")
        ranking: tuple[RankedQuest, ...] | None = None
        if body is not None:
            rows = body.get("quetes")
            ranking = tuple(
                quest
                for row in (rows if isinstance(rows, list) else [])
                if isinstance(row, dict) and (quest := _read_ranked(row)) is not None
            )
        self._rankings[key] = ranking
        return ranking

    def health(self) -> ServerHealth | None:
        """L'état du serveur, ou `None` s'il n'a pas répondu.

        `/sante` et pas autre chose : elle répond sans condition ni compte, elle
        existe depuis le premier jour, et elle ne dépend d'aucune donnée. Une
        adresse plus récente ferait passer pour injoignable un serveur qui
        tourne parfaitement mais n'a pas encore été redéployé, ce qui est
        précisément l'erreur de diagnostic à éviter : un point d'entrée manquant
        n'est pas une panne de connexion.

        Ne lève jamais, comme le reste du module.
        """
        if self._health_asked:
            return self._health
        body = self._get("/sante")
        self._health_asked = True
        self._health = (
            ServerHealth(
                protocol=_as_int(body.get("protocole")),
                sessions=_as_int(body.get("sessions")),
                measures=_as_int(body.get("measures")),
                players=_as_int(body.get("players")),
            )
            if body
            else None
        )
        return self._health

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
