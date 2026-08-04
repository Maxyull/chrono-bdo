# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage [SemVer](https://semver.org/lang/fr/). Les règles propres au projet,
notamment les trois versions qui évoluent séparément, sont expliquées dans
[docs/versionnage.md](docs/versionnage.md).

## [Non publié]

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
- **Commande `python -m chrono`**, qui construit le référentiel et rend compte
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

[Non publié]: https://github.com/Maxyull/chrono-bdo/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Maxyull/chrono-bdo/releases/tag/v0.1.0
