# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage [SemVer](https://semver.org/lang/fr/). Les règles propres au projet,
notamment les trois versions qui évoluent séparément, sont expliquées dans
[docs/versionnage.md](docs/versionnage.md).

## [Non publié]

### Ajouté

- **Une fenêtre, `rubin fenetre`.** Trois onglets. **Session** dit où l'on en
  est et ce qui vient. **Zones** montre les deux rectangles que Rubin lit *et ce
  qu'il y lit à l'instant*. **Réglages** porte les curseurs, la langue du client
  de jeu et l'opacité.

  L'onglet des zones est celui qui manquait le plus. Trois des défauts de ce
  projet ont coûté une séance chacun, faute de pouvoir répondre à « qu'est-ce
  que tu lis, là, tout de suite ». Il y répond en une seconde et demie.

- **Les zones de lecture et les seuils sont réglables**, enregistrés dans
  `reglages.json`, en français et modifiable au bloc-notes. Ce qui autorise à
  donner ces boutons : un réglage faux produit une mesure **manquante**, jamais
  une mesure fausse. Une zone mal placée capture du décor, où l'analyse ne
  trouve aucun titre connu ; un seuil mal réglé rate des bandeaux ou en propose
  que l'analyse refuse. On perd des mesures, on n'en invente aucune.

- **Un chronomètre en direct**, dans l'en-tête de la fenêtre. Le temps qui court
  sur la quête en cours s'affiche pendant qu'elle est chronométrée, au lieu de
  n'apparaître qu'une fois la quête finie.

  Ce n'est pas qu'un confort, et c'est ce qui l'a rendu prioritaire. Aujourd'hui,
  un bandeau de DÉPART ignoré est **parfaitement silencieux** : le joueur ne
  s'aperçoit qu'une heure plus tard qu'il manque des quêtes. Le chronomètre le
  dit sur-le-champ, en restant sur « aucune quête chronométrée » alors qu'une
  quête vient d'être acceptée. Il transforme le « ça va trop vite et certaines
  quêtes ne sont pas comptées » signalé le 05/08/2026 en fait observable.

  ⚠️ C'est le temps de la quête **en cours**, jamais un total de session : un
  total serait le débit au rythme médian, qui ment du simple au double, 77
  quêtes à l'heure annoncées contre 36 réellement produites. Et l'horloge est
  celle du journal d'événements, `time.monotonic`, jamais une heure du jour.

- **Le compteur de couverture**, en bas de l'onglet Session : combien des 3 924
  quêtes principales sont bien mesurées, peu mesurées, jamais mesurées, dans les
  couleurs de la légende juste au-dessus. Il donne l'échelle de ce qui reste et
  rend chaque contribution lisible.

  ⚠️ **Le serveur ne rend pas les quêtes jamais mesurées**, et ce n'est pas un
  oubli : il ne connaît que celles dont il a reçu une mesure. Les 3 924 quêtes
  principales sont un fait du catalogue, que le client porte, donc la
  soustraction se fait de ce côté-ci. Le chiffre du jour est « 0 verte, 11
  orange, 3 913 jamais mesurées », sans pourcentage ni arrondi flatteur. Serveur
  injoignable ou absent : la ligne dit qu'elle ne sait pas, elle n'affiche pas
  trois zéros, qui se liraient « personne n'a jamais rien mesuré ».

- **La fenêtre refuse de se poser sur ce qu'elle lit.** Rubin lit une capture
  d'écran, donc une fenêtre posée sur une zone de lecture est lue à la place de
  cette zone. Elle se place d'elle-même à côté du panneau de quêtes, et prévient
  quand on l'y déplace. ⚠️ La transparence n'y change rien, c'est le mélange des
  deux qui est capturé.

  Ce n'est **pas une surcouche**. Rien n'est injecté dans le jeu, aucune
  fonction graphique n'est accrochée : c'est une fenêtre Windows ordinaire. La
  limite du projet vise l'injection, et elle tient.

  Tk, de la bibliothèque standard, **n'ajoute aucun octet** à l'exécutable, là
  où Qt en aurait ajouté cent cinquante pour cinq curseurs et une liste.


