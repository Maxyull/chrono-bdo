# Chrono

**Le chronomètre de quêtes pour Black Desert Online.**

Chrono mesure le temps que prend chaque quête principale, sans que vous ayez à
appuyer sur quoi que ce soit. Vous jouez normalement, il lit l'écran, et il vous
dit quelles chaînes de quêtes rapportent le plus de quêtes par heure.

> ⚠️ **Projet en construction.** Le référentiel des quêtes fonctionne et est
> testé. La capture d'écran, le chronométrage et le classement ne sont pas
> encore écrits. Voir [État d'avancement](#état-davancement). Il n'y a pas
> encore de version téléchargeable.

---

## Pourquoi ce projet existe

Black Desert compte environ 19 000 quêtes, dont 3 924 principales réparties en
349 chaînes. Quand on décide de les faire toutes, une question devient
importante : **par où commencer ?**

Personne n'a la réponse, parce que personne ne l'a mesurée. Les guides classent
les quêtes par récompense, jamais par temps. Or une chaîne de 117 quêtes courtes
et groupées vaut mieux que vingt quêtes isolées qui obligent à traverser la
carte entre chacune, même si les secondes par quête sont comparables.

Chrono mesure ce que personne ne mesure : le **débit**, en quêtes par heure et
par chaîne.

## Comment ça marche

Le jeu affiche un bandeau en bas à droite à chaque changement d'état de quête :

| Bandeau | Couleur | Ce qu'on en fait |
|---|---|---|
| `Nouvelle quête` | jaune | départ du chronomètre |
| `Quête accomplie` | cyan | arrêt du chronomètre |

Les deux portent le nom complet de la quête, avec sa région. Chrono surveille
cette seule zone, environ 400 × 160 pixels, et ne réveille la reconnaissance de
caractères que lorsque les pixels changent. En pratique, quelques dizaines de
lectures par heure au lieu de plusieurs milliers.

**Aucune interaction avec le jeu.** Pas de lecture mémoire, pas d'injection,
pas de surcouche, pas de touche simulée. Chrono regarde une capture d'écran,
exactement comme un logiciel d'enregistrement vidéo. C'est une limite de
conception, pas une étape à franchir plus tard.

## Ce qui rend la mesure difficile

**Les bandeaux se ratent.** Quand on enchaîne vite, un bandeau d'accomplissement
peut passer sans être vu. Chrono n'est donc pas un minuteur mais un journal
d'événements : il note ce qu'il voit, et reconstruit les durées après coup en
indiquant leur qualité.

| Ce qui a été vu | Mesure | Qualité |
|---|---|---|
| les deux bandeaux | accepté → accompli | exacte |
| départ suivant seulement | accepté → accepté suivant | déduite par la chaîne |
| trou de plusieurs positions | aucune | écartée |

La déduction est possible parce que l'identifiant d'une quête est une paire
`chaîne/position` : voir démarrer `21136/2` implique que `21136/1` vient de
s'achever.

**Un nom ne suffit pas à identifier une quête.** 705 quêtes principales, soit
18 % d'entre elles, partagent leur nom avec une autre. `[Serendia] Boss des
Fogans` désigne trois quêtes distinctes. Seule la chaîne en cours permet de
trancher, et quand elle ne suffit pas, Chrono renonce à la mesure plutôt que de
l'attribuer au hasard.

> **Rater une mesure donne un chiffre incomplet. En inventer une donne un
> chiffre faux.** Les deux erreurs ne coûtent pas la même chose, donc les
> réglages ne sont pas symétriques.

## Français et anglais

Le référentiel est chargé dans les deux langues, et les deux partagent les mêmes
identifiants. Un joueur du client français et un joueur du client anglais lisent
des textes différents, aboutissent au même identifiant et alimentent la même
ligne de classement. Aucune table de traduction n'est écrite à la main.

## État d'avancement

| Partie | État |
|---|---|
| Référentiel des quêtes, deux langues | ✅ fonctionne, testé |
| Reconstitution des chaînes | ✅ 267 chaînes sur 349 complètes |
| Capture et lecture des bandeaux | ✅ fonctionne en jeu |
| Chronométrage et journal d'événements | ✅ fonctionne en jeu |
| Suivi de quête, pour lever les ambiguïtés de noms | ⬜ à écrire |
| Envoi au serveur et classement | ⬜ à écrire |

Première mesure en conditions réelles, le 5 août 2026 :

```
5 min 48 s   [Calpheon] Discuter avec Enrique
```

Soit la quête 21139/46, quarante-sixième d'une chaîne de quatre-vingt-quinze.

Quatre défauts ont été trouvés en une seule session de jeu, et **aucun n'était
visible sur des captures fixes** : l'icône du bandeau se déplace de 150 pixels
selon la longueur du nom, la corrélation plafonne à 0,90 au lieu de 0,99 parce
que le décor bouge derrière, la reconnaissance avale des espaces, et un bandeau
d'objectif porte une ligne de description qu'on prendrait pour la suite du nom.
Chacun suffisait à lui seul pour qu'aucune quête ne soit jamais mesurée.

Voir l'état du référentiel :

```bash
python -m chrono referentiel
```

Chronométrer une session :

```bash
python -m chrono suivre
```

## Sources des données

Le catalogue des quêtes provient de [BDO Codex](https://bdocodex.com/). Ces
données appartiennent à Pearl Abyss ; Chrono les télécharge chez vous au premier
lancement et ne les redistribue pas.

Black Desert Online est une marque de Pearl Abyss. Ce projet n'est ni affilié à
Pearl Abyss, ni approuvé par eux.

## Documentation

| Fichier | Ce qu'il contient |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | ce qui a changé, version par version |
| [docs/versionnage.md](docs/versionnage.md) | les trois choses qui versionnent séparément, et pourquoi les confondre serait une erreur |
| [CONTRIBUTING.md](CONTRIBUTING.md) | langue du projet, politique de tests, ce que Chrono ne fera jamais |

## Licence

MIT, voir [LICENSE](LICENSE).

## Confidentialité

Ce logiciel n'envoie rien sans qu'on le lui demande, et ne transmet jamais de
pseudonyme, de position, de discussion, de capture d'écran ni d'horaire de jeu.
Le détail de ce qui part et de ce qui ne part pas est publié dans la
[politique de confidentialité](https://maxyull.fr/confidentialite.html).

## Politique de signature

Le code de ce projet est écrit et relu par Maxime Lacoste, seul mainteneur. Il
est publié sur [github.com/Maxyull/chrono-bdo](https://github.com/Maxyull/chrono-bdo),
sous licence MIT, sans composant propriétaire ni double licence commerciale.

Les versions publiées sont construites par `empaquetage/construire.py` à partir
de l'état du dépôt, et l'empreinte SHA-256 de chaque archive est publiée à côté
d'elle.

La signature de code est assurée par [SignPath.io](https://signpath.io/), au
moyen d'un certificat fourni par la [SignPath Foundation](https://signpath.org/),
qui l'offre gratuitement aux projets libres. **La demande est en cours** : tant
qu'elle n'a pas abouti, ce qui suit s'applique.

⚠️ **L'exécutable n'est pas encore signé.** Windows et certains antivirus
peuvent donc l'annoncer comme provenant d'un éditeur inconnu, ce qui est un
faux positif courant des programmes Python empaquetés. Deux précautions sont
prises en attendant : le programme n'est pas compressé par UPX, et il est
distribué en dossier plutôt qu'en fichier auto-extractible, deux traits que les
antivirus associent aux logiciels malveillants.

Vérifier une archive téléchargée :

```powershell
Get-FileHash chrono-windows.zip -Algorithm SHA256
```
