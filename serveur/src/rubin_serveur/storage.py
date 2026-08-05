"""Le stockage des mesures, et les statistiques qu'on en tire.

Deux tables seulement. Une session est un envoi, une mesure est une durée. La
mesure ne porte pas de date, conformément au protocole : le serveur sait
combien de temps a pris une quête, jamais à quelle heure quelqu'un jouait.

La médiane est calculée en Python et non en base. Postgres saurait le faire,
SQLite non, et la même couche doit servir aux deux pour que les requêtes soient
vérifiées avant la mise en ligne et pas après. Sur les volumes attendus, des
dizaines de milliers de durées, l'écart de performance ne se voit pas.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from rubin.protocol import SessionPayload
from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

metadata = MetaData()

sessions = Table(
    "sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    # Identifiant anonyme du client. Sert à dédupliquer et à écarter en bloc
    # une source aberrante, jamais à savoir qui joue.
    Column("player", String(64), nullable=False, index=True),
    Column("language", String(8), nullable=False),
    Column("catalog_date", String(16), nullable=False),
    Column("protocol", Integer, nullable=False),
    Column("client", String(32), nullable=False),
    Column("dropped", Integer, nullable=False, default=0),
)

measures = Table(
    "measures",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", Integer, ForeignKey("sessions.id"), nullable=False),
    # La quête est éclatée en chaîne et position : c'est ce qui permet de
    # classer les chaînes entières sans découper une chaîne de caractères à
    # chaque requête.
    Column("chain", Integer, nullable=False, index=True),
    Column("position", Integer, nullable=False),
    Column("seconds", Float, nullable=False),
    Column("quality", String(16), nullable=False),
    Column("confidence", Float, nullable=False),
)


@dataclass(frozen=True)
class QuestStats:
    """Ce qu'on sait du temps d'une quête."""

    chain: int
    position: int
    #: La médiane, jamais le record. Un temps envoyé par un client local est
    #: falsifiable : un tricheur seul ne déplace pas une médiane sur des
    #: centaines de mesures, alors qu'il s'empare d'un record en une fois. Et
    #: la médiane est de toute façon le chiffre utile, puisqu'il s'agit de
    #: prévoir une durée, pas de couronner un champion.
    median_seconds: float
    samples: int
    fastest_seconds: float

    @property
    def quest(self) -> str:
        return f"{self.chain}/{self.position}"


@dataclass(frozen=True)
class ChainStats:
    """Le débit d'une chaîne, qui est la vraie question posée au logiciel."""

    chain: int
    measured_quests: int
    median_seconds: float
    #: Quêtes par heure, en supposant qu'on enchaîne au rythme médian. C'est ce
    #: chiffre qui permet de choisir par où commencer quand il reste des
    #: milliers de quêtes à faire.
    quests_per_hour: float
    samples: int
    #: Somme des temps médians des quêtes mesurées de la chaîne.
    #:
    #: C'est le chiffre qui répond à « combien de temps me prendra cette
    #: chaîne », et il n'est pas interchangeable avec le précédent. Le débit au
    #: rythme médian écrase les quêtes longues ; or il faudra bien les faire.
    #: Sur une session réelle de huit quêtes, le débit médian annonçait 77
    #: quêtes par heure là où la session en avait produit 36.
    measured_total_seconds: float
    #: Nombre de quêtes de la chaîne encore jamais mesurées, s'il est connu.
    #: Tant qu'il n'est pas nul, le total ci-dessus est un plancher, et se
    #: présenter autrement serait mentir.
    unmeasured_quests: int | None = None