- **Un robot Discord de consultation**, dans le nouveau dossier `bot/`, avec son
  propre `pyproject.toml` et son propre environnement, sur le modèle de
  `serveur/`. Trois commandes, toutes en lecture : `/rapides` pour les chaînes
  les plus rapides, `/chaine` pour le rythme d'une chaîne, `/quete` pour le
  temps d'une quête. Il n'envoie aucune mesure, n'en reçoit aucune, ne publie
  rien de lui-même, et n'exerce aucun pouvoir d'administration sur un serveur
  Discord.

  Deux choses n'y sont jamais tues, pour les mêmes raisons que dans la liste
  des quêtes suivantes. **Chaque temps porte son nombre de mesures**, et en
  dessous de cinq il porte une marque : la base entière compte onze mesures,
  toutes d'un seul joueur sur une seule chaîne, donc presque toutes les réponses
  seront vides ou fragiles, et c'est l'état réel du projet. Une quête que
  personne n'a chronométrée s'affiche « jamais mesurée », jamais une colonne
  vide, qui se lirait « instantané ». **Aucune durée totale** n'est annoncée :
  le module qui lit l'API ne lit même pas le champ `measured_total_seconds` que
  le serveur publie, parce qu'un total bâti sur des médianes ment du simple au
  double, 77 quêtes/heure au rythme médian contre 36 réellement produites.

  ⚠️ Le robot est **écrit, vérifié, et pas démarré** : il lui faut un jeton de
  robot dans `RUBIN_BOT_JETON`, donc une application créée à la main sur le
  portail développeur Discord, ce qui n'est pas du code. Sans jeton, il dit ce
  qui manque et rend la main, sans trace de pile et sans rien envoyer à Discord.
  Contrairement au serveur web, un robot est un processus qui tourne en
  permanence : il lui faudra son propre service systemd, sans bloc Caddy
  puisque rien n'entre. Tout est décrit dans `bot/README.md`, rien n'est
  déployé.

  À ne pas confondre avec le rattachement d'un compte Discord, sorti en 0.4.0 :
  celui-là est un parcours OAuth2 dans le serveur, sans jeton de robot, sans
  passerelle et sans présence dans un salon. Les deux vivent l'un sans l'autre.

- **Un compteur de couverture côté serveur, `GET /v1/couverture`.** Il rend
  combien de quêtes sont **bien mesurées**, cinq mesures ou plus, et combien le
  sont **peu**, de une à quatre. Ce sont les seuils que la fenêtre emploie déjà
  pour ses pastilles vertes et orange. Une seule requête SQL groupe les mesures
  par quête et les répartit en tranches, sans rien rapatrier pour le compter en
  Python.

  Il ne rend **pas** les quêtes jamais mesurées, et c'est le cœur de la
  décision. Le serveur ne connaît que les quêtes dont il a reçu au moins une
  mesure ; les 3 924 quêtes principales sont un fait du catalogue, que le client
  porte et que le serveur n'a jamais vu. Il aurait été facile de lui faire
  soustraire deux nombres et d'annoncer les grises : c'eût été lui faire dire un
  chiffre qu'aucune de ses tables ne contient. Le serveur dit ce qu'il sait, le
  client complètera avec ce qu'il sait.

  Aucun pourcentage non plus. Avec onze mesures d'un seul joueur sur une seule
  chaîne, la réponse honnête ressemble à « 0 bien mesurée, 11 peu mesurées », et
  c'est ce chiffre-là qui doit se lire, sans arrondi flatteur.

  ⚠️ Limite connue, signalée et non corrigée ici : **ces tranches comptent des
  mesures, pas des contributeurs.** Un joueur a jusqu'à 44 personnages et refait
  chaque quête sur chacun, donc cinq passages d'une seule main suffisent à
  peindre une quête en vert.

  L'affichage en bas de la fenêtre viendra séparément : ce lot est le point
  d'entrée serveur, rien du client n'est touché.

