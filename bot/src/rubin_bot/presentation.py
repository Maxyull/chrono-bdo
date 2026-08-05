"""Mise en forme des réponses envoyées dans Discord.

Rien ici n'appelle le réseau : ce sont des fonctions pures, ce qui les rend
vérifiables une par une, y compris les cas dégradés qu'on ne saurait pas
provoquer sur le vrai serveur.

Deux règles, et elles ne sont pas cosmétiques.

**Aucun chiffre ne s'affiche sans ce sur quoi il repose.** Chaque temps est
suivi de son nombre de mesures, et une quête jamais mesurée le dit en toutes
lettres. Une colonne vide ou un zéro se lirait « instantané » au lieu de
« inconnu », ce qui est exactement la différence entre un chiffre incomplet et
un chiffre faux.

**Aucune durée totale.** Le module `api` ne lit même pas le champ que le
serveur publie pour cela ; ici, on n'additionne rien non plus. Une somme de
médianes annonce le double de ce qu'une session produit réellement.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from .api import ChainTime, QuestTime

#: En deçà de ce nombre de mesures, un temps est signalé comme fragile. Cinq
#: est le seuil retenu dans `docs/ou-va-le-projet.md` pour qu'une médiane soit
#: crédible. Aujourd'hui, la base entière compte onze mesures : presque tout
#: sera donc marqué, et c'est la vérité de l'état du projet.
FRAGILE_SAMPLES: Final = 5

MARK: Final = "⚠️"

FRAGILE_NOTE: Final = (
    f"{MARK} moins de {FRAGILE_SAMPLES} mesures : un ordre de grandeur, pas une référence."
)

#: Le serveur compte des mesures, pas des joueurs distincts. Tant que ce sera
#: le cas, aucun message ne doit parler de joueurs : dix mesures d'une même
#: personne ne valent pas dix avis.
SAMPLES_NOTE: Final = "Le compte porte sur des mesures, pas sur des joueurs distincts."

NO_TOTAL_NOTE: Final = (
    "Pas de durée totale : additionner des médianes annonce environ le double du "
    "temps qu'une vraie session demande."
)

UNAVAILABLE: Final = (
    "Le serveur Rubin n'a pas répondu, panne ou délai dépassé. "
    "Réessayez dans un moment ; rien n'est perdu, le robot ne fait que lire."
)


def format_duration(seconds: float) -> str:
    """Une durée en toutes lettres, dans la forme employée par le client."""
    minutes, rest = divmod(int(seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min {rest:02d} s" if minutes else f"{rest} s"


def format_number(value: float, decimals: int = 1) -> str:
    """Un nombre décimal à la française, virgule comprise."""
    return f"{value:.{decimals}f}".replace(".", ",")


def format_samples(samples: int) -> str:
    """« 1 mesure », « 11 mesures ». Jamais un nombre nu."""
    return f"{samples} mesure" if samples <= 1 else f"{samples} mesures"


def is_fragile(samples: int) -> bool:
    return samples < FRAGILE_SAMPLES


def _mark(samples: int) -> str:
    return f" {MARK}" if is_fragile(samples) else ""


def never_measured_quest(chain: int, position: int) -> str:
    """Ce que dit le robot quand le serveur rend 404 sur une quête."""
    return (
        f"**Quête {chain}/{position}** : jamais mesurée.\n"
        "Personne ne l'a encore chronométrée, ce n'est pas un temps de zéro."
    )


def never_measured_chain(chain: int) -> str:
    """Ce que dit le robot quand le serveur rend 404 sur une chaîne."""
    return (
        f"**Chaîne {chain}** : jamais mesurée.\n"
        "Aucune de ses quêtes n'a encore été chronométrée."
    )


def quest_message(quest: QuestTime) -> str:
    """Le temps d'une quête, avec ce sur quoi il repose."""
    lines = [
        f"**Quête {quest.chain}/{quest.position}**",
        f"Médiane **{format_duration(quest.median_seconds)}**, "
        f"sur {format_samples(quest.samples)}{_mark(quest.samples)}",
        f"Meilleur temps {format_duration(quest.fastest_seconds)}",
        "",
        SAMPLES_NOTE,
    ]
    if is_fragile(quest.samples):
        lines.append(FRAGILE_NOTE)
    return "\n".join(lines)


def chain_message(chain: ChainTime) -> str:
    """Le débit d'une chaîne, sans jamais promettre une durée totale."""
    lines = [
        f"**Chaîne {chain.chain}**",
        f"Rythme médian **{format_number(chain.quests_per_hour)} quêtes par heure**, "
        f"soit {format_duration(chain.median_seconds)} par quête",
        f"{chain.measured_quests} quête"
        f"{'s' if chain.measured_quests > 1 else ''} mesurée"
        f"{'s' if chain.measured_quests > 1 else ''}, "
        f"{format_samples(chain.samples)}{_mark(chain.samples)}",
        "",
        NO_TOTAL_NOTE,
        SAMPLES_NOTE,
    ]
    if is_fragile(chain.samples):
        lines.append(FRAGILE_NOTE)
    return "\n".join(lines)


def empty_ranking(min_samples: int) -> str:
    """Le classement vide, qui est l'état normal du projet aujourd'hui."""
    return (
        f"**Chaînes les plus rapides**\n"
        f"Aucune chaîne n'atteint {format_samples(min_samples)}.\n"
        "La base est encore trop maigre pour qu'un classement veuille dire quelque chose."
    )


def ranking_message(chains: Sequence[ChainTime], min_samples: int) -> str:
    """Le classement des chaînes les plus rapides, au rythme médian.

    Chaque ligne porte son nombre de mesures. Un classement sans cette colonne
    laisserait croire que la première ligne est la plus rapide, alors qu'elle
    est seulement la seule à avoir été mesurée.
    """
    if not chains:
        return empty_ranking(min_samples)
    lines = [
        "**Chaînes les plus rapides**, au rythme médian",
        "",
    ]
    for rank, chain in enumerate(chains, start=1):
        lines.append(
            f"`{rank:>2}.` **{chain.chain}** — "
            f"{format_number(chain.quests_per_hour)} q/h, "
            f"{chain.measured_quests} quête{'s' if chain.measured_quests > 1 else ''} mesurée"
            f"{'s' if chain.measured_quests > 1 else ''}, "
            f"{format_samples(chain.samples)}{_mark(chain.samples)}"
        )
    lines += [
        "",
        f"Chaînes retenues à partir de {format_samples(min_samples)}.",
        NO_TOTAL_NOTE,
        SAMPLES_NOTE,
    ]
    if any(is_fragile(chain.samples) for chain in chains):
        lines.append(FRAGILE_NOTE)
    return "\n".join(lines)
