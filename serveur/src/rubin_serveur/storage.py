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
    case,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

#: Nombre de mesures à partir duquel une quête est réputée bien mesurée.
#:
#: C'est le seuil déjà employé par l'interface, dans
#: `rubin/interface/theme.py`. Il est **recopié plutôt qu'importé** : ce module
#: doit se charger sur un serveur sans écran, or `theme.py` importe tkinter dès
#: son chargement. Une constante de plus vaut mieux qu'une dépendance graphique
#: dans un service web.
#:
#: Le seuil n'est pas statistique, il est honnête : la base contient onze
#: mesures d'un seul joueur, donc presque tout sera « peu mesuré », et c'est
#: exactement ce qu'il faut montrer.
WELL_MEASURED_AT = 5

#: Nombre de mesures en dessous duquel une quête n'entre pas au classement.
#:
#: **Trois, et le raisonnement n'est pas un arrondi de confort.** En dessous, la
#: médiane n'est pas une médiane :
#:
#: - sur **une** mesure, la « médiane » est cette mesure. Le classement rendrait
#:   le temps d'une personne, présenté comme celui de tout le monde ;
#: - sur **deux**, c'est la moyenne des deux, donc un passage chanceux tire le
#:   résultat de la moitié de son écart. Un tricheur, ou simplement un joueur
#:   qui a trouvé son objectif au premier coup, prend la tête à lui seul ;
#: - à partir de **trois**, la médiane est une valeur réellement observée, au
#:   milieu, et aucune mesure isolée ne peut la devenir.
#:
#: Le relevé qui a fait écrire cette constante est réel, pris en production le
#: 05/08/2026 : la chaîne 21403 tenait la tête du classement des chaînes à
#: **198,8 quêtes/heure sur UNE seule mesure**. Un classement de chaînes sur peu
#: de mesures est vague ; un classement de quêtes sur peu de mesures est faux et
#: convaincant, parce que la première place ira toujours à la quête mesurée une
#: fois par quelqu'un de chanceux.
MIN_SAMPLES_PER_QUEST = 3

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

