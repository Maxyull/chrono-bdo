"""Ce que répond le robot, indépendamment de Discord.

Chaque fonction prend un client d'API et des nombres déjà typés, et rend le
texte à envoyer. Aucune n'importe `discord` : c'est ce qui permet de vérifier
toutes les réponses, y compris celles des pannes, sans jeton, sans passerelle
et sans réseau.

Aucune ne lève d'exception non plus. Une trace de pile dans un salon Discord
n'apprend rien à personne et donne l'impression que le robot est mort ; une
phrase en français dit ce qui s'est passé et ce qu'on peut faire.
"""

from __future__ import annotations

from .api import DEFAULT_MIN_SAMPLES, MAX_RANKING, InvalidQuestNumber, RubinApi, ServerUnavailable
from .presentation import (
    UNAVAILABLE,
    chain_message,
    never_measured_chain,
    never_measured_quest,
    quest_message,
    ranking_message,
)


async def answer_ranking(
    api: RubinApi,
    limit: int = MAX_RANKING,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> str:
    """Répond au classement des chaînes les plus rapides."""
    try:
        chains = await api.ranking(limit=limit, min_samples=min_samples)
    except ServerUnavailable:
        return UNAVAILABLE
    return ranking_message(chains, max(1, min_samples))


async def answer_chain(api: RubinApi, chain: int) -> str:
    """Répond au temps d'une chaîne donnée."""
    try:
        stats = await api.chain(chain)
    except InvalidQuestNumber as error:
        return f"Numéro de chaîne invalide : {error}"
    except ServerUnavailable:
        return UNAVAILABLE
    if stats is None:
        return never_measured_chain(chain)
    return chain_message(stats)


async def answer_quest(api: RubinApi, chain: int, position: int) -> str:
    """Répond au temps d'une quête donnée."""
    try:
        stats = await api.quest(chain, position)
    except InvalidQuestNumber as error:
        return f"Identifiant de quête invalide : {error}"
    except ServerUnavailable:
        return UNAVAILABLE
    if stats is None:
        return never_measured_quest(chain, position)
    return quest_message(stats)
