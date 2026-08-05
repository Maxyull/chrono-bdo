"""Ce que le client envoie au serveur, et rien de plus.

Ce module est partagé : le client le sérialise, le serveur le relit. Le tenir
en un seul endroit est le seul moyen d'éviter que les deux définitions du même
lot ne divergent, ce qui donnerait des mesures acceptées puis mal interprétées,
la pire des issues.

**Aucune donnée personnelle n'y entre.** Ni pseudonyme du jeu, ni nom de
famille, ni horodatage à la seconde des sessions. Le classement n'a besoin que
de durées, et un identifiant tiré au sort au premier lancement suffit à
dédupliquer et à repérer un envoi aberrant sans jamais savoir de qui il vient.

La version du protocole est un entier à part, distinct de celle du logiciel.
Les deux ne vivent pas au même rythme : le logiciel se met à jour chez chaque
joueur quand il le veut, le serveur d'un coup. À tout instant, le serveur reçoit
des lots émis par plusieurs versions de client. Voir `docs/versionnage.md`.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from . import __version__

if TYPE_CHECKING:  # pragma: pas de couverture
    # Importé pour les annotations seulement. À l'exécution, ce module ne
    # dépend que de la bibliothèque standard : le serveur le relit sans avoir
    # à installer numpy ni un moteur de reconnaissance d'images, qui ne lui
    # servent à rien. Un protocole qui traîne les dépendances de l'un de ses
    # deux bouts est un protocole mal placé.
    from .timing import Measure, Timeline

#: Version du protocole. À incrémenter dès qu'un champ change de sens.
#: Le serveur accepte cette version et la précédente.
PROTOCOL_VERSION: Final = 1

#: Bornes de plausibilité d'une durée, en secondes.
#:
#: En deçà d'une seconde, aucune quête ne peut être acceptée puis rendue :
#: c'est une lecture double ou un envoi fabriqué. Au-delà de six heures, le
#: joueur a laissé le logiciel tourner en faisant autre chose, ce qui n'est pas
#: une durée de quête.
#:
#: Le client écarte ces mesures avant l'envoi et le serveur les refuse
#: également : le premier par honnêteté, le second parce qu'il ne peut pas
#: faire confiance au premier.
MIN_SECONDS: Final = 1.0
MAX_SECONDS: Final = 6 * 3600.0


@dataclass(frozen=True)
class MeasurePayload:
    """Une durée, dépouillée de tout ce qui n'est pas nécessaire.

    Pas de date : le serveur a besoin de savoir combien de temps a pris une
    quête, pas à quelle heure le joueur jouait. Ce qu'on n'envoie pas ne peut
    ni fuiter, ni être exigé plus tard.
    """

    quest: str
    seconds: float
    quality: str
    confidence: float

    @classmethod
    def from_measure(cls, measure: Measure) -> MeasurePayload:
        return cls(
            quest=str(measure.quest_id),
            seconds=round(measure.seconds, 2),
            quality=measure.quality.value,
            confidence=round(measure.confidence, 3),
        )

    @property
    def is_plausible(self) -> bool:
        return MIN_SECONDS <= self.seconds <= MAX_SECONDS and 0.0 <= self.confidence <= 1.0


@dataclass(frozen=True)
class SessionPayload:
    """Un lot de mesures, envoyé en fin de session.

    En fin de session et non au fil de l'eau : cela évite toute requête réseau
    pendant que le joueur joue, et permet de dédupliquer localement avant
    d'envoyer.
    """

    player: str
    language: str
    #: Date du référentiel ayant servi à identifier les quêtes, au format
    #: AAAA-MM-JJ. Le catalogue suit le jeu et non le logiciel : sans elle,
    #: une quête renommée par une mise à jour donnerait deux séries de temps
    #: sans moyen de savoir qu'il s'agit de la même.
    catalog_date: str
    measures: tuple[MeasurePayload, ...] = ()
    protocol: int = PROTOCOL_VERSION
    client: str = __version__
    dropped: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionPayload:
        measures = tuple(MeasurePayload(**m) for m in data.get("measures", []))
        known = {f for f in cls.__dataclass_fields__ if f != "measures"}
        return cls(measures=measures, **{k: v for k, v in data.items() if k in known})


@dataclass
class PlayerIdentity:
    """Identifiant anonyme, tiré au sort une fois et conservé localement.

    Sert uniquement à ne pas compter deux fois le même joueur et à écarter en
    bloc les envois d'une source aberrante. Il ne dit rien de qui joue, et rien
    ne permet de remonter du serveur vers une personne.
    """

    value: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def load_or_create(cls, path: Path) -> PlayerIdentity:
        try:
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return cls(existing)
        except OSError:
            pass
        identity = cls()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(identity.value, encoding="utf-8")
        except OSError:
            # Un identifiant qui ne peut pas être conservé reste utilisable
            # pour cette session : mieux vaut compter le joueur deux fois que
            # perdre ses mesures.
            pass
        return identity


def build_session(
    timeline: Timeline,
    player: str,
    catalog_date: str,
    language: str = "fr",
) -> SessionPayload:
    """Prépare le lot d'une session, en écartant ce qui n'est pas plausible.

    Le filtrage a lieu ici, chez le client, alors que le serveur le refera de
    son côté. Ce n'est pas une redondance inutile : le client filtre par
    honnêteté, pour ne pas polluer les médianes des autres avec ses propres
    ratés ; le serveur filtre parce qu'il ne peut faire confiance à aucun
    client, le sien compris.
    """
    payloads = [MeasurePayload.from_measure(m) for m in timeline.measures]
    kept = tuple(p for p in payloads if p.is_plausible)
    return SessionPayload(
        player=player,
        language=language,
        catalog_date=catalog_date,
        measures=kept,
        dropped=timeline.dropped + (len(payloads) - len(kept)),
    )


__all__ = [
    "MAX_SECONDS",
    "MIN_SECONDS",
    "PROTOCOL_VERSION",
    "MeasurePayload",
    "PlayerIdentity",
    "SessionPayload",
    "build_session",
]
