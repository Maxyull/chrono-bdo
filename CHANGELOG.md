# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage [SemVer](https://semver.org/lang/fr/). Les règles propres au projet,
notamment les trois versions qui évoluent séparément, sont expliquées dans
[docs/versionnage.md](docs/versionnage.md).

## [Non publié]

## [0.6.0] - 2026-08-06

### Ajouté

- **Bouton « Envoyer le rapport ».** Dans Réglages, sous Compte Discord :
  empaquette les dernières pannes enregistrées (`echecs/erreurs.log`) et les
  envoie au serveur, qui les relaie dans un salon Discord. Le webhook Discord
  n'est jamais connu du logiciel distribué : c'est le serveur qui le détient
  et relaie, pour qu'il ne puisse jamais être extrait de l'exécutable et
  détourné pour spammer le salon. Demandé par Maxime le 06/08/2026.

### Modifié

- **« Toutes les quêtes par chaîne » suit maintenant l'ordre réel du jeu**,
  et non plus l'ordre alphabétique. Relevé en observant l'écran de Maxime
  (panneau « Principales » du journal, défilé en entier) : Balenos,
  Serendia, Calpheon, Mediah, Valencia, Kamasylvia, Drieghan, O'dyllita,
  Abyss One, Terre du matin radieux, Ulukita, Edania, dans cet ordre. 178
  des 349 chaînes tombent dans cet ordre confirmé ; les 110 restantes, sans
  région connue ou avec une région jamais vue en jeu, vont dans un nouvel
  onglet replié « Autres chaînes (position non confirmée) » plutôt que
  d'être placées au hasard.
- **« Toutes les quêtes par chaîne » passe avant « les plus rapides ».**
  Demandé par Maxime le 06/08/2026 : la liste par chaîne est déjà utile avec
  une seule mesure, le classement exige trois mesures par quête et reste
  souvent vide tant que la base est jeune. Un avertissement « en
  construction » l'accompagne maintenant, pour ne pas laisser croire à une
  fonctionnalité cassée.
