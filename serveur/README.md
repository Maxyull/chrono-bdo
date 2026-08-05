# Rubin, serveur de classement

Reçoit les mesures des joueurs et publie les temps médians par quête et le
débit par chaîne.

## Deux principes

**La lecture est publique et sans compte.** Un classement n'a d'intérêt que
consultable : exiger une inscription pour voir un temps médian n'ajoute aucune
sécurité et retire la moitié des lecteurs.

**Aucun client n'est cru sur parole**, y compris celui de ce dépôt. Un temps
mesuré chez un joueur est une affirmation, pas une observation, et rien
n'empêche quiconque d'en fabriquer. Deux garde-fous en découlent :

- les durées invraisemblables sont refusées à l'entrée, sous une seconde comme
  au-delà de six heures ;
- **le classement se fait sur la médiane, jamais sur le record.** Un tricheur
  s'empare d'un record en un seul envoi ; il ne déplace pas une médiane établie
  sur des centaines de mesures. Et la médiane est de toute façon le chiffre
  utile, puisqu'il s'agit de prévoir une durée et non de couronner un champion.

## Ce que le serveur ne sait pas

Il ne stocke ni pseudonyme du jeu, ni nom de famille, ni horaire de session.
Une mesure ne porte même pas de date. Un identifiant tiré au sort chez le
joueur suffit à dédupliquer et à écarter une source aberrante, sans jamais
permettre de remonter à une personne.

## Interface

| Chemin | Ce qu'il fait |
|---|---|
| `GET /sante` | état du serveur et compteurs |
| `POST /v1/sessions` | reçoit un lot de mesures |
| `GET /v1/quetes/{chaine}/{position}` | temps médian d'une quête |
| `GET /v1/chaines/{chaine}` | débit d'une chaîne |
| `GET /v1/chaines` | **les chaînes les plus rapides**, en quêtes par heure |
| `GET /v1/couverture` | combien de quêtes sont bien mesurées, et combien le sont peu |
| `GET /v1/discord/connexion` | envoie vers Discord pour rattacher un compte |
| `GET /v1/discord/retour` | reçoit le retour de Discord et rattache le compte |

`GET /v1/chaines` est la réponse à la question qui a fait naître le projet : par
où commencer quand il reste des milliers de quêtes à faire.

## La couverture ne compte que deux tranches sur trois

`GET /v1/couverture` rend le nombre de quêtes **bien mesurées**, cinq mesures ou
plus, et **peu mesurées**, de une à quatre. Ce sont les vertes et les orange de
la fenêtre, au seuil qu'elle emploie déjà.

Il ne rend **pas** les grises, les jamais mesurées, et ce n'est pas un oubli. Le
serveur ne connaît que les quêtes dont il a reçu au moins une mesure. Les 3 924
quêtes principales sont un fait du catalogue, que le client porte et que le
serveur n'a jamais vu : rien ne lui garantit d'ailleurs que tous les clients
lisent le même. La soustraction appartient donc au client, seul à connaître son
propre total. Le serveur dit ce qu'il sait, le client complète avec ce qu'il
sait.

Aucun pourcentage n'est rendu non plus. La base contient onze mesures d'un seul
joueur : la réponse honnête ressemble à « 0 bien mesurée, 11 peu mesurées », et
un pourcentage ne ferait que rendre ce chiffre moins lisible.

⚠️ **Ces tranches comptent des mesures, pas des contributeurs.** Un joueur a
jusqu'à 44 personnages et refait chaque quête sur chacun : il peut donc
légitimement mesurer 44 fois la même quête, qui passerait « bien mesurée » alors
qu'une seule main a parlé. La limite est connue et n'est pas encore corrigée.

## Le rattachement Discord, éteint par défaut

Les deux dernières adresses répondent **503** tant que `RUBIN_DISCORD_ID` et
`RUBIN_DISCORD_SECRET` sont absents, ce qui est le cas en production. C'est
l'état normal et non une panne : contribuer n'a jamais demandé de compte, et un
serveur qui refuserait de démarrer faute d'identifiants Discord couperait la
mesure de tous les joueurs pour une fonction que personne n'utilise.

⚠️ **Poser ces deux variables stocke un pseudonyme Discord, donc une donnée
personnelle.** Le README du projet et la
[politique de confidentialité](https://maxyull.fr/confidentialite.html)
promettent aujourd'hui qu'aucun pseudonyme n'est transmis. L'ordre est donc
obligatoire : **politique d'abord, variables ensuite.**

| Variable | Rôle |
|---|---|
| `RUBIN_DISCORD_ID` | identifiant de l'application, portail développeur Discord |
| `RUBIN_DISCORD_SECRET` | secret de la même application |
| `RUBIN_DISCORD_RETOUR` | URL de retour, `https://rubin.maxyull.fr/v1/discord/retour` par défaut |
| `RUBIN_DISCORD_ETAT` | clé qui signe l'état ; tirée au sort si absente, donc à figer en production |

La dernière mérite une explication. L'état signé est ce qui empêche un tiers de
rattacher **son** compte Discord au numéro d'un autre contributeur et de
s'attribuer ses mesures. Non fournie, la clé change à chaque redémarrage, et
toute connexion en cours à ce moment-là échoue sans raison visible. Le script de
déploiement en génère une et la range dans le fichier de secrets, hors de tout
dépôt git.

L'état porte sa date d'émission, elle-même signée, et n'est plus accepté au-delà
d'un quart d'heure : une adresse de retour finit dans un historique ou un
journal de mandataire, et une signature sans date y resterait valable pour
toujours.

## Lancer en développement

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]" -e ..
uvicorn rubin_serveur.main:app --reload
```

La base par défaut est SQLite en mémoire : tout disparaît à l'arrêt, ce qui est
le comportement voulu pour du développement. En production, `RUBIN_DB` pointe
vers Postgres.

## Licence

MIT, voir [../LICENSE](../LICENSE).

## Déploiement

```bash
bash serveur/deploiement/deployer.sh
```

Le script se lance depuis le poste, sous Git Bash, et fait tout le travail sur
le VPS. Il est **rejouable** : le relancer met à jour le code et redémarre le
service sans rien détruire, ce qui en fait aussi le script de mise à jour.

Il installe une base Postgres dédiée, le code dans `/opt/rubin`, un service
systemd et un bloc Caddy. Les conventions sont celles de `bdi-infra`, qui
occupe la même machine : mêmes accès, un fichier `.caddyfile` par service.

Trois choix méritent d'être connus :

- **Pas de conteneur.** Le VPS n'a que deux giga-octets de mémoire disponible,
  et le service en consomme cinquante-six méga-octets en systemd.
- **Une base séparée** plutôt qu'un schéma dans celle de BDI : les deux
  services n'ont aucune donnée commune, et sauvegarder ou restaurer l'un ne
  doit pas toucher l'autre.
- **La configuration Caddy est validée avant d'être rechargée.** Une erreur de
  syntaxe appliquée telle quelle couperait *tous* les sites du serveur.

Le script ne crée pas l'enregistrement DNS, qui vit chez le registrar. Tant
qu'il manque, Caddy ne peut obtenir aucun certificat.