#: Rattachement facultatif d'un contributeur à un compte Discord.
#:
#: Table séparée des sessions, et non colonne ajoutée : le rattachement se fait
#: une fois pour toutes tandis qu'un joueur envoie des dizaines de sessions, et
#: il doit pouvoir disparaître sans emporter les mesures avec lui.
players = Table(
    "players",
    metadata,
    Column("player", String(64), primary_key=True),
    Column("discord_id", String(32), nullable=False, index=True),
    Column("discord_name", String(64), nullable=False),
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


@dataclass(frozen=True)
class Coverage:
    """Combien de quêtes sont bien mesurées, et combien le sont peu.

    ⚠️ **Les quêtes jamais mesurées manquent, et c'est volontaire.** Le serveur
    ne connaît que les quêtes dont il a reçu au moins une mesure. Le nombre de
    quêtes principales, 3 924, est un fait du catalogue, que le client porte et
    que le serveur n'a jamais vu : rien ne lui garantit d'ailleurs que tous les
    clients lisent le même catalogue. Rendre ici un nombre de quêtes grises
    reviendrait à annoncer un chiffre qu'on ne peut pas vérifier, et un chiffre
    faux entre dans les affichages sans jamais en ressortir. La soustraction
    appartient au client, qui est le seul à connaître son propre total.

    ⚠️ **Ces tranches comptent des mesures, pas des contributeurs.** Un joueur a
    jusqu'à 44 personnages et refait chaque quête sur chacun : il peut donc
    légitimement mesurer 44 fois la même quête, qui passerait « bien mesurée »
    alors qu'une seule main a parlé. Le serveur ne distingue pas encore les
    contributeurs par quête ; la limite est connue et n'est pas corrigée ici.
    """

    #: Quêtes portant au moins `threshold` mesures. Les vertes de l'interface.
    well_measured: int
    #: Quêtes portant de 1 à `threshold - 1` mesures. Les orange de l'interface.
    lightly_measured: int
    #: Le seuil employé, rendu avec le résultat pour que la réponse se suffise
    #: à elle-même : un client qui l'aurait recopié verrait tout de suite qu'il
    #: n'a pas le même que le serveur.
    threshold: int = WELL_MEASURED_AT

    @property
    def measured_quests(self) -> int:
        """Total des quêtes que le serveur a vues passer, tranches confondues."""
        return self.well_measured + self.lightly_measured


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

    def ranked_quests(
        self, limit: int = 50, min_samples: int = MIN_SAMPLES_PER_QUEST
    ) -> list[QuestStats]:
        """Les quêtes les plus rapides, une par une, sur leur temps médian.

        C'est la bonne unité pour décider quoi faire, et `ranked_chains` ne la
        donne pas : une chaîne moyenne ses quêtes rapides et ses quêtes lentes,
        alors qu'on choisit quête par quête. C'est aussi ce que le planificateur
        consommera.

        ⚠️ **Le seuil compte ici plus que partout ailleurs.** Voir
        `MIN_SAMPLES_PER_QUEST` : en dessous de trois mesures, la première place
        revient mécaniquement à la quête qu'une seule personne a mesurée une
        seule fois, et la liste entière est fausse tout en paraissant précise.

        ⚠️ **La médiane, jamais le record**, comme partout dans ce projet. Un
        temps envoyé par un client local est une affirmation : un tricheur
        s'empare d'un record en un envoi, il ne déplace pas une médiane.

        Le tri retombe sur la chaîne puis la position à durée égale. Sans cela,
        deux quêtes au même temps changeraient de place d'un appel à l'autre au
        gré de l'ordre rendu par la base, et une liste qui bouge sans que rien
        n'ait changé se lit comme une liste qui ment.
        """
        with self.engine.connect() as connection:
            quests = [
                (row.chain, row.position)
                for row in connection.execute(
                    select(measures.c.chain, measures.c.position, func.count().label("n"))
                    .group_by(measures.c.chain, measures.c.position)
                    .having(func.count() >= min_samples)
                )
            ]
        stats = [
            s
            for chain, position in quests
            if (s := self.quest_stats(chain, position)) is not None
        ]
        stats.sort(key=lambda s: (s.median_seconds, s.chain, s.position))
        return stats[:limit]

    def coverage(self) -> Coverage:
        """Répartit les quêtes mesurées en deux tranches, en une seule requête.

        Le groupement et le comptage se font **en base**. Rapatrier toutes les
        mesures pour les compter en Python tiendrait tant qu'il y en a onze, et
        cesserait de tenir exactement quand le compteur deviendrait intéressant.

        Le `coalesce` n'est pas une précaution de style : une somme sur zéro
        ligne rend `NULL`, pas zéro. Sur une base vierge, juste après un
        déploiement, la réponse serait donc `None` là où le client attend un
        entier, et le compteur tomberait sur le seul cas où il est certain
        d'être appelé, le tout premier démarrage.
        """
        per_quest = (
            select(func.count().label("samples"))
            .select_from(measures)
            .group_by(measures.c.chain, measures.c.position)
            .subquery()
        )
        tally = select(
            func.coalesce(
                func.sum(case((per_quest.c.samples >= WELL_MEASURED_AT, 1), else_=0)), 0
            ).label("well_measured"),
            func.coalesce(
                func.sum(case((per_quest.c.samples < WELL_MEASURED_AT, 1), else_=0)), 0
            ).label("lightly_measured"),
        )
        with self.engine.connect() as connection:
            row = connection.execute(tally).one()
        return Coverage(
            well_measured=int(row.well_measured),
            lightly_measured=int(row.lightly_measured),
        )

    def link_discord(self, player: str, discord_id: str, discord_name: str) -> None:
        """Rattache un contributeur à un compte Discord, ou met à jour son nom.

        Un même compte Discord peut se rattacher à plusieurs identifiants : le
        joueur a réinstallé, ou joue sur deux machines. On ne l'interdit pas,
        parce que l'empêcher n'apporterait rien et casserait un cas légitime.
        """
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(players.c.player).where(players.c.player == player)
            ).first()
            if existing:
                connection.execute(
                    players.update()
                    .where(players.c.player == player)
                    .values(discord_id=discord_id, discord_name=discord_name)
                )
            else:
                connection.execute(
                    players.insert().values(
                        player=player, discord_id=discord_id, discord_name=discord_name
                    )
                )

    def display_name(self, player: str) -> str | None:
        """Nom à afficher pour ce contributeur, ou `None` s'il est resté anonyme."""
        with self.engine.connect() as connection:
            row = connection.execute(
                select(players.c.discord_name).where(players.c.player == player)
            ).first()
        return str(row.discord_name) if row else None

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
                "linked": connection.execute(
                    select(func.count()).select_from(players)
                ).scalar_one(),
            }
