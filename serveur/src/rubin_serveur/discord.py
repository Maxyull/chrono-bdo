"""Rattacher un compte Discord à un contributeur, pour le nommer au classement.

Un classement de pseudonymes anonymes n'intéresse personne. Se connecter permet
d'y apparaître sous son nom, et rien de plus.

Quatre principes gouvernent ce module.

**Contribuer ne demande aucun compte.** La connexion est facultative et ne
change rien à ce qui est mesuré ni envoyé. Un joueur qui ne veut pas de Discord
alimente les médianes exactement comme les autres ; il n'apparaît simplement
pas nommé.

**Le lot de mesures ne porte jamais d'identité.** L'association entre
l'identifiant anonyme et le compte Discord se fait ici, une fois, et n'est
jamais renvoyée au client. Aucun envoi en circulation ne contient de nom.

**On ne demande que l'identité.** La portée `identify` donne le nom et
l'identifiant du compte, rien d'autre : ni courriel, ni serveurs fréquentés, ni
liste d'amis. Ce qu'on ne demande pas ne peut pas fuiter.

**Le jeton Discord n'est pas conservé.** Il sert à lire le nom une fois, puis
il est jeté. Garder un jeton d'accès obligerait à le protéger et à le
renouveler, pour une information qu'on a déjà.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any, Final

import requests

_AUTHORIZE: Final = "https://discord.com/oauth2/authorize"
# L'annotation est nécessaire : le vérificateur de sécurité signale toute
# constante dont le nom évoque un jeton, sans regarder sa valeur. Ici c'est
# l'adresse publique d'échange de Discord, documentée et sans aucun secret.
_TOKEN_ENDPOINT: Final = "https://discord.com/api/oauth2/token"  # noqa: S105
_IDENTITY: Final = "https://discord.com/api/users/@me"
_TIMEOUT: Final = 15

#: Seule portée demandée. Voir l'en-tête du module.
SCOPE: Final = "identify"


@dataclass(frozen=True)
class DiscordConfig:
    """Ce qu'il faut pour parler à Discord, lu dans l'environnement."""

    client_id: str
    client_secret: str
    redirect_uri: str
    #: Sert à signer l'état transmis à Discord et relu au retour. Tiré au sort
    #: au démarrage s'il n'est pas fourni : la conséquence est qu'un
    #: redémarrage pendant une connexion en cours l'invalide, ce qui est sans
    #: gravité et se corrige en recommençant.
    state_secret: str

    @classmethod
    def from_env(cls) -> DiscordConfig | None:
        """Lit la configuration, ou renvoie `None` si elle est absente.

        Absente n'est pas une erreur : le serveur doit tourner sans connexion
        Discord, et le dire clairement à qui essaie de s'en servir, plutôt que
        de refuser de démarrer.
        """
        client_id = os.environ.get("RUBIN_DISCORD_ID", "")
        client_secret = os.environ.get("RUBIN_DISCORD_SECRET", "")
        if not client_id or not client_secret:
            return None
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=os.environ.get(
                "RUBIN_DISCORD_RETOUR", "https://rubin.maxyull.fr/v1/discord/retour"
            ),
            state_secret=os.environ.get("RUBIN_DISCORD_ETAT", secrets.token_hex(32)),
        )


@dataclass(frozen=True)
class DiscordIdentity:
    """Ce que Discord accepte de dire d'un compte, et que nous gardons."""

    discord_id: str
    name: str


def sign_state(player: str, secret: str) -> str:
    """Signe l'identifiant du joueur pour le transmettre à Discord et le relire.

    Discord renvoie cet état tel quel au retour. Non signé, n'importe qui
    pourrait forger un retour rattachant **son** compte Discord au numéro
    d'un autre contributeur, et s'attribuer ses temps.

    La signature n'est pas du chiffrement : l'identifiant reste lisible dans
    l'adresse. Ce n'est pas un secret, c'est un numéro tiré au sort qui ne
    désigne personne.
    """
    signature = hmac.new(secret.encode(), player.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{player}.{signature}"


def read_state(state: str, secret: str) -> str | None:
    """Relit un état signé, ou `None` s'il a été altéré."""
    player, _, signature = state.partition(".")
    if not player or not signature:
        return None
    expected = hmac.new(secret.encode(), player.encode(), hashlib.sha256).hexdigest()[:32]
    # Comparaison à temps constant : une comparaison ordinaire s'arrête au
    # premier caractère différent, ce qui laisse mesurer la progression et
    # reconstituer une signature valide essai après essai.
    return player if hmac.compare_digest(signature, expected) else None


def authorize_url(config: DiscordConfig, player: str) -> str:
    """Adresse vers laquelle envoyer le joueur pour qu'il se connecte."""
    from urllib.parse import urlencode

    parameters = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "state": sign_state(player, config.state_secret),
        # Redemander l'accord à chaque fois plutôt que de le supposer acquis :
        # rattacher un compte est un acte volontaire, pas une formalité qu'on
        # traverse sans la voir.
        "prompt": "consent",
    }
    return f"{_AUTHORIZE}?{urlencode(parameters)}"


def exchange_code(config: DiscordConfig, code: str) -> DiscordIdentity | None:
    """Échange le code contre l'identité, sans conserver le jeton.

    Ne lève jamais : un échec de Discord ne doit pas faire tomber le serveur ni
    rendre une trace à un visiteur. On rend `None` et l'appelant le dit
    lisiblement.
    """
    try:
        token_response = requests.post(
            _TOKEN_ENDPOINT,
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=_TIMEOUT,
        )
        if token_response.status_code >= 400:
            return None
        token: str = token_response.json().get("access_token", "")
        if not token:
            return None

        identity_response = requests.get(
            _IDENTITY, headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT
        )
        if identity_response.status_code >= 400:
            return None
        body: dict[str, Any] = identity_response.json()
    except (requests.RequestException, ValueError):
        return None

    discord_id = str(body.get("id", ""))
    if not discord_id:
        return None
    # Discord a deux noms : le pseudonyme global, récent, et le nom d'usager
    # historique. On prend le premier disponible pour afficher quelque chose de
    # reconnaissable par la personne elle-même.
    name = str(body.get("global_name") or body.get("username") or discord_id)
    return DiscordIdentity(discord_id=discord_id, name=name)
