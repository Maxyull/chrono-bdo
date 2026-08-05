"""Lecture de l'API publique de Rubin.

Trois règles gouvernent ce module, et elles découlent toutes du fait qu'il
parle à un serveur qui peut être lent, injoignable, ou en train de redémarrer.

**Une absence n'est pas une panne.** Le serveur rend 404 quand personne n'a
jamais mesuré une quête. C'est une information, et elle vaut d'être affichée
telle quelle. Une panne réseau, elle, ne dit rien du tout sur la quête : les
deux cas remontent donc séparément, `None` d'un côté, `ServerUnavailable` de
l'autre. Les confondre ferait dire au robot « jamais mesurée » à propos d'une
quête qu'il n'a simplement pas su interroger.

**Chaque appel porte un délai d'attente.** Sans lui, un serveur qui accepte la
connexion puis se tait laisse la commande Discord sans réponse pour toujours,
et l'utilisateur ne saura jamais pourquoi.

**Les numéros venus de Discord sont hostiles jusqu'à vérification.** Ils sont
bornés avant d'entrer dans une URL, et le champ `measured_total_seconds` du
serveur n'est délibérément pas lu, voir plus bas.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Final

import aiohttp

#: Serveur public par défaut. Surchargeable pour pointer une instance de
#: développement, jamais codé en dur ailleurs que ici.
DEFAULT_BASE_URL: Final = "https://rubin.maxyull.fr"

#: Délai d'attente total, en secondes. Une commande Discord doit recevoir sa
#: première réponse en moins de trois secondes ; au-delà, il faut différer.
#: Cinq secondes laissent la marge nécessaire sans laisser traîner un appel.
DEFAULT_TIMEOUT: Final = 5.0

USER_AGENT: Final = "rubin-bot"

#: Bornes des numéros acceptés. Le référentiel connaît 349 chaînes principales
#: dont les numéros vont de quelques milliers à quelques dizaines de milliers
#: (21136, 3500). Ces bornes ne prétendent pas dire quelles chaînes existent,
#: seulement écarter ce qui n'est de toute façon pas un numéro de chaîne, avant
#: que la valeur n'atteigne une URL.
MIN_CHAIN: Final = 1
MAX_CHAIN: Final = 999_999
MIN_POSITION: Final = 1
MAX_POSITION: Final = 9_999

#: Nombre de chaînes ramenées par le classement. Un message Discord tient dans
#: deux mille caractères : une trentaine de lignes est le maximum lisible.
MAX_RANKING: Final = 25

#: Seuil de mesures en dessous duquel une chaîne n'entre pas au classement.
#: Reprend le défaut du serveur. Une médiane sur un seul échantillon n'est pas
#: une médiane, et la laisser en tête décrédibiliserait tout le tableau.
DEFAULT_MIN_SAMPLES: Final = 3


class ServerUnavailable(Exception):
    """Le serveur n'a pas répondu, ou a répondu autre chose qu'attendu.

    Volontairement indistincte d'un cas à l'autre du côté de l'appelant : que
    ce soit un délai dépassé, un 502 du mandataire ou du JSON illisible, il n'y
    a rien à faire de différent, et rien d'utile à dire à un joueur.
    """


class InvalidQuestNumber(ValueError):
    """Un numéro de chaîne ou de position hors de tout domaine plausible."""


@dataclass(frozen=True)
class QuestTime:
    """Ce que les joueurs ont mesuré sur une quête.

    `samples` compte des **mesures**, pas des joueurs distincts : le serveur
    ne sait pas encore compter les seconds (voir `docs/ou-va-le-projet.md`).
    Rien de ce qui s'affiche ne doit donc parler de joueurs.
    """

    chain: int
    position: int
    median_seconds: float
    samples: int
    fastest_seconds: float


@dataclass(frozen=True)
class ChainTime:
    """Ce que les joueurs ont mesuré sur une chaîne entière.

    Le serveur publie aussi `measured_total_seconds`, la somme des médianes des
    quêtes mesurées. **Il n'est pas lu ici, et c'est délibéré.** Sur une session
    réelle, le rythme médian annonçait 77 quêtes par heure là où la session en
    avait produit 36 : trajets, dialogues, marché, mort. Une durée totale bâtie
    sur des médianes ment du simple au double, et elle ment en étant plausible
    et précise, ce qui est la pire des formes. Un champ qu'on ne lit pas est un
    champ qu'on ne peut pas afficher par mégarde.
    """

    chain: int
    measured_quests: int
    median_seconds: float
    quests_per_hour: float
    samples: int


def check_chain(chain: int) -> int:
    """Vérifie un numéro de chaîne avant qu'il n'entre dans une URL."""
    if not MIN_CHAIN <= chain <= MAX_CHAIN:
        raise InvalidQuestNumber(
            f"numéro de chaîne hors bornes : {chain}, attendu entre {MIN_CHAIN} et {MAX_CHAIN}"
        )
    return chain


def check_position(position: int) -> int:
    """Vérifie une position dans une chaîne avant qu'elle n'entre dans une URL."""
    if not MIN_POSITION <= position <= MAX_POSITION:
        raise InvalidQuestNumber(
            f"position hors bornes : {position}, attendu entre {MIN_POSITION} et {MAX_POSITION}"
        )
    return position


def _as_int(body: dict[str, Any], key: str) -> int:
    try:
        return int(body[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ServerUnavailable(f"réponse inattendue du serveur sur « {key} »") from error


def _as_float(body: dict[str, Any], key: str) -> float:
    try:
        return float(body[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ServerUnavailable(f"réponse inattendue du serveur sur « {key} »") from error


def _quest_from(body: dict[str, Any]) -> QuestTime:
    return QuestTime(
        chain=_as_int(body, "chain"),
        position=_as_int(body, "position"),
        median_seconds=_as_float(body, "median_seconds"),
        samples=_as_int(body, "samples"),
        fastest_seconds=_as_float(body, "fastest_seconds"),
    )


def _chain_from(body: dict[str, Any]) -> ChainTime:
    return ChainTime(
        chain=_as_int(body, "chain"),
        measured_quests=_as_int(body, "measured_quests"),
        median_seconds=_as_float(body, "median_seconds"),
        quests_per_hour=_as_float(body, "quests_per_hour"),
        samples=_as_int(body, "samples"),
    )


class RubinApi:
    """Client de lecture, et rien d'autre.

    Aucune méthode d'écriture n'existe ici : le robot ne peut pas envoyer de
    mesure même par erreur de programmation, puisqu'il n'en a pas le moyen.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = session
        #: Vrai quand la session appartient à l'appelant : on ne ferme jamais
        #: ce qu'on n'a pas ouvert.
        self._borrowed = session is not None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
            self._borrowed = False
        return self._session

    async def aclose(self) -> None:
        """Ferme la session HTTP, si c'est nous qui l'avons ouverte."""
        if self._session is not None and not self._borrowed and not self._session.closed:
            await self._session.close()

    async def _get(self, path: str) -> dict[str, Any] | None:
        """Rend le corps JSON, `None` sur 404, lève `ServerUnavailable` sinon."""
        session = await self._ensure_session()
        try:
            async with session.get(
                self._base + path,
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
            ) as response:
                if response.status == 404:
                    # Jamais mesurée. Une absence, pas une panne.
                    return None
                if response.status >= 400:
                    raise ServerUnavailable(f"le serveur a répondu {response.status}")
                body = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            raise ServerUnavailable(f"appel impossible : {error}") from error
        if not isinstance(body, dict):
            raise ServerUnavailable("le serveur n'a pas rendu d'objet JSON")
        return body

    async def quest(self, chain: int, position: int) -> QuestTime | None:
        """Temps d'une quête, ou `None` si personne ne l'a jamais mesurée."""
        check_chain(chain)
        check_position(position)
        body = await self._get(f"/v1/quetes/{chain}/{position}")
        return _quest_from(body) if body is not None else None

    async def chain(self, chain: int) -> ChainTime | None:
        """Temps d'une chaîne, ou `None` si personne ne l'a jamais mesurée."""
        check_chain(chain)
        body = await self._get(f"/v1/chaines/{chain}")
        return _chain_from(body) if body is not None else None

    async def ranking(
        self,
        limit: int = MAX_RANKING,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ) -> list[ChainTime]:
        """Les chaînes les plus rapides, au rythme médian.

        Une liste vide est une réponse valable, et même la réponse attendue
        aujourd'hui : la base ne contient que onze mesures, toutes d'un seul
        joueur sur une seule chaîne.
        """
        limit = max(1, min(limit, MAX_RANKING))
        min_samples = max(1, min_samples)
        body = await self._get(f"/v1/chaines?limit={limit}&min_samples={min_samples}")
        if body is None:
            # Cette adresse ne rend pas 404 : si elle le fait, c'est le serveur
            # qui a changé sous nos pieds, pas un classement vide.
            raise ServerUnavailable("le classement est introuvable sur ce serveur")
        rows = body.get("chaines")
        if not isinstance(rows, list):
            raise ServerUnavailable("le classement rendu n'est pas une liste")
        return [_chain_from(row) for row in rows if isinstance(row, dict)]