class Storage:
    """Accès à la base, sans dépendance à son moteur."""

    def __init__(self, url: str = "sqlite+pysqlite:///:memory:", echo: bool = False) -> None:
        options: dict[str, Any] = {}
        if ":memory:" in url:
            # SQLite en mémoire crée une base **par connexion**. Avec le pool
            # par défaut, la table créée ici a disparu à la requête suivante,
            # qui échoue sur « no such table ». Une connexion unique et
            # partagée est la seule façon d'obtenir une base en mémoire qui
            # existe vraiment.
            options = {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            }
        self.engine: Engine = create_engine(url, echo=echo, future=True, **options)
        metadata.create_all(self.engine)

    def store(self, payload: SessionPayload) -> int:
        """Enregistre un lot, et renvoie le nombre de mesures retenues."""
        with self.engine.begin() as connection:
            result = connection.execute(
                sessions.insert().values(
                    player=payload.player,
                    language=payload.language,
                    catalog_date=payload.catalog_date,
                    protocol=payload.protocol,
                    client=payload.client,
                    dropped=payload.dropped,
                )
            )
            primary_key = result.inserted_primary_key
            if primary_key is None:  # pragma: pas de couverture
                raise RuntimeError("insertion de session sans clé primaire")
            session_id = primary_key[0]
            rows = []
            for measure in payload.measures:
                chain, _, position = measure.quest.partition("/")
                if not chain.isdigit() or not position.isdigit():
                    continue  # identifiant illisible : la mesure est écartée
                rows.append(
                    {
                        "session_id": session_id,
                        "chain": int(chain),
                        "position": int(position),
                        "seconds": measure.seconds,
                        "quality": measure.quality,
                        "confidence": measure.confidence,
                    }
                )
            if rows:
                connection.execute(measures.insert(), rows)
        return len(rows)

    def _durations(self, where: Any) -> list[tuple[int, int, float]]:
        with self.engine.connect() as connection:
            return [
                (row.chain, row.position, row.seconds)
                for row in connection.execute(
                    select(measures.c.chain, measures.c.position, measures.c.seconds).where(where)
                )
            ]

    def quest_stats(self, chain: int, position: int) -> QuestStats | None:
        rows = self._durations(
            (measures.c.chain == chain) & (measures.c.position == position)
        )
        if not rows:
            return None
        durations = sorted(seconds for _, _, seconds in rows)
        return QuestStats(
            chain=chain,
            position=position,
            median_seconds=round(statistics.median(durations), 1),
            samples=len(durations),
            fastest_seconds=round(durations[0], 1),
        )

    def chain_stats(self, chain: int) -> ChainStats | None:
        rows = self._durations(measures.c.chain == chain)
        if not rows:
            return None
        by_quest: dict[int, list[float]] = {}
        for _, position, seconds in rows:
            by_quest.setdefault(position, []).append(seconds)
        medians = [statistics.median(sorted(v)) for v in by_quest.values()]
        median = statistics.median(sorted(medians))
        return ChainStats(
            chain=chain,
            measured_quests=len(by_quest),
            median_seconds=round(median, 1),
            quests_per_hour=round(3600 / median, 1) if median else 0.0,
            samples=len(rows),
            measured_total_seconds=round(sum(medians), 1),
        )

    def ranked_chains(self, limit: int = 50, min_samples: int = 1) -> list[ChainStats]:
        """Les chaînes les plus rapides, à la quête.

        `min_samples` écarte les chaînes qu'une seule personne a mesurées une
        seule fois : une médiane sur un échantillon n'est pas une médiane, et
        laisser une telle ligne en tête du classement le décrédibiliserait.
        """
        with self.engine.connect() as connection:
            chains = [
                row.chain
                for row in connection.execute(
                    select(measures.c.chain, func.count().label("n"))
                    .group_by(measures.c.chain)
                    .having(func.count() >= min_samples)
                )
            ]
        stats = [s for chain in chains if (s := self.chain_stats(chain)) is not None]
        stats.sort(key=lambda s: s.quests_per_hour, reverse=True)
        return stats[:limit]

    def counts(self) -> dict[str, int]:
        with self.engine.connect() as connection:
            return {
                "sessions": connection.execute(
                    select(func.count()).select_from(sessions)
                ).scalar_one(),
                "measures": connection.execute(
                    select(func.count()).select_from(measures)
                ).scalar_one(),
                "players": connection.execute(
                    select(func.count(func.distinct(sessions.c.player)))
                ).scalar_one(),
            }
