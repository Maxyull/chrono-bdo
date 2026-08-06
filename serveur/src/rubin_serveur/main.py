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
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from rubin.protocol import PROTOCOL_VERSION, SessionPayload

from .discord import DiscordConfig, authorize_url, exchange_code, read_state
from .rapport import send_report
from .storage import MIN_SAMPLES_PER_QUEST, Storage

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
    title="Rubin",
    description="Temps de quêtes de Black Desert Online, mesurés par les joueurs.",
    version="0.1.0",
)
storage = Storage(os.environ.get("RUBIN_DB", "sqlite+pysqlite:///:memory:"))


#: Dernière version publiée du logiciel, et version minimale encore acceptée.
#: Le serveur en est la source : lui seul sait quand une correction devient
#: indispensable, et lui seul est mis à jour d'un coup.
LATEST_CLIENT = os.environ.get("RUBIN_LATEST", "0.1.0")
MIN_CLIENT = os.environ.get("RUBIN_MIN_CLIENT", "0.1.0")
DOWNLOAD_URL = os.environ.get(
    "RUBIN_DOWNLOAD", "https://github.com/Maxyull/rubin-bdo/releases/latest"
)

#: Configuration du rattachement Discord, lue **une seule fois** au démarrage.
#:
#: Une lecture par requête serait plus souple, mais le secret qui signe l'état
#: est tiré au sort quand il n'est pas fourni : relu à chaque appel, il
#: changerait entre l'aller et le retour, et aucune connexion n'aboutirait
#: jamais. Une panne d'autant plus pénible qu'elle n'apparaîtrait qu'en
#: production, où le secret n'est pas posé.
#:
#: `None` est l'état normal tant que Discord n'est pas configuré, et non une
#: erreur : le serveur doit tourner sans, et le dire à qui essaie de s'en
#: servir plutôt que de refuser de démarrer.
discord_config: DiscordConfig | None = DiscordConfig.from_env()

#: Un identifiant de contributeur est un UUID rendu en hexadécimal, soit
#: trente-deux caractères. Le motif est volontairement plus strict que la
#: colonne : le point sépare les trois parties de l'état signé, et un
#: identifiant qui en contiendrait déplacerait la frontière entre le numéro et
#: sa signature. Refuser à l'entrée coûte moins cher que d'y penser partout.
PLAYER_PATTERN = re.compile(r"\A[0-9A-Za-z_-]{8,64}\Z")

#: Longueur maximale du code d'autorisation accepté au retour. Celui de Discord
#: en fait une trentaine. Au-delà de cette borne, ce n'est plus un code, c'est
#: quelqu'un qui essaie de nous faire relayer un envoi démesuré vers Discord.
MAX_DISCORD_CODE = 512

#: Largeur de la colonne qui garde le pseudonyme. Discord borne les siens à
#: trente-deux caractères, mais ce qu'il rend n'est pas de notre ressort : un
#: nom plus long ferait échouer l'écriture en base, donc le rattachement, après
#: que la personne a pourtant donné son accord.
MAX_DISCORD_NAME = 64

#: Un webhook Discord par application qui peut envoyer un rapport, chacun lu
#: une seule fois au démarrage. `None` est l'état normal tant qu'il n'est pas
#: posé : le serveur tourne sans, et le dit à qui essaie de s'en servir
#: plutôt que de refuser de démarrer — même principe que `discord_config`.
#:
#: Deux applications, deux salons : demandé par la session butin-bdo le
#: 06/08/2026 (voir COORDINATION.md), pour que les rapports de Butin
#: n'atterrissent pas dans le salon de Rubin. `REPORT_WEBHOOKS["rubin"]` est
#: le défaut de la route `rapport`, pour rester compatible avec un appelant
#: qui n'envoie pas encore de champ `app`.
REPORT_WEBHOOKS: dict[str, str | None] = {
    "rubin": os.environ.get("RUBIN_RAPPORT_WEBHOOK"),
    "butin": os.environ.get("BUTIN_RAPPORT_WEBHOOK"),
}

