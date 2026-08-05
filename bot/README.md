# Rubin, robot Discord

Répond dans Discord aux questions qu'on pose au serveur de classement : quelles
chaînes vont le plus vite, combien de temps prend une chaîne, combien de temps
prend une quête.

## Ce qu'il fait, et ce qu'il ne fait pas

Il **lit** l'API publique de https://rubin.maxyull.fr, et rien d'autre.

| | |
|---|---|
| Envoie des mesures | ❌ jamais, il n'en a même pas le moyen |
| Reçoit des mesures | ❌ jamais |
| Publie de lui-même | ❌ il répond, il ne parle pas tout seul |
| Gère des rôles, supprime, bannit | ❌ aucun pouvoir d'administration |
| Lit le contenu des messages | ❌ aucune intention privilégiée |

À ne pas confondre avec le **rattachement de compte** du serveur
(`../serveur/src/rubin_serveur/discord.py`), qui est un parcours OAuth2 servant
à afficher un pseudonyme au classement. Celui-là n'a ni jeton de robot, ni
passerelle, ni présence dans un salon. Les deux chantiers sont indépendants et
peuvent vivre l'un sans l'autre.

## Les commandes

| Commande | Ce qu'elle rend |
|---|---|
| `/rapides [nombre]` | les chaînes les plus rapides, au rythme médian |
| `/chaine <numero>` | le rythme mesuré sur une chaîne |
| `/quete <chaine> <position>` | le temps médian d'une quête |

## Les deux règles d'affichage, qui ne sont pas cosmétiques

**Aucun chiffre ne s'affiche sans ce sur quoi il repose.** Chaque temps est
suivi de son nombre de mesures, et un temps établi sur moins de cinq mesures
porte une marque. Une quête que personne n'a chronométrée s'affiche « jamais
mesurée », en toutes lettres : une colonne vide ou un zéro se lirait
« instantané » au lieu de « inconnu ».

Aujourd'hui, la base compte **onze mesures, toutes d'un seul joueur sur une
seule chaîne**. La quasi-totalité des réponses seront donc vides ou marquées, et
c'est l'état réel du projet, pas une panne du robot.

**Aucune durée totale.** Le serveur publie `measured_total_seconds`, la somme
des médianes d'une chaîne. Le robot ne lit même pas ce champ. Sur une session
réelle, le rythme médian annonçait 77 quêtes par heure là où la session en avait
produit 36 : trajets, dialogues, marché, mort. Un total bâti sur des médianes
ment du simple au double, et il ment en restant plausible et précis.

## Configuration

Tout passe par l'environnement, rien n'est versionné.

| Variable | Rôle |
|---|---|
| `RUBIN_BOT_JETON` | jeton de robot, portail développeur Discord, onglet Bot |
| `RUBIN_BOT_SERVEUR` | serveur interrogé, `https://rubin.maxyull.fr` par défaut |
| `RUBIN_BOT_DELAI` | délai d'attente des appels HTTP, 5 secondes par défaut |

Sans jeton, `python -m rubin_bot` affiche ce qui manque et rend la main avec le
code 1. Ni trace de pile, ni connexion tentée avec un jeton vide. C'est l'état
normal tant que l'application Discord n'existe pas.

⚠️ Le jeton ne se recopie **jamais** dans le dépôt, ni dans un argument de ligne
de commande, où il finirait dans l'historique du shell et dans la liste des
processus. Sur le poste, il vit dans `D:\DEV\secrets`.

## Ce qui reste à faire à la main, et qui n'est pas du code

### 1. Créer l'application sur le portail développeur

Sur https://discord.com/developers/applications :

1. **New Application**, nom « Rubin ».
2. Onglet **Bot**, puis **Reset Token** pour générer le jeton. Il ne se
   réaffiche jamais : le copier tout de suite dans `D:\DEV\secrets`.
3. Dans le même onglet, laisser les trois **Privileged Gateway Intents**
   décochés, `Presence`, `Server Members` et `Message Content`. Le robot est
   construit avec `discord.Intents.none()` : les interactions de commandes lui
   parviennent sans aucune intention. En cocher une « au cas où » demanderait
   une validation à Discord au-delà de cent serveurs, et donnerait accès à des
   données que le projet n'a aucune raison de voir.
4. Décocher **Public Bot** tant que le robot n'est pas censé être installé
   ailleurs que sur le serveur de Maxime.

### 2. Fabriquer l'URL d'invitation

Onglet **OAuth2** → **URL Generator** :

- portées : `bot` **et** `applications.commands` ;
- permissions : **aucune** suffit. Une réponse à une commande est une réponse
  d'interaction, elle ne demande pas la permission d'envoyer des messages. Si
  un jour une commande devait écrire hors interaction, il faudrait ajouter
  `Send Messages` (2048), et seulement celle-là.

L'URL a cette forme, avec l'identifiant d'application à la place des zéros :

```
https://discord.com/api/oauth2/authorize?client_id=000000000000000000&permissions=0&scope=bot%20applications.commands
```

Elle s'ouvre dans un navigateur connecté, et propose le serveur Discord où
installer le robot. Les commandes apparaissent quelques instants après le
premier démarrage, le temps que Discord les publie.

### 3. Le faire tourner en permanence

**Un robot n'est pas un serveur web.** Le serveur Rubin répond à des requêtes
qui arrivent par Caddy ; le robot, lui, maintient une connexion sortante
permanente vers la passerelle Discord. Il ne se déclenche pas, il *tourne*. Il
lui faut donc son propre service systemd, distinct de `rubin` qui existe déjà,
et **aucun bloc Caddy**, puisque rien n'entre.

Ce qu'il faudrait, décrit et non déployé :

- un dossier `/opt/rubin-bot`, un venv, `pip install -e .` ;
- un fichier d'environnement lisible du seul compte de service, `chmod 600`,
  portant `RUBIN_BOT_JETON` ;
- une unité `rubin-bot.service` avec `Restart=always` et `RestartSec=10`, la
  passerelle Discord coupant régulièrement les connexions longues ;
- ⚠️ **ne pas activer l'unité avant que le jeton ne soit posé.** Sans jeton, le
  robot rend 1, et `Restart=always` le relancerait en boucle.

Le VPS n'a que deux giga-octets : comme pour le serveur, pas de conteneur.

### 4. Avant d'afficher le moindre pseudonyme

Aucune commande n'affiche aujourd'hui de pseudonyme de joueur, et c'est
volontaire. La
[politique de confidentialité](https://maxyull.fr/confidentialite.html) promet
qu'aucun pseudonyme n'est transmis, et elle vit dans un autre dépôt, celui de
`maxyull.fr`.

L'ordre est le même que pour le rattachement de compte : **politique d'abord,
code ensuite.** Une commande qui afficherait le nom Discord d'un contributeur à
côté de son temps rendrait cette promesse fausse le jour de sa mise en ligne.

## Développer

```bash
cd bot
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check .
mypy
```

Les tests n'ont besoin ni de jeton, ni de réseau, ni de serveur Discord : ils
montent un vrai serveur HTTP local et interrogent le robot à travers lui.

## Licence

MIT, voir [../LICENSE](../LICENSE).
