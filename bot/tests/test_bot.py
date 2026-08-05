"""Vérifications du raccordement Discord, sans jeton et sans passerelle.

Rien ici n'ouvre de connexion : on construit le robot en mémoire et on regarde
ce qu'il déclare. C'est justement ce qu'il faut pouvoir vérifier tant que
l'application Discord n'existe pas.
"""

from __future__ import annotations

import asyncio

import discord

from rubin_bot.api import DEFAULT_BASE_URL, DEFAULT_TIMEOUT
from rubin_bot.bot import build_bot


class TestCommandes:
    def test_inscrit_les_trois_commandes_de_consultation(self) -> None:
        bot = build_bot(DEFAULT_BASE_URL, DEFAULT_TIMEOUT)
        try:
            noms = {commande.name for commande in bot.tree.get_commands()}
        finally:
            asyncio.run(bot.api.aclose())
        assert noms == {"rapides", "chaine", "quete"}

    def test_n_inscrit_rien_d_autre(self) -> None:
        """Régression : le périmètre du robot est la lecture, et rien de plus.

        Pas de gestion de rôles, pas de suppression de message, pas de
        bannissement, pas d'envoi de mesure. Une commande ajoutée sans y penser
        élargirait ce périmètre en silence ; ce test oblige à l'assumer.
        """
        bot = build_bot(DEFAULT_BASE_URL, DEFAULT_TIMEOUT)
        try:
            assert len(bot.tree.get_commands()) == 3
        finally:
            asyncio.run(bot.api.aclose())


class TestIntentions:
    def test_ne_demande_aucune_intention(self) -> None:
        bot = build_bot(DEFAULT_BASE_URL, DEFAULT_TIMEOUT)
        try:
            intentions = bot.intents
        finally:
            asyncio.run(bot.api.aclose())
        assert intentions.value == discord.Intents.none().value

    def test_ne_demande_aucune_intention_privilegiee(self) -> None:
        """Régression : les intentions privilégiées se demandent à Discord, et s'expliquent.

        Contenu des messages, liste des membres, présences : ce sont les trois
        que Discord fait valider, et au-delà de cent serveurs il faut monter un
        dossier. Un robot qui ne répond qu'à des commandes n'en a besoin
        d'aucune. En cocher une « au cas où » coûterait une démarche, et
        donnerait accès à des données que le projet n'a aucune raison de voir.
        """
        bot = build_bot(DEFAULT_BASE_URL, DEFAULT_TIMEOUT)
        try:
            intentions = bot.intents
        finally:
            asyncio.run(bot.api.aclose())
        assert not intentions.message_content
        assert not intentions.members
        assert not intentions.presences