#: Un message Discord plafonne à 2000 caractères. Borné plus bas ici pour
#: laisser de la place à l'horodatage et au nom que la route ajoute avant
#: l'envoi (voir `rapport`).
MAX_REPORT_LENGTH = 1800


@app.get("/v1/version")
def version() -> dict[str, Any]:
    """Ce que le client doit savoir pour se tenir à jour.

    Servie sans condition et sans compte : un logiciel devenu trop ancien pour
    envoyer ses mesures doit tout de même pouvoir apprendre qu'il est trop
    ancien, sans quoi il resterait bloqué sans le savoir.
    """
    return {
        "derniere": LATEST_CLIENT,
        "minimale": MIN_CLIENT,
        "protocole": PROTOCOL_VERSION,
        "protocole_minimal": MIN_PROTOCOL,
        "telechargement": DOWNLOAD_URL,
    }


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


@app.get("/v1/quetes")
def quest_ranking(
    limit: int = 10, min_samples: int = MIN_SAMPLES_PER_QUEST
) -> dict[str, Any]:
    """Les quêtes les plus rapides, une par une, sur leur temps médian.

    C'est le déplacement de l'unité primaire demandé le 05/08/2026 : `/v1/chaines`
    classe des **chaînes**, et une chaîne moyenne ses quêtes rapides et ses
    quêtes lentes. Pour décider quoi faire, il faut le temps de **chaque** quête.

    ⚠️ **Le serveur ne rend aucun nom de quête, et ce n'est pas un oubli.** Il ne
    connaît que `chaine/position` : les noms sont un fait du catalogue, que le
    client porte et que le serveur n'a jamais vu. Les afficher ici demanderait au
    serveur d'affirmer ce qu'il ne peut pas vérifier, et rien ne lui garantit que
    tous les clients lisent le même référentiel, ni la même langue.

    ⚠️ **`min_samples` vaut trois par défaut, jamais un.** Voir
    `MIN_SAMPLES_PER_QUEST` : la base contient vingt-et-une mesures, presque
    toutes uniques par quête, donc la réponse d'aujourd'hui est une liste
    **vide**. C'est la bonne réponse : « personne n'a encore assez mesuré » est
    vrai, là où un classement sans seuil trierait le bruit et paraîtrait précis.

    Le plancher reste à un, comme pour `/v1/chaines` : qui le demande
    explicitement sait ce qu'il fait, et chaque ligne porte de toute façon son
    nombre de mesures. C'est le **défaut** qui protège, pas la borne.
    """
    limit = max(1, min(limit, 200))
    seuil = max(1, min_samples)
    return {
        "quetes": [
            asdict(s) | {"quete": s.quest} for s in storage.ranked_quests(limit, seuil)
        ],
        "min_echantillons": seuil,
    }


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


@app.get("/v1/couverture")
def coverage() -> dict[str, Any]:
    """Combien de quêtes sont bien mesurées, et combien le sont peu.

    Donne l'échelle de ce qui reste à mesurer, et rend chaque contribution
    lisible : une quête de plus qui passe d'orange à verte se voit.

    ⚠️ **Les quêtes jamais mesurées ne sont pas ici, et ce n'est pas un
    oubli.** Le serveur ne connaît que les quêtes dont il a reçu au moins une
    mesure ; le nombre de quêtes principales appartient au catalogue, que le
    client porte et que le serveur n'a jamais vu. C'est donc au client de
    soustraire ces deux tranches de son propre total pour obtenir ses grises.
    Le faire ici demanderait au serveur d'affirmer un chiffre qu'il ne peut pas
    vérifier.

    Aucun pourcentage n'est rendu non plus. La base contient aujourd'hui onze
    mesures d'un seul joueur : la réponse honnête ressemble à « 0 bien mesurée,
    11 peu mesurées », et c'est ce chiffre-là qui doit s'afficher.

    Sans condition ni compte, comme le reste de la lecture.
    """
    stats = storage.coverage()
    return asdict(stats) | {"measured_quests": stats.measured_quests}


