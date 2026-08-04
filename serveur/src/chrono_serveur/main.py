"""L'interface web du serveur de classement.

Les codes de statut sont écrits en clair plutôt que par les constantes du
cadriciel : celles-ci changent de nom au fil des versions, et un code HTTP,
lui, ne se déprécie pas.

Deux principes gouvernent les choix ci-dessous.

**La lecture est publique et sans compte.** Le classement n'a d'intérêt que
consultable : imposer une inscription pour voir un temps médian n'ajoute
aucune sécurité et retire la moitié des lecteurs.

**Aucun client n'est cru sur parole**, y compris celui de ce dépôt. Un temps
mesuré chez un joueur est une affirmation, pas une observation, et rien
n'empêche quiconque d'en fabriquer. D'où deux garde-fous : les durées
invraisemblables sont refusées à l'entrée, et le classement se fait sur la
médiane, qu'un tricheur seul ne déplace pas.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Annotated, Any

from chrono.protocol import PROTOCOL_VERSION, SessionPayload
from fastapi import Body, FastAPI, HTTPException

from .storage import Storage

#: Nombre maximal de mesures dans un lot. Une session très longue en produit
#: quelques centaines : au-delà de mille, c'est un envoi fabriqué, ou un
#: logiciel qui a mal tourné. Dans les deux cas, il ne doit pas entrer.
MAX_MEASURES_PER_SESSION = 1000

#: Le serveur accepte la version courante du protocole et la précédente. Un
#: joueur qui n'a pas mis à jour depuis un mois continue de contribuer ;
#: au-delà, son lot est refusé avec un message qui dit quoi faire, plutôt
#: qu'accepté et mal interprété. Une mesure mal interprétée entre dans les
#: médianes et n'en ressort jamais.
MIN_PROTOCOL = PROTOCOL_VERSION - 1

app = FastAPI(
    title="Chrono BDO",
    description="Temps de quêtes de Black Desert Online, mesurés par les joueurs.",
    version="0.1.0",
)
storage = Storage(os.environ.get("CHRONO_DB", "sqlite+pysqlite:///:memory:"))


@app.get("/sante")
def health() -> dict[str, Any]:
    return {"etat": "ok", "protocole": PROTOCOL_VERSION, **storage.counts()}


@app.post("/v1/sessions", status_code=201)
def submit(payload: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    """Reçoit un lot de mesures."""
    try:
        session = SessionPayload.from_dict(payload)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, f"lot illisible : {error}") from error

    if session.protocol < MIN_PROTOCOL:
        raise HTTPException(
            409,
            f"protocole {session.protocol} trop ancien, {MIN_PROTOCOL} au minimum : "
            "mettez le logiciel à jour",
        )
    if session.protocol > PROTOCOL_VERSION:
        raise HTTPException(
            409,
            f"protocole {session.protocol} inconnu de ce serveur, qui en est au "
            f"{PROTOCOL_VERSION}",
        )
    if len(session.measures) > MAX_MEASURES_PER_SESSION:
        raise HTTPException(
            413,
            f"{len(session.measures)} mesures, {MAX_MEASURES_PER_SESSION} au maximum",
        )

    # Le client filtre déjà les durées invraisemblables. On refiltre : il n'est
    # pas question de croire un client sur parole, fût-il le nôtre.
    plausible = [m for m in session.measures if m.is_plausible]
    refused = len(session.measures) - len(plausible)
    stored = storage.store(
        SessionPayload(
            player=session.player,
            language=session.language,
            catalog_date=session.catalog_date,
            measures=tuple(plausible),
            protocol=session.protocol,
            client=session.client,
            dropped=session.dropped,
        )
    )
    return {"enregistrees": stored, "refusees": refused}


@app.get("/v1/quetes/{chain}/{position}")
def quest(chain: int, position: int) -> dict[str, Any]:
    """Temps médian d'une quête."""
    stats = storage.quest_stats(chain, position)
    if stats is None:
        raise HTTPException(404, f"aucune mesure pour {chain}/{position}")
    return asdict(stats) | {"quete": stats.quest}


@app.get("/v1/chaines/{chain}")
def chain(chain: int) -> dict[str, Any]:
    """Débit d'une chaîne de quêtes."""
    stats = storage.chain_stats(chain)
    if stats is None:
        raise HTTPException(404, f"aucune mesure pour la chaîne {chain}")
    return asdict(stats)


@app.get("/v1/chaines")
def ranking(limit: int = 50, min_samples: int = 3) -> dict[str, Any]:
    """Les chaînes les plus rapides, en quêtes par heure.

    C'est la réponse à la question qui a fait naître ce projet : par où
    commencer quand il reste des milliers de quêtes à faire.
    """
    limit = max(1, min(limit, 200))
    return {
        "chaines": [asdict(s) for s in storage.ranked_chains(limit, max(1, min_samples))],
        "min_echantillons": max(1, min_samples),
    }
