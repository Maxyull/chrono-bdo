# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage [SemVer](https://semver.org/lang/fr/). Les règles propres au projet,
notamment les trois versions qui évoluent séparément, sont expliquées dans
[docs/versionnage.md](docs/versionnage.md).

## [Non publié]

Rien pour l'instant.

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