def _discord_or_503() -> DiscordConfig:
    """La configuration Discord, ou un refus lisible si elle est absente.

    503 et non 404 : l'adresse existe, c'est le service derrière elle qui n'est
    pas gréé. Un 404 laisserait croire à une faute de frappe, et enverrait
    chercher l'erreur du mauvais côté.
    """
    if discord_config is None:
        raise HTTPException(
            503,
            "le rattachement Discord n'est pas configuré sur ce serveur : "
            "contribuer n'en a de toute façon jamais eu besoin",
        )
    return discord_config


def _clean_discord_name(name: str) -> str:
    """Rend le pseudonyme affichable, sans jamais le refuser.

    Refuser un nom exotique reviendrait à perdre un rattachement que la
    personne a explicitement demandé. On borne et on nettoie ce qui casserait
    l'affichage ou l'écriture en base, et on garde le reste tel quel.
    """
    cleaned = "".join(character for character in name if character.isprintable()).strip()
    return cleaned[:MAX_DISCORD_NAME] or "?"


@app.get("/v1/discord/connexion")
def discord_login(player: str) -> RedirectResponse:
    """Envoie le contributeur vers Discord pour qu'il rattache son compte.

    L'identifiant anonyme part signé dans le paramètre `state`, que Discord
    nous rendra tel quel : c'est la seule chose qui empêche un tiers de
    rattacher **son** compte au numéro de quelqu'un d'autre et de s'attribuer
    ses mesures.

    Ce que cela ne protège pas, et qu'il vaut mieux écrire que découvrir :
    **connaître l'identifiant d'un contributeur suffit à demander un état signé
    pour lui.** Cet identifiant ne quitte jamais la machine du joueur, sauf
    dans ses lots de mesures, que le serveur ne republie pas. Il tient donc
    lieu de mot de passe sans en être un, et c'est acceptable pour ce qu'il
    protège, un nom affiché à côté d'un temps de quête, pas pour davantage.
    """
    config = _discord_or_503()
    if not PLAYER_PATTERN.fullmatch(player):
        raise HTTPException(422, "identifiant de contributeur invalide")
    # 307 et non 302 : la méthode et le corps sont conservés, ce qui évite
    # qu'un mandataire zélé transforme la requête en chemin.
    return RedirectResponse(authorize_url(config, player), status_code=307)


@app.get("/v1/discord/retour")
def discord_callback(code: str = "", state: str = "") -> dict[str, Any]:
    """Reçoit le retour de Discord, lit le pseudonyme, et rattache le compte.

    Tout ce qui arrive ici vient de l'extérieur : rien n'oblige le visiteur à
    être passé par Discord, ni même par nous. `code` et `state` sont donc
    traités comme hostiles jusqu'à preuve du contraire, et cette preuve est la
    signature de l'état.
    """
    config = _discord_or_503()
    if not code or not state:
        raise HTTPException(400, "retour Discord incomplet")
    if len(code) > MAX_DISCORD_CODE:
        raise HTTPException(400, "code d'autorisation démesuré")

    # Un seul message pour l'état trafiqué, forgé ou périmé : distinguer les
    # trois dirait à qui essaie lequel il est en train de contourner.
    player = read_state(state, config.state_secret)
    if player is None or not PLAYER_PATTERN.fullmatch(player):
        raise HTTPException(400, "état invalide ou expiré, recommencez le rattachement")

    identity = exchange_code(config, code)
    if identity is None:
        # 502 : nous n'avons rien à nous reprocher, c'est l'échange avec
        # Discord qui n'a rien rendu. Le dire évite de faire chercher la panne
        # du côté du joueur.
        raise HTTPException(502, "Discord n'a pas confirmé ce code, recommencez")

    name = _clean_discord_name(identity.name)
    storage.link_discord(player, identity.discord_id, name)
    return {"rattache": True, "nom": name}


