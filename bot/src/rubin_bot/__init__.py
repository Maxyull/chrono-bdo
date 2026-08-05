"""Robot Discord de consultation des temps de quêtes de Rubin.

Il ne fait que **lire** l'API publique de https://rubin.maxyull.fr et répondre
à qui l'interroge. Il n'envoie aucune mesure, ne reçoit aucune mesure, ne
publie rien de lui-même, et n'exerce aucun pouvoir d'administration sur un
serveur Discord.

À ne pas confondre avec le rattachement de compte du serveur
(`serveur/src/rubin_serveur/discord.py`), qui est un parcours OAuth2 sans
jeton de robot, sans passerelle et sans présence dans un salon.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