- **Une troisième zone de lecture : le panneau de choix d'un carrefour.**
  `choice_region` la calcule, `Settings` la garde sous `zone_choix`, et
  l'onglet Zones la montre, la lit et la fait tracer comme les deux autres. Le
  domaine a trois surfaces lisibles ; l'application n'en connaissait que deux.

  Ce qu'elle apporte est double. Le jeu y coupe le préfixe de région,
  « [Carrefour] Du côté de Valks » là où le catalogue porte
  « [Calpheon][Carrefour] Du côté de Valks » : **76 quêtes principales** sont
  dans ce cas, et `Catalog.resolve_partial` sait déjà les rattraper, mais elle
  n'était appelée que sur les lignes du bandeau. Surtout, un carrefour est un
  choix qui **exclut** l'autre branche : ce panneau est le seul endroit connu
  qui dise laquelle a été prise, sur les **69 embranchements répartis dans 38
  chaînes** que `ETAT.md` range dans « ce qu'aucun code ne peut résoudre ».

  ⚠️ **La zone est ESTIMÉE, pas mesurée.** Aucune capture de ce panneau
  n'existe, ni dans le dépôt ni dans les échantillons de calibration. Elle dit
  donc la seule chose sûre, que le panneau est au centre de l'écran, et prend
  la moitié de la fenêtre autour. Elle est à vérifier en jeu, et c'est écrit à
  tous les endroits où elle se lit : dans sa docstring, dans le rôle affiché
  sous son titre, et dans son entrée d'aide, **rendue sans image** parce que
  les deux autres montrent de vraies captures et qu'un dessin propre ferait
  viser une cible qui n'existe pas.

  Elle est sans danger malgré cela, et pour la raison habituelle : une zone
  mal placée capture du décor, du décor ne produit aucune correspondance
  unique de huit caractères, donc le résultat est une **absence**
  d'identification, jamais une identification erronée. C'est vérifié sur du
  vrai texte de dialogue relevé au centre d'une capture du jeu.

## [0.4.0] - 2026-08-05

La première version qu'on peut mettre entre les mains d'un testeur : elle ne
peut plus se tromper de fenêtre, ni échouer en silence, ni laisser quelqu'un
devant un « aucune quête mesurée » sans explication.

### Ajouté

- **La liste des quêtes suivantes.** Après chaque mesure, les quêtes qui
  viennent dans la chaîne s'affichent avec leur temps de référence et le nombre
  de mesures derrière. C'est la question qu'on se pose en jouant, et à laquelle
  le bilan de fin de session répondait trop tard pour décider quoi que ce soit.
  Réglable par `--suivantes N`, `0` pour supprimer l'affichage.

  Trois choses n'y sont jamais tues, parce que les taire donnerait une liste
  qu'on ne peut pas suivre : une quête jamais mesurée le dit au lieu de laisser
  une colonne vide, qui se lirait comme « instantané » ; un trou de numérotation
  est annoncé, 82 chaînes sur 349 en portant et le référentiel connaissant
  18 999 quêtes quand le jeu en compte 19 235 ; une branche d'un choix est
  marquée, 69 quêtes principales sur 38 chaînes étant des embranchements.

  La liste ne prévoit **pas** de durée totale. La somme des médianes ment d'un
  facteur deux, 77 quêtes/heure au rythme médian contre 36 réellement produites.

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
- **Le rattachement Discord est enfin branché.** Le module qui le fait existait
  depuis deux versions, avec ses tests, mais aucune adresse ne l'appelait :
  `/v1/discord/retour` rendait 404 en production. Un module complet et
  documenté ressemble à s'y méprendre à une fonctionnalité prête, et l'état du
  projet l'annonçait comme telle. Deux adresses le relient désormais à
  l'application : `GET /v1/discord/connexion`, qui envoie vers Discord avec
  l'identifiant anonyme signé dans le paramètre `state`, et
  `GET /v1/discord/retour`, qui échange le code, lit le pseudonyme et rattache
  le compte.

  **Il reste éteint**, et c'est voulu. Sans `RUBIN_DISCORD_ID` ni
  `RUBIN_DISCORD_SECRET`, les deux adresses répondent 503 en disant pourquoi,
  et le reste du serveur n'en sait rien : contribuer n'a jamais demandé de
  compte. ⚠️ Les poser stockerait un pseudonyme Discord, donc une donnée
  personnelle, que la politique de confidentialité promet aujourd'hui de ne pas
  transmettre. Politique d'abord, variables ensuite.

  L'état signé porte désormais sa **date d'émission**, elle-même signée, et
  n'est plus accepté au-delà d'un quart d'heure. Sans elle, un état ramassé
  dans un historique de navigation ou un journal de mandataire restait valable
  indéfiniment, et le rejouer permettait de rattacher **son** compte Discord au
  numéro d'un autre contributeur, donc de s'attribuer ses mesures. La date ne
  supprime pas la fuite, elle en ferme la fenêtre.