@app.get("/v1/discord/compte")
def discord_account(player: str) -> dict[str, Any]:
    """Dit si ce contributeur est rattaché à un compte Discord, et sous quel nom.

    Sans cette route, le rattachement réussissait sans que le logiciel puisse
    jamais l'apprendre : il ouvre le navigateur, Discord renvoie le joueur au
    serveur, le serveur enregistre, et la fenêtre reste sur « autorisez Rubin
    dans votre navigateur, puis revenez ici », indéfiniment. Constaté par
    Maxime le 06/08/2026, sur un compte pourtant bel et bien rattaché
    (`/v1/discord/retour` avait rendu `{"rattache":true,"nom":"maxyull"}`).

    Elle ne rend **que** ce que le joueur a déjà envoyé lui-même : son propre
    pseudonyme, celui qui s'affiche déjà à côté de ses temps au classement.
    Rien de plus n'est lisible ici, en particulier pas l'identifiant Discord,
    qui ne sert qu'à reconnaître un même compte d'un rattachement à l'autre.

    Même portée que `/v1/discord/connexion` : connaître l'identifiant anonyme
    d'un contributeur suffit à poser la question. C'est la même limite,
    assumée au même endroit, et elle protège la même chose, un nom affiché à
    côté d'un temps de quête.
    """
    if not PLAYER_PATTERN.fullmatch(player):
        raise HTTPException(422, "identifiant de contributeur invalide")
    nom = storage.display_name(player)
    return {"rattache": nom is not None, "nom": nom}


@app.post("/v1/rapport", status_code=202)
def rapport(payload: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    """Reçoit un rapport de bogue et le relaie dans un salon Discord.

    Le webhook Discord n'est jamais connu du client : voir l'en-tête de
    `rapport.py`. Le pseudonyme affiché est celui du rattachement Discord
    du joueur s'il en a un (voir `storage.display_name`), sinon les huit
    premiers caractères de son identifiant anonyme — assez pour distinguer
    deux rapports du même joueur, pas assez pour l'identifier.

    `app` choisit le salon : `"rubin"` par défaut, pour rester compatible
    avec un appelant qui n'envoie pas encore ce champ. `"butin"` a demandé
    ce champ le 06/08/2026 (voir COORDINATION.md) pour ne pas atterrir dans
    le salon de Rubin ; toute autre valeur retombe sur `"rubin"` plutôt que
    de rendre une erreur, un rapport égaré valant mieux qu'un rapport perdu.
    """
    application = str(payload.get("app") or "rubin")
    webhook_url = REPORT_WEBHOOKS.get(application) or REPORT_WEBHOOKS.get("rubin")
    if not webhook_url:
        raise HTTPException(503, "envoi de rapport non configuré")

    player = str(payload.get("joueur", ""))
    if not PLAYER_PATTERN.fullmatch(player):
        raise HTTPException(422, "identifiant de contributeur invalide")

    contenu = str(payload.get("contenu", "")).strip()
    if not contenu:
        raise HTTPException(422, "rapport vide")
    if len(contenu) > MAX_REPORT_LENGTH:
        raise HTTPException(
            413, f"rapport de {len(contenu)} caractères, {MAX_REPORT_LENGTH} au maximum"
        )

    nom = storage.display_name(player) or f"joueur anonyme {player[:8]}"
    horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = f"**{horodatage} — {nom}**\n{contenu}"

    # Le salon est un forum : chaque rapport y ouvre son propre fil, voir la
    # docstring de `send_report`. `application` figure dans le titre parce
    # qu'un rapport de Butin retombe dans le salon de Rubin tant que
    # `BUTIN_RAPPORT_WEBHOOK` n'est pas posé, et qu'il faut alors pouvoir le
    # reconnaître au premier coup d'œil.
    fil = f"🐛 {application} — {nom}"

    if not send_report(webhook_url, message, thread_name=fil):
        raise HTTPException(502, "Discord n'a pas confirmé l'envoi, réessayez")

    return {"envoye": True}


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
