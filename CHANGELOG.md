# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage [SemVer](https://semver.org/lang/fr/). Les règles propres au projet,
notamment les trois versions qui évoluent séparément, sont expliquées dans
[docs/versionnage.md](docs/versionnage.md).

## [Non publié] — sortira en 0.4.0

Le numéro est déjà posé dans le code et dans les métadonnées du binaire, parce
qu'ils doivent bouger ensemble et qu'il vaut mieux le faire une fois. **La
version n'est pas publiée pour autant** : cette section reste ouverte, et sera
datée le jour de la release.

### Ajouté

- **Les lectures ratées laissent une trace.** Une image jugée digne d'être lue
  dont aucun bandeau ne sortait était jusqu'ici abandonnée sur place, sans rien
  laisser derrière elle. Une session qui ne mesurait rien ne disait donc pas
  pourquoi, et les cinq défauts connus du projet ont tous dû être trouvés à la
  main, en jouant. L'image et les lignes lues sont désormais gardées dans
  `echecs/`, avec leur score : les lignes disent si l'analyse a refusé un texte
  pourtant bien lu, l'image dit si la lecture n'a rien vu de correct.
- **Commande `rubin echecs`**, qui compte ce qui est retenu et en fabrique une
  archive sur demande. Le bilan de fin de session annonce le nombre de bandeaux
  vus mais illisibles, ce qui distingue enfin deux pannes opposées : le jeu qui
  ne montre rien, et le logiciel qui ne sait pas lire.
- **Trois destinations d'envoi**, avec leur plafond en kilo-octets : une issue
  GitHub (25 600 Ko), catbox.moe (204 800 Ko) et pixeldrain (20 971 520 Ko).
  L'archive est bornée par celle qu'on vise, et quand elle déborde, la
  destination suivante est proposée. Fabriquer une archive que l'hébergeur
  refusera au dépôt serait un piège.

### Notes

- **Rien de tout cela ne part sur le réseau.** L'archive est écrite sur le
  disque et son chemin s'affiche ; c'est le joueur qui l'envoie, s'il le veut,
  où il veut. Un envoi automatique déciderait à sa place de partager ses images.
- Le WebP est **sans perte** malgré son coût, 20 Ko la vignette mesurés sur
  trois captures réelles. Ces images servent à rejouer la reconnaissance quand
  elle s'améliore, et une comparaison faite sur des pixels altérés par la
  compression ne prouverait rien sur la vraie capture.
- Quatre garde-fous bornent le dossier : seuls les échecs sont gardés, une image
  déjà vue n'est pas réécrite, purge à quatre-vingt-dix jours, plafond de taille.
  Le dernier échec n'est jamais effacé, même par le plafond : un dossier vide
  serait indiscernable d'une session sans aucun échec.

## [0.3.0] - 2026-08-05

### Changé

- **Le projet s'appelle désormais Rubin**, du nom du héraut de Calpheon qui
  donne les vingt-trois quêtes contre-la-montre du jeu, seul endroit où Black
  Desert mesure lui-même une durée. Le nom précédent disait ce que fait le
  logiciel sans rien dire du jeu.
- Le serveur a suivi : `rubin.maxyull.fr`, avec les mesures déjà collectées.

### Ajouté

- **Les embranchements sont repérés.** 69 quêtes principales, réparties sur 38
  chaînes, sont des branches d'un choix : le jeu propose deux quêtes et une
  seule sera faite. Une chaîne qui en contient ne sera donc jamais terminée en
  entier, et le total de ses quêtes surestime ce qu'il reste à faire. Le bilan
  de session le signale.

Rien pour l'instant.

## [0.2.0] - 2026-08-05

Le chronomètre fonctionne, mesure de vraies quêtes et publie ses résultats.

### Ajouté

- **Capture de la zone du bandeau** : la fenêtre du jeu est trouvée toute seule,
  la zone en est déduite, et une capture coûte 4 millisecondes.
- **Reconnaissance de la présence d'un bandeau** par la forme de son icône.
  Nécessaire parce que sans bandeau, la zone montre le chat du jeu, qui défile
  en permanence et déclencherait la lecture sans arrêt.
