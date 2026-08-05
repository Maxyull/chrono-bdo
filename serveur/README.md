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

Le dernier est la réponse à la question qui a fait naître le projet : par où
commencer quand il reste des milliers de quêtes à faire.

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
