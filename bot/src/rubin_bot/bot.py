"""Le raccordement à Discord, et rien de plus.

Tout ce qui décide de quelque chose vit dans `commands` et `presentation`, qui
n'importent pas `discord`. Ce module se contente d'inscrire trois commandes et
de recopier leur réponse. C'est ce qui permet de vérifier le comportement du
robot sans jeton, sans passerelle et sans réseau.

**Aucune intention privilégiée.** Le robot est construit avec
`discord.Intents.none()` : les interactions de commandes lui parviennent sans
qu'il ait besoin de lire le contenu des messages, la liste des membres ou les
présences. Ces trois-là sont précisément les intentions privilégiées, celles
qui demandent une autorisation à Discord ; ne pas en avoir besoin est un choix,
pas un oubli.

**Aucun pouvoir d'administration.** Pas de rôle, pas de suppression de message,
pas de bannissement, pas de message envoyé de sa propre initiative. Le robot
répond quand on l'interroge, et se tait le reste du temps.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Final

import discord
from discord import app_commands

from .api import DEFAULT_MIN_SAMPLES, MAX_CHAIN, MAX_POSITION, MAX_RANKING, RubinApi
from .commands import answer_chain, answer_quest, answer_ranking

_LOG: Final = logging.getLogger("rubin_bot")

#: Nombre de chaînes affichées par défaut au classement.
DEFAULT_RANKING: Final = 10

#: Message rendu quand une commande échoue pour une raison qu'on n'avait pas
#: prévue. Le détail part dans le journal du service, jamais dans le salon :
#: une trace de pile n'apprend rien à un joueur et peut divulguer un chemin.
UNEXPECTED: Final = "Une erreur inattendue s'est produite, elle est notée dans le journal du robot."


class RubinBot(discord.Client):
    """Client Discord en lecture seule, adossé à l'API publique de Rubin."""

    def __init__(self, api: RubinApi) -> None:
        super().__init__(intents=discord.Intents.none())
        self.api = api
        self.tree = app_commands.CommandTree(self)
        register_commands(self.tree, api)

    async def setup_hook(self) -> None:
        """Publie les commandes auprès de Discord au démarrage."""
        await self.tree.sync()

    async def close(self) -> None:
        """Ferme la session HTTP avant de quitter la passerelle."""
        await self.api.aclose()
        await super().close()


async def reply(interaction: discord.Interaction, answer: str) -> None:
    """Envoie la réponse, en tenant compte du délai de trois secondes.

    Discord ferme l'interaction si rien ne lui revient en trois secondes, or un
    appel HTTP peut en prendre cinq. La réponse est donc systématiquement
    différée : le joueur voit « réfléchit... » plutôt qu'un échec.
    """
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True)
    await interaction.followup.send(answer)


async def run_answer(interaction: discord.Interaction, answer: Awaitable[str]) -> None:
    """Exécute une réponse, sans jamais laisser une exception atteindre Discord.

    Une exception non rattrapée dans un gestionnaire de commande laisse le
    joueur devant un « l'application ne répond pas » qui ne dit rien, et remplit
    le journal d'une trace qu'il ne verra jamais. Ici, l'incident est journalisé
    et une phrase lisible part dans le salon.
    """
    try:
        text = await answer
    except Exception:
        _LOG.exception("échec inattendu d'une commande")
        text = UNEXPECTED
    try:
        await reply(interaction, text)
    except discord.DiscordException:
        # L'interaction a expiré, ou le salon a disparu pendant l'appel. Rien à
        # rattraper, et surtout rien qui doive arrêter le robot.
        _LOG.warning("réponse impossible à envoyer sur une interaction")


def register_commands(tree: app_commands.CommandTree, api: RubinApi) -> None:
    """Inscrit les trois commandes de consultation, et seulement elles."""

    @tree.command(
        name="rapides",
        description="Les chaînes de quêtes les plus rapides, au rythme médian",
    )
    @app_commands.describe(nombre="Combien de chaînes afficher, 25 au maximum")
    async def rapides(
        interaction: discord.Interaction,
        nombre: app_commands.Range[int, 1, MAX_RANKING] = DEFAULT_RANKING,
    ) -> None:
        await run_answer(
            interaction,
            answer_ranking(api, limit=nombre, min_samples=DEFAULT_MIN_SAMPLES),
        )

    @tree.command(name="chaine", description="Le rythme mesuré sur une chaîne de quêtes")
    @app_commands.describe(numero="Numéro de la chaîne, par exemple 21136")
    async def chaine(
        interaction: discord.Interaction,
        numero: app_commands.Range[int, 1, MAX_CHAIN],
    ) -> None:
        await run_answer(interaction, answer_chain(api, numero))

    @tree.command(name="quete", description="Le temps médian mesuré sur une quête")
    @app_commands.describe(
        chaine="Numéro de la chaîne, par exemple 21136",
        position="Position dans la chaîne, par exemple 1",
    )
    async def quete(
        interaction: discord.Interaction,
        chaine: app_commands.Range[int, 1, MAX_CHAIN],
        position: app_commands.Range[int, 1, MAX_POSITION],
    ) -> None:
        await run_answer(interaction, answer_quest(api, chaine, position))


def build_bot(base_url: str, timeout: float) -> RubinBot:
    """Fabrique le robot et son client d'API, sans rien envoyer à Discord."""
    return RubinBot(RubinApi(base_url=base_url, timeout=timeout))