### Corrigé

- 🔴 **Le navigateur était pris pour le jeu.** `find_game_window` retenait la
  première fenêtre visible dont le **titre** contient « black desert », et
  s'arrêtait là. Chrome affichant une vidéo « RETOUR SUR BLACK DESERT ! ... -
  YouTube » gagnait donc contre le jeu qui tournait à côté.

  La conséquence était la pire possible : `rubin verifier` répondait « fenêtre
  du jeu... 2560x1392 » puis « tout est en ordre » en pointant un navigateur, et
  la session qui suivait ne mesurait jamais rien sans dire pourquoi. Un joueur
  de Black Desert qui regarde une vidéo de Black Desert n'est pas un cas tordu.

  C'est désormais le **programme propriétaire** de la fenêtre qui tranche, lu
  par le système, et jamais le titre. Une fenêtre dont on a su lire le programme
  et qui n'est pas le jeu est écartée quel que soit son titre ; une fenêtre dont
  le programme est illisible, ce qui arrive quand le client tourne avec plus de
  privilèges que Rubin, reste un candidat de dernier recours. `rubin verifier`
  liste ce qu'il a retenu et ce qu'il a écarté : une vérification qui ne dit pas
  sur quoi elle a porté ne vérifie rien.

- **Le panneau de suivi annonçait la mauvaise chaîne.** Il retenait toutes les
  quêtes reconnues, puis prenait la chaîne la plus représentée. Or ce sont les
  quêtes de métier que le joueur épingle, et il en garde plusieurs. Sur un
  panneau réel, « Tissu haut de gamme » (type 5) et « Vie citadine » (type 2)
  mettaient en minorité la seule quête principale présente : le panneau annonçait
  la chaîne 3500 là où le joueur était dans la 21139.

  Seules les quêtes principales sont désormais retenues, seul périmètre que le
  produit mesure, et le panneau se tait quand il n'en reconnaît aucune.

- **La liste des quêtes à venir n'apparaissait qu'à la deuxième quête.** Elle
  était branchée sur « une mesure vient de se clore ». Or la première quête
  acceptée d'une session n'en clôt aucune, faute de quête précédente à borner.
  Elle suit désormais la **position**, ce qui l'affiche aussi quand on démarre
  le logiciel au milieu d'une chaîne déjà entamée, cas le plus courant.

- **Un pictogramme pouvait interrompre une session.** Les symboles hors ASCII
  employés dans les messages, comme « ⚠ », n'existent pas dans la page de codes
  cp1252 de la console Windows. Leur affichage lève une erreur d'encodage quand
  la sortie n'a pas pu être basculée en UTF-8, et même quand elle l'a été, la
  plupart des polices de console les rendent en carré vide. Tous les marqueurs
  des sorties sont passés en texte simple.

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