- **Les chaînes de Renaissance et d'Éveil (quêtes de classe) se replient à
  part, en tête de la liste par chaîne.** Sur 349 chaînes, 61 appartiennent
  au parcours d'une classe jouable (une paire Renaissance/Éveil chacune) et
  noyaient les chaînes de scénario sous « [R » et « [É » une fois triées par
  nom. Elles restent toutes présentes, seulement regroupées sous une
  catégorie qui se déplie comme une chaîne ordinaire. Demandé par Maxime le
  06/08/2026.
- Vérifié à cette occasion que la liste ne contient déjà **que** des quêtes
  principales (`Catalog.chains` filtre sur `KIND_MAIN` depuis le début) :
  pas de séparation « Principales »/« Autres » à faire.

## [0.5.9] - 2026-08-06

### Corrigé

- **La mise à jour en un clic ne relançait pas Rubin.** Trouvé par Maxime en
  cliquant pour de vrai le 06/08/2026 : Rubin fermait Rubin lui-même 1,5 s
  après avoir lancé l'installateur, avant que le Gestionnaire de redémarrage
  de Windows ait pu l'enregistrer pour le relancer. Un programme fermé de son
  propre chef n'est plus rien à relancer pour lui : l'installateur travaillait
  bien, mais rien ne rouvrait Rubin ensuite. Rubin reste maintenant ouvert
  après avoir lancé l'installateur, et le laisse fermer et rouvrir Rubin
  lui-même (`CloseApplications=force`, `RestartApplications=yes`).

### Ajouté

- **Le numéro de version dans l'en-tête**, à côté de « RUBIN », avec la
  mise à jour disponible juste à côté quand il y en a une : « RUBIN v0.5.8 —
  mise à jour disponible : v0.5.9 ». Demandé par Maxime le 06/08/2026, pour
  le voir d'un coup d'œil sans chercher.
- **Un lien Discord**, dans la fenêtre (sous le lien de l'onglet Envois) et
  dans le README. Demandé par Maxime le 06/08/2026.
- **Des badges dans le README** : CI, dernière release, licence, versions de
  Python prises en charge, Discord.

### Corrigé (documentation)

- La référence à SignPath dans le README pointait vers `signpath.io`, alors
  que la demande de signature du 05/08/2026 a été faite auprès de la
  [SignPath Foundation](https://signpath.org/), qui offre la signature
  gratuite aux projets libres. Signalé par Maxime.

## [0.5.8] - 2026-08-06

### Ajouté

- **Un onglet Envois, qui montre les paquets réellement postés au serveur.**
  Demandé par Maxime le 06/08/2026, à la place du lien vers la politique de
  confidentialité posé la veille : montrer les paquets eux-mêmes, poids et
  contenu, plutôt qu'en décrire la teneur. Le contenu est publié **avant**
  chaque tentative d'envoi, réussie ou non : un envoi qui échoue a quand même
  tenté de partir avec ce contenu-là, c'est justement le cas où savoir ce qui
  a été tenté compte le plus. Le lien « voir ce qui est envoyé », sous le
  témoin de connexion, ouvre maintenant cet onglet au lieu d'un navigateur.

## [0.5.7] - 2026-08-06

### Ajouté

- **La vérification de mise à jour se répète toutes les cinq minutes**, tant
  que Rubin est ouvert, plus seulement au lancement et après chaque quête
  mesurée. Discuté avec Maxime le 06/08/2026 : un vrai push (connexion
  permanente au serveur) réglerait le même problème, mais ferait porter au
  serveur une connexion ouverte par joueur pour un événement aussi rare
  qu'une nouvelle version. Un sondage périodique donne le même résultat
  pratique, sans rien ajouter côté serveur.

### Modifié

- **L'adresse du serveur n'est plus écrite dans la fenêtre.** Demandé par
  Maxime le 06/08/2026 : le témoin de connexion se lit maintenant
  « serveur : connecté (37 ms) — 31 mesures reçues », avec la latence de
  `/sante` plutôt que l'URL. Un lien « voir ce qui est envoyé », juste en
  dessous, ouvre la politique de confidentialité dans le navigateur.

## [0.5.6] - 2026-08-06

### Ajouté

- **Un installateur Windows, avec mise à jour en un clic depuis la fenêtre.**
  Demandé par Maxime le 06/08/2026, après l'archive zip seule. Compilé par
  Inno Setup (`empaquetage/rubin.iss`), il s'installe **par utilisateur**,
  jamais dans Program Files : c'est ce qui permet à Rubin de se mettre à jour
  lui-même sans jamais demander les droits administrateur.

  Un bouton apparaît dans l'en-tête dès qu'une version plus récente est
  connue (`autoupdate.py`), sauf pendant une session en cours. Un clic
  télécharge l'installateur depuis GitHub Releases, **vérifie son empreinte
  SHA-256 avant d'en faire quoi que ce soit**, puis le lance en silence.
  L'installateur ferme et relance Rubin lui-même (`CloseApplications=force`,
  `RestartApplications=yes`, Gestionnaire de redémarrage de Windows).

  ⚠️ **`updates.py` avait explicitement refusé ceci** : « rien n'est remplacé
  automatiquement… il faudrait un lanceur intermédiaire ». C'est exactement
  ce que fait maintenant l'installateur : ce module-là ne se contredit pas,
  il devient ce second programme qui manquait.

  Au passage, `metadonnees.txt` (nom, version Windows de l'exécutable) est
  désormais régénéré à chaque construction depuis `rubin.__version__`, au
  lieu de rester figé à la main : il portait encore 0.4.0.

### Modifié

- **« Toutes les quêtes » se range désormais par CHAÎNE, plus par lettre du
  nom.** Revu par Maxime le 06/08/2026 : le premier jet groupait par lettre,
  ce qui n'est pas ce que montre l'onglet « Principales » du journal du jeu.
  Celui-ci liste des chaînes, chacune avec son propre décompte, du type
  « [Abyss One] Magnus : 0/104 » : c'est cette forme qui est reprise, avec
  « mesurées » plutôt que la progression du joueur, que Rubin ne connaît pas.

  Les quêtes d'une chaîne dépliée gardent l'ordre du jeu (leur position),
  jamais un tri alphabétique qui mélangerait le début et la fin d'une même
  histoire. Les 349 chaînes elles-mêmes sont triées par nom, faute d'un ordre
  de scénario dans le référentiel.

- **La fenêtre par défaut est plus grande**, 700 à 820 de haut. Signalé par
  Maxime le 06/08/2026 : même avec le défilement, elle montrait trop peu à la
  fois.

## [0.5.5] - 2026-08-06

### Ajouté

- **Une panne qui arrête la session le dit, et propose de reprendre.**
  Signalé par Maxime le 06/08/2026 : la session se désactivait parfois toute
  seule, sans qu'il sache pourquoi. `_run` attrapait déjà l'exception mais ne
  le montrait qu'une seconde, dans une étiquette vite recouverte. Deux
  correctifs liés :

  - la panne et sa trace complète sont désormais écrites dans
    `echecs/erreurs.log`, en ajout, pour survivre au message suivant ;
  - la fenêtre demande, une fois le bouton retombé sur « Je commence mes
    quêtes » : « Rubin a rencontré un problème… Faites-vous encore des
    quêtes ? ». Un « oui » relance la mesure tout de suite. Cette question ne
    se pose **jamais** pour un clic volontaire sur « Arrêter », qui ne publie
    pas le même signal que la panne.

- **Une note personnelle par quête, dans l'onglet Session.** Demandé par
  Maxime le 05/08/2026 au soir : de quoi noter le monstre à tuer, l'instance
  à faire, le choix pris à un carrefour, ou un mot ou un nombre relevé dans
  le chat du jeu, pour la prochaine fois qu'on refait cette quête, sur un
  autre personnage ou après l'avoir oublié.

  Purement locale (`notes.py`), sur le modèle du record personnel : rien
  n'est envoyé au serveur, qui n'a par conception aucune notion de note. Le
  champ ne s'active que le temps qu'une quête est en cours, et se vide entre
  deux, comme le meilleur temps connu et le record personnel juste au-dessus.

## [0.5.4] - 2026-08-05

### Corrigé

- **Console cachée au double-clic** (#83). L'exécutable ouvrait une fenêtre de
  terminal vide à côté de la fenêtre de Rubin, que rien ne justifiait sur ce
  chemin. `console=False`, avec `AttachConsole` dans `point_entree.py` pour
  que `rubin verifier`/`suivre`/`echecs` gardent leur texte quand elles sont
  lancées depuis un vrai terminal.
- **L'onglet Session défile** (#83). La légende des couleurs et la couverture,
  en bas, restaient invisibles une fois la liste des quêtes faites assez
  longue.

## [0.5.3] - 2026-08-05

### Ajouté

- **Le record personnel du joueur s'affiche pendant qu'il joue une quête**
  (#80), à côté du meilleur temps connu de tous. Relu dans ses propres
  sessions passées (`history.py`), aucune donnée envoyée au réseau pour ça.
- **Un arbre alphabétique des 3 924 quêtes principales** (#81), groupées par
  lettre, avec pour chacune si elle est déjà mesurée et son meilleur temps.
  ⚠️ Vérifié seulement par capture d'écran hors jeu, pas encore en jouant
  pour de vrai.

### Corrigé

- **L'archive n'est plus en LZMA** (#82). `ZIP_LZMA` compresse mieux, mais ni
  l'explorateur Windows ni `Expand-Archive` de PowerShell ne savent le
  décompresser : trois releases (v0.5.0 à v0.5.2) étaient illisibles par les
  outils natifs. `ZIP_DEFLATED, compresslevel=9` désormais.

## [0.5.2] - 2026-08-05

### Modifié

- **`rubin fenetre` se connecte au serveur sans qu'on le demande** (#79).
  Défaut désormais `https://rubin.maxyull.fr` pour ce sous-comman­de : le
  joueur qui double-clique ne doit taper aucune commande. `rubin suivre`
  garde son propre défaut, sans envoi.

## [0.5.1] - 2026-08-05

### Corrigé

- **Le double-clic sur l'exécutable ouvre la fenêtre** (#78). Sans
  sous-commande, il ouvrait `referentiel`, un reste de l'époque CLI : un
  double-clic sans commande tapée n'atteignait donc jamais la fenêtre.

## [0.5.0] - 2026-08-05

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

- **Le chat du jeu ne se mêle plus au nom de la quête.** C'était le défaut qui
  empêchait Rubin de mesurer quoi que ce soit : **neuf échecs sur neuf** du
  5 août 2026 étaient de ce type. La zone du bandeau recouvre le haut du chat,
  et la reconnaissance rendait les lignes des deux mélangées, dans un ordre qui
  alterne :

  ```
  0,96  Queteaccomplie                      <- le titre
  0,98  Guer                                <- du CHAT, APRÈS le titre
  0,94  [Hebdo] Echange d'arme du Voile     <- le nom
  0,97  finp                                <- du chat
  1,00  noir                                <- la SUITE du nom
  ```

  Le nom recollé devenait « Guer [Hebdo] Echange d'arme du Voile finp noir »,
  qui ne se résout en rien. Les noms étaient pourtant lus entre 0,94 et 0,97 :
  rien ne manquait à la reconnaissance, il manquait de savoir **où** chaque
  ligne avait été lue. Le moteur rendait cette information depuis toujours, et
  elle était jetée sur place.

  La correction garde les boîtes et filtre dessus. Le bandeau centre son texte
  sur un axe fixe, le chat est calé à gauche : une ligne appartient au bandeau
  si son milieu tombe dans la colonne ouverte par le titre, colonne que chaque
  ligne retenue élargit ensuite. **Aucune abscisse n'est écrite dans le code**,
  parce qu'un seuil calé sur des captures fixes est le deuxième piège du
  projet. Relevé sur les neuf vignettes : sous le titre, la barre opaque du
  bandeau hache le chat, qui ne dépasse jamais x = 33,5, quand la colonne du
  bandeau commence au plus tôt à x = 103,5.

  En cas de doute la ligne est **abandonnée**, jamais attribuée au bandeau. Le
  pire cas reste donc une mesure perdue : vérifié, un nom pollué de chat ne
  retombe sur aucune quête, ni par résolution exacte, ni par recollages, ni par
  correspondance partielle.

  ⚠️ Le type rendu par `TextReader.read` **n'a pas changé** : c'est un
  protocole employé par le panneau de suivi, le choix automatique de zone et la
  fenêtre. Les boîtes passent par un second point d'entrée, `read_boxed`, que
  seul le chemin d'une vraie session emprunte.

- **Le journal des échecs garde la boîte de chaque ligne.** Son absence a coûté
  cher : le journal du 5 août montrait bien le chat mêlé au bandeau, mais sans
  une seule coordonnée, donc sans de quoi mesurer la séparation. Il a fallu
  rejouer la reconnaissance sur les neuf vignettes pour retrouver une
  information que le logiciel jetait deux fois de suite.

- **Les zones de lecture sont retenues par taille de fenêtre.** `reglages.json`
  porte désormais un bloc `zones_par_taille`, dont les clés se lisent
  « 2560x1440 ». Une zone tracée en plein écran ne s'applique plus qu'en plein
  écran, une zone tracée en fenêtré qu'en fenêtré, et les deux cohabitent : le
  joueur qui alterne retrouve chaque fois son tracé au lieu de le refaire.

  ⚠️ **Une zone n'a de sens qu'avec la résolution où elle a été tracée.** Le
  bandeau de quête est ancré au coin bas-droit de la fenêtre du jeu, donc un
  rectangle relevé en 2560 x 1440 tombe en plein décor dès que la fenêtre fait
  1920 x 1080. Jusqu'ici Rubin gardait UN rectangle, sans clé : changer de
  résolution ou passer en fenêtré laissait une zone devenue fausse **et
  enregistrée**, donc survivant au redémarrage. C'était le seul réglage du
  projet capable de rester faux d'une session à l'autre sans que rien ne
  l'annonce.

  Rien n'est mis à l'échelle d'une résolution à l'autre. Sur une taille de
  fenêtre inconnue, on retombe sur le calcul d'origine, qui suit la fenêtre :
  une zone extrapolée serait une zone inventée, et le principe du projet vaut
  ici comme ailleurs. La propriété qui autorise à exposer ces réglages est
  préservée, et même renforcée : un réglage faux produit une mesure
  **manquante**, jamais une mesure fausse.

  **Un fichier écrit avant ce bloc se relit sans rien perdre.** Ses trois zones
  n'ont pas de résolution connue, et cela ne se devine pas. Les jeter aurait
  effacé le travail du joueur, en particulier la zone du panneau de choix, dont
  le calcul d'origine n'est qu'une **estimation** et dont son tracé est la seule
  source fiable. Les appliquer partout aurait refait le défaut qu'on corrige,
  en le rendant permanent. Elles sont donc conservées et réécrites, mais
  attendent d'être attribuées à une taille de fenêtre par `adopted_for` : un
  geste, pas une supposition.

  La table est traitée comme le reste du fichier, c'est-à-dire comme hostile :
  une taille illisible, un nom de zone inconnu ou un rectangle plat coûtent la
  zone concernée et rien d'autre, jamais le démarrage ni les zones voisines.

  C'est le premier des deux étages décrits dans `CLAUDE.md`, et il est utile
  seul. Le second, envoyer les zones au serveur pour en tirer la zone habituelle
  d'une résolution, n'est **pas** fait : c'est un envoi nouveau, il tombe sous
  la règle « rien n'est envoyé sans `--envoyer` ».

- **Une session de jeu ne peut plus être perdue.** Chaque mesure est écrite sur
  le disque **dès qu'elle existe**, dans un journal en ajout, une ligne par
  mesure. Un journal resté orphelin est relu et envoyé au démarrage suivant.

  La fermeture par la croix était déjà couverte, et vérifiée. Trois cas ne
  l'étaient pas : le processus tué, Windows qui redémarre, le logiciel qui
  plante. Une session de deux heures y disparaissait entièrement, et une partie
  ne se rejoue pas.

  ⚠️ **Le remède n'est pas d'attraper plus d'événements de fermeture.** On n'en
  attrape jamais tout, un `kill` ne se négocie pas, et chaque piège ajouté donne
  une fausse impression de sûreté, ce qui est pire que de savoir qu'on n'est pas
  couvert. Un processus tué au milieu d'une écriture ne peut abîmer que la
  dernière ligne du journal, que la relecture jette sans toucher au reste.

- **Les mesures partent après chaque quête terminée**, et non plus seulement à
  l'arrêt. Une quête finie est un événement naturel et la mesure y est complète,
  alors qu'un minuteur enverrait au milieu d'une quête un lot à rattraper : le
  temps ne dit rien sur l'état de la donnée, une quête terminée si.

  ⚠️ **Seules les mesures jamais transmises repartent**, et c'est la pièce
  centrale. Renvoyer toute la session à chaque quête ferait recevoir au serveur
  les mêmes mesures des dizaines de fois. Elles gonfleraient `samples` et
  entreraient dans les médianes, et ce serait **invisible** : rien ne distingue
  une mesure reçue deux fois de deux mesures réelles. Le curseur de ce qui est
  parti est écrit dans le journal, donc une reprise après plantage ne renvoie
  rien non plus.

  Un envoi dont on ignore le sort, faute de réponse du serveur, n'est jamais
  représenté : il a pu aboutir, et un doublon ne se rattrape jamais alors qu'une
  mesure manquante reste sur le disque. Un envoi refusé par un serveur qui a
  répondu, lui, repart plus tard : on sait qu'il n'a rien enregistré.

  L'envoi part dans un fil à part, un seul à la fois, et le fil de mesure ne
  l'attend jamais. Un serveur lent ne doit faire rater aucun bandeau.

  Au passage, une affirmation corrigée dans `protocol.py` et `upload.py` : ils
  promettaient qu'« aucune requête réseau ne part pendant que le joueur joue ».
  C'était déjà faux, `ReferenceClient` interroge le serveur à chaque quête pour
  afficher les temps des autres.

- **Un classement PAR QUÊTE, `GET /v1/quetes`, et son onglet dans la fenêtre.**
  Le serveur classait des **chaînes** et rendait **une** quête à la fois ; il
  n'existait aucun classement de quêtes. C'est pourtant la bonne unité : une
  chaîne moyenne ses quêtes rapides et ses quêtes lentes, alors qu'on choisit
  quête par quête, et c'est ce que le planificateur consommera.

  ⚠️ **`min_samples` vaut trois par défaut, et jamais un.** Un classement de
  chaînes sur peu de mesures est vague ; un classement de quêtes sur peu de
  mesures est **faux et convaincant**. Relevé en production le 05/08/2026 : la
  chaîne 21403 tenait la tête à 198,8 quêtes/heure **sur une seule mesure**. Le
  raisonnement derrière le trois : sur une mesure, la « médiane » est cette
  mesure ; sur deux, c'est leur moyenne, donc un passage chanceux tire le
  résultat de la moitié de son écart ; à partir de trois, la médiane est une
  valeur réellement observée, qu'aucune mesure isolée ne peut devenir.

  Le classement se fait sur la **médiane**, jamais sur le record : `ETAT.md`
  tranche, et l'arbitrage de Maxime sur le contraire n'est pas rendu. Chaque
  ligne porte son nombre de mesures. Quand rien n'atteint le seuil, la fenêtre
  le **dit** au lieu d'afficher un tableau vide, et c'est l'état du jour : la
  base contient vingt-et-une mesures, presque toutes uniques par quête.

  ⚠️ **Le serveur ne rend aucun nom de quête**, seulement `chaine/position` :
  les noms sont un fait du catalogue, que le client porte. La résolution se fait
  donc à l'affichage, comme la soustraction des quêtes grises.

- **Chercher une quête par son nom, dans le même onglet.** Trois lettres
  suffisent, la comparaison passe par `fold` des deux côtés : le catalogue porte
  « [Calpheon] Ce qui s'est passé jusqu'à présent » et personne ne tape cela.
  Un clic montre la médiane, le nombre de mesures et le meilleur temps connu, ou
  « jamais mesurée » en toutes lettres, jamais une colonne vide qui se lirait
  « instantané ». Quêtes principales seulement : proposer les 15 075 autres
  ferait cliquer sur des quêtes qui n'auront jamais de temps.

- **Un mode démonstration, purement d'affichage.** Pour voir le tableau rempli
  avant d'avoir assez de mesures. Il ne s'allume pas tout seul, chaque ligne
  porte **TEST** en clair, un bandeau le répète au-dessus, et il s'efface de
  lui-même dès que le vrai classement est complet.

  ⛔ **Aucune donnée fabriquée n'entre en base ni dans un lot.** La forme retenue
  est la garantie elle-même : ces lignes sont des chaînes de caractères déjà
  mises en forme, jamais des mesures, donc il n'existe à aucun instant un objet
  qui pourrait se glisser dans un envoi. « Ça disparaîtra à dix vraies entrées »
  n'aurait rien gardé : ce qui disparaît d'un affichage reste en base et
  continue de peser. Un test verrouille les trois portes.

- **Un témoin de connexion au serveur**, sous le chronomètre, visible depuis
  n'importe quel onglet. Trois états distincts, parce qu'ils appellent trois
  gestes différents : aucun serveur configuré, ce qui est un choix et non une
  panne ; configuré mais injoignable ; connecté, avec l'adresse. Un mot **et**
  une couleur, jamais la couleur seule.

  ⚠️ **Un point d'entrée manquant n'est pas une panne de connexion.** Cas réel
  du 05/08/2026 : le serveur répondait parfaitement mais rendait 404 sur
  `/v1/couverture`, faute d'avoir été redéployé. Le témoin ne regarde que
  `/sante` ; c'est à chaque compteur de dire séparément qu'il n'a pas eu sa
  réponse.

- **Le compteur de couverture distingue les quêtes hors périmètre.** À côté des
  trois tranches, sur sa propre ligne : « + 15 075 quêtes non principales, que
  Rubin ne mesure pas ». Le catalogue en connaît 18 999, dont 3 924 principales
  en 349 chaînes.

  ⚠️ **Ce nombre ne rejoint jamais le total de la couverture**, dont le
  dénominateur reste 3 924. Rubin ne mesure que les principales, et c'est
  délibéré : chronométrer une quête répétable n'a aucun sens puisqu'on la refait
  indéfiniment. Les mêler donnerait un chiffre décourageant **et** faux.

- **La fenêtre dit ce que la surveillance voit, en direct** (#63) : images
  capturées, bandeaux vus, lectures. Une session aveugle se voit désormais à
  l'écran au lieu de se déduire d'une base vide une heure plus tard.
- **Une image est gardée quand la surveillance ne voit rien pendant deux
  minutes** (#67), dans `echecs/`, même sans lecture ratée à proprement
  parler : jusque-là, une zone qui ne présentait jamais de bandeau ne
  laissait aucune trace du tout.
- **Les captures qui répètent la précédente sont comptées** (#68), pour
  distinguer une vraie panne de lecture d'un simple silence de jeu.
- **Les zones sont verrouillées pendant la mesure**, et Rubin dit pourquoi
  (#65, #66) : les modifier en cours de session pouvait égarer une zone déjà
  vérifiée sans avertissement.
- **Les lignes d'un alphabet que le client de jeu n'affiche pas sont
  écartées** (#64) : du bruit de reconnaissance sur écran localisé polluait
  parfois les noms reconstruits.
- **La table de zones par taille de fenêtre (0.5.0 ci-dessus) est enfin
  branchée** (#58 → #70). Elle existait et ses tests passaient depuis 0.5.0,
  mais rien ne l'appelait : une zone tracée à la mauvaise résolution restait
  active des heures durant sans qu'aucun signal ne le dise. C'était la cause
  racine de la panne de mesure constatée le 05/08 au matin.
- **Le nom d'une quête faite, dans le tableau de session, est cliquable** et
  mène à sa fiche dans le classement (#71).
- **Le meilleur temps connu s'affiche pendant qu'on joue une quête** (#72),
  au record et non à la médiane : ce widget-là ne classe personne, il
  informe, voir `format_current_reference`.
- **La couverture et le classement se rafraîchissent après chaque quête
  mesurée** (#73), au lieu de rester figés depuis le lancement de la fenêtre.
- **La requête au référentiel, dans `_add_measure`, est sortie du fil de
  Tk** (#74) : elle pouvait geler la fenêtre jusqu'à cinq secondes à la
  première quête inconnue d'une session.
- **La fenêtre est enfin incluse dans l'exécutable construit** (#77).
  `tkinter` était dans les `excludes` de `rubin.spec`, un retrait forcé par
  PyInstaller : la 0.4.0 publiée le 5 août ne contenait pas la fenêtre,
  malgré des tests verts, parce qu'aucun test ne construit l'exécutable.

### Corrigé

- **La fenêtre pouvait geler à la première quête inconnue mesurée dans une
  session**, jusqu'à cinq secondes.

  `_add_measure` tourne sur le fil de Tk, celui qui vide la file de messages et
  redessine la fenêtre. Elle appelait `ReferenceClient.quest(...)` en direct
  pour afficher le nombre de mesures et l'écart aux autres joueurs, un GET HTTP
  **synchrone** dès que la quête n'était pas déjà en cache, avec le même délai
  que documenté sur `_ask_server` : jusqu'à cinq secondes quand le serveur ne
  répond pas. Toutes les autres requêtes réseau de la fenêtre passaient déjà
  par un fil séparé (`_ask_server`, `_query_reference`,
  `_ask_current_reference`), celle-ci était la seule exception.

  La requête part désormais dans un fil démon, et publie la référence obtenue
  sur la file de messages : `_finish_measure` termine l'affichage sur le fil de
  Tk une fois la réponse connue, exactement comme le reste du réseau.

- **L'onglet Zones lit tout seul quand on y entre**, au lieu d'exiger un clic
  sur « Lire maintenant » pour montrer quoi que ce soit. Ouvrir un onglet devait
  suffire à voir l'état.

  ⚠️ La lecture ne pouvait pas devenir automatique telle quelle : elle coûte
  environ une seconde et demie, la reconnaissance travaillant sur 349x115 puis
  340x380, et elle tournait **sur le fil de Tk**. La rendre automatique sans la
  déporter aurait figé la fenêtre à chaque bascule d'onglet, ce qui est pire que
  le bouton. Elle part donc dans un fil, qui ne touche à aucun composant et
  passe par la file de messages, avec une seule lecture à la fois et un
  « lecture en cours… » affiché sur-le-champ. Le bouton reste : c'est le geste
  naturel quand on vient de tracer une zone.

- **La ligne d'état du nouvel onglet était présente et invisible**, trouvée en
  éprouvant la fenêtre et non en la relisant : son contenu demandait 628 pixels
  là où la fenêtre en offre 505, et Tk n'affiche simplement pas ce qui dépasse.
  C'est le message le plus important de l'onglet qui disparaissait, celui qui
  dit « aucune quête n'a encore assez de mesures pour être classée ». L'onglet
  défile désormais, et la ligne d'état est posée **avant** le tableau. Même
  défaut que les boutons invisibles de l'onglet Zones, au même endroit du
  raisonnement.

- **Les quêtes enchaînées vite sont enfin comptées.** « Ça va trop vite et
  certaines quêtes ne sont pas comptées », signalé par Maxime le 05/08/2026 :
  c'est vérifié, mesuré, et corrigé.

  La surveillance refusait de relire une image trop proche de la dernière lue,
  et cette proximité se mesurait par la **différence moyenne sur toute la zone**.
  Or la zone est surtout du décor, qui ne change pas quand la quête change : le
  seul signal utile y était noyé. Sur les vingt minutes de jeu réel enregistrées
  ce jour-là, **huit paires de bandeaux voisins sur vingt-huit** passaient sous
  le seuil de 8,0 alors que les deux bandeaux étaient bel et bien différents.

  Le cas le plus net, à deux secondes d'intervalle : « Quête accomplie /
  [Mediah] Les marchands d'Altinova II » puis « Nouvelle quête / [Mediah] Les
  marchands d'Altinova III ». **2,54 de différence.** Le second était pris pour
  le premier, le chronomètre de cette quête ne démarrait jamais, et la quête
  n'apparaissait nulle part. Ce n'était pas une mesure fausse, c'était une quête
  entière absente.

  La comparaison porte désormais sur **la barre du bandeau seule**, découpée
  d'après l'icône que la détection de présence retrouve déjà, et retient **la
  ligne qui a le plus changé** au lieu d'en faire la moyenne. Sur les mêmes
  vingt-huit paires réelles, la plus faible valeur passe de 2,15 à **6,78**,
  toutes au-dessus du nouveau seuil de 5,0.

  ⚠️ **La piste évidente était la mauvaise, et il vaut mieux l'écrire que la
  laisser reproposer** : comparer la bande du **nom** plutôt que l'image entière
  donne **0,84** sur cette paire, donc pire que ce qu'on corrigeait. Deux quêtes
  qui se suivent dans une chaîne portent souvent le même nom à un chiffre romain
  près, et c'est le **titre** qui porte alors toute la différence.

  Le même changement règle les bandeaux saisis pendant leur animation d'entrée,
  vingt et un sur cette session : leur titre sort tronqué, « Quete acc » ou
  « Nou », donc ils sont refusés, ce qui est correct, mais ils servaient ensuite
  de référence au bandeau posé qui suivait. Mesuré sur une paire réelle : 7,66
  sur la zone entière, donc sous l'ancien seuil, contre 17,31 sur la barre.

  Le sens de l'erreur est assumé : relire un bandeau déjà lu ne coûte qu'un peu
  de calcul, rater un bandeau coûte une quête. Le risque de l'autre côté, noyer
  la file de lecture, est borné et il a été mesuré lui aussi : un bandeau n'est
  présent à l'écran que 5 à 11 % du temps, donc tout relire donnerait 0,4 à 0,9
  lecture par seconde contre 1 à 3 que le moteur soutient.

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

- **Les quêtes dont le chiffre romain de fin est parti à la ligne se
  retrouvent.** `Catalog.resolve_truncated` complète un nom lu qui est le
  **début exact** d'un nom du catalogue, quand le reste manquant se réduit à un
  chiffre romain. Elle est le troisième et dernier recours de `resolve_lines`,
  après la résolution exacte et après `resolve_partial`.

  Relevé en observant vingt minutes de jeu réel : cinq échecs d'affilée sur
  « [Mediah] Les marchands d'Altinova II ». Le nom déborde de la largeur du
  bandeau, son numéro passe seul sur la deuxième ligne, et ce fragment de deux
  caractères sort à **0,515**, sous le seuil des lignes qui est à 0,75. Il est
  écarté avant d'arriver au catalogue, et le nom reconstruit devient « Les
  marchands d'Altinova », qui n'est le nom complet d'aucune quête.

  Ce n'était pas un défaut de normalisation : `fold` ramène très bien « Ⅱ »
  (U+2161) à « ii ». Et `resolve_partial` n'y pouvait rien, puisqu'elle cherche
  par la **fin** du nom, pour le cas symétrique du panneau de choix où c'est le
  préfixe de région qui saute. Ici c'est justement la fin qui manque.

  Compté sur le catalogue réel : **81 quêtes principales** finissent par un
  chiffre romain, et **76** portent un nom que le seul début ne distingue plus.
  ⚠️ Le rapport qui a lancé ce travail annonçait 74 : le vrai chiffre est 76.
  **72 des 81** se retrouvent désormais, 5 sans aucun contexte, 4 par la chaîne
  en cours, 63 par la position suivante. Vérifié sur les 3 924 quêtes
  principales : **zéro mauvaise réponse**, et aucun nom complet résolu
  autrement qu'avant.

  ⛔ Le garde-fou est ce qui rend la méthode acceptable, et il est volontairement
  étroit : **on ne complète que s'il ne reste qu'un candidat.** « Les marchands
  d'Altinova » est le début exact du I, du II et du III ; sans contexte, on
  renonce. La chaîne en cours puis la position exactement suivante départagent,
  jamais une position plus loin, exactement comme `resolve_in_chain` le fait
  déjà pour les homonymes. Un nom qui est déjà celui d'une quête ne se voit
  jamais ajouter de numéro, et un début de moins de huit caractères n'est pas
  complété du tout. Une quête non identifiée coûte une mesure ; une quête mal
  identifiée pollue une médiane pour toujours.

  Restent **9 quêtes sur 81** hors de portée : 3 dont le nom amputé est déjà
  celui d'une autre quête, 3 dont le début fait moins de huit caractères
  (« Fracas »), et 3 dont le nom amputé est lui-même ambigu.

  ⚠️ **Ce que cela ne corrige pas, et qui appartient au chemin de lecture** :
  le fragment continue d'être jeté avant la résolution, donc les quêtes
  retrouvées le sont par déduction et non par lecture. Abaisser le seuil pour
  une ligne très courte serait le remède direct, mais **un seuil n'y suffirait
  pas** : la confiance d'un bandeau est le **minimum** des scores retenus, donc
  garder une ligne à 0,515 ferait tomber le bandeau entier sous
  `MIN_READING_SCORE`, à 0,80. Il faudrait sortir les fragments très courts du
  calcul de confiance, ou baisser les deux seuils, ce qui n'est pas la même
  décision. La résolution par début de nom reste utile dans les deux cas, et le
  test le vérifie : les deux chemins tombent sur la même quête.

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