- **Lecture du bandeau** : quatre types reconnus, noms sur deux lignes recollés,
  artefacts de reconnaissance écartés.
- **Boucle de surveillance** : capture huit fois par seconde, ne lance la
  reconnaissance qu'au moment utile, et sait reconnaître qu'un bandeau en a
  remplacé un autre sans que la zone se vide.
- **Journal d'événements** : reconstruit les durées après coup et sait déduire
  une fin manquée par la position dans la chaîne.
- **Commande `chrono suivre`** : chronomètre les quêtes pendant une session.

### Corrigé

Quatre défauts trouvés en une session de jeu, dont aucun n'était visible sur
des captures fixes, et dont chacun suffisait à lui seul pour qu'aucune quête ne
soit jamais mesurée :

- **L'icône du bandeau n'est pas à une place fixe.** La barre s'adapte à la
  longueur du nom et reste ancrée à droite : l'icône se déplace sur 150 pixels.
  Elle est désormais cherchée par glissement horizontal.
- **Le seuil de présence était calé sur des captures fixes.** En jeu la
  corrélation plafonne à 0,90 et non 0,99, le décor bougeant derrière un bandeau
  semi-transparent. Abaissé de 0,80 à 0,70.
- **La reconnaissance avale des espaces.** « Ce qui s'est passé » est rendu
  « Cequi s'estpasse ». Les noms sont désormais comparés sans espaces ni
  ponctuation, ce qui ne coûte aucune ambiguïté supplémentaire.
- **Un bandeau d'objectif porte une ligne de description** que rien ne distingue
  d'une suite de nom. Les recollages sont essayés du plus long au plus court.

### Mesuré en conditions réelles

Première quête chronométrée le 5 août 2026 : `[Calpheon] Discuter avec Enrique`,
soit 21139/46, en 5 min 48 s, mesure exacte.

## [0.1.0] - 2026-08-04

Première version. Elle ne mesure encore aucun temps : elle établit ce que le
jeu contient, ce qui est la moitié du travail sans laquelle l'autre n'a aucun
sens.

### Ajouté

- **Référentiel des quêtes en français et en anglais.** 18 999 quêtes
  téléchargées depuis BDO Codex, mises en cache localement, jamais
  redistribuées. Les deux langues partagent les mêmes identifiants, donc un
  joueur du client anglais et un joueur du client français alimenteront la même
  ligne de classement sans qu'aucune traduction soit écrite à la main.
- **Reconstitution des chaînes de quêtes.** L'identifiant d'une quête est une
  paire `chaîne/position` : le regroupement par chaîne rebâtit les 349 chaînes
  de quêtes principales, dont 267 sans trou de numérotation. La chaîne 21601 en
  compte 117, ce que le journal du jeu confirme.
- **Résolution d'un nom vers un identifiant**, insensible aux accents et à la
  casse, qui **refuse de trancher** quand un nom désigne plusieurs quêtes.
- **Commande `python -m rubin`**, qui construit le référentiel et rend compte
  de son état.

### Connu

- **705 quêtes principales, soit 18 %, partagent leur nom avec une autre.**
  `[Serendia] Boss des Fogans` en désigne trois. Elles ne sont pas identifiables
  par le nom seul et attendent la levée d'ambiguïté par la chaîne en cours, qui
  viendra avec le chronomètre.
- **82 chaînes ont des trous de numérotation**, parce que des quêtes ont été
  retirées du jeu ou que la chaîne comporte un embranchement. L'ordre relatif
  des positions connues reste juste, seule la complétude n'est pas garantie.
- Le jeu annonce 19 235 quêtes, le référentiel en connaît 18 999. L'écart de 236
  n'est pas expliqué.

[Non publié]: https://github.com/Maxyull/rubin-bdo/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Maxyull/rubin-bdo/releases/tag/v0.2.0
[0.1.0]: https://github.com/Maxyull/rubin-bdo/releases/tag/v0.1.0
