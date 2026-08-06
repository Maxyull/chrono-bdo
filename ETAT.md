# État du projet, au 5-6 août 2026 (v0.5.4 publiée)

**À lire en entier avant de coder.** Ce fichier dit où en est Rubin, ce qui a
été appris en conditions réelles, et ce qui reste. Les pièges consignés plus
bas ont chacun coûté une session à découvrir : aucun n'était visible autrement
qu'en jouant.

---

## Ce qui fonctionne

Le logiciel mesure de vraies quêtes sur un vrai écran, les envoie, et affiche
les temps de référence des autres. La chaîne complète tient debout.

| Partie | État |
|---|---|
| Référentiel, 18 999 quêtes FR + EN | ✅ |
| Reconstitution des 349 chaînes principales | ✅ |
| Capture, détection et lecture du bandeau | ✅ vérifié en jeu |
| Chronométrage et déduction des fins manquées | ✅ vérifié en jeu |
| Identification des quêtes | ✅ **100 %** |
| Panneau de suivi de quête | ✅ |
| Liste des quêtes suivantes | ✅ trous et branches signalés |
| Serveur, classement, envoi | ✅ **en ligne** |
| Exécutable Windows | ✅ **v0.5.4 publiée**, la fenêtre est dedans, double-clic suffit |
| Vérification de version | ✅ le serveur annonce **0.5.4** (corrigé le 05/08/2026 au soir, voir plus bas) |
| Rétention des lectures ratées | ✅ local, envoi manuel, **et image gardée à l'aveugle après deux minutes de silence** |
| Interface graphique | ✅ 3 onglets, zones réglables, meilleur temps personnel, liste alphabétique, note de quête |
| Rattachement Discord | ✅ en ligne, identifiants posés le 06/08/2026 |
| Robot Discord de consultation | ✅ déployé le 06/08/2026, `rubin-bot.service` |

## En ligne

| | |
|---|---|
| Serveur | **https://rubin.maxyull.fr** |
| Dépôt | https://github.com/Maxyull/rubin-bdo |
| Release | **v0.5.4**, https://github.com/Maxyull/rubin-bdo/releases |
| Confidentialité | https://maxyull.fr/confidentialite.html |

Le serveur tourne en systemd sur le VPS OVH, dans `/opt/rubin`, base Postgres
dédiée, derrière Caddy. Redéploiement et mise à jour :
`bash serveur/deploiement/deployer.sh`, rejouable sans rien détruire.

✅ **Corrigé le 05/08/2026 au soir.** `deployer.sh` dérive `RUBIN_LATEST` de
`rubin.__version__`, mais ce numéro n'avait pas bougé depuis des mois malgré
cinq tags git (v0.5.0 à v0.5.4) : la variable annonçait donc toujours 0.4.0.
`__version__` et `pyproject.toml` corrigés à 0.5.4, puis redéployé ; vérifié
en direct, `GET /v1/version` répond désormais `0.5.4`.

⚠️ **Résidu qu'un redéploiement ne peut pas corriger** : l'exécutable v0.5.4
déjà téléchargé par un joueur garde `__version__="0.4.0"` figé dedans, donc
son propre contrôle de version (`updates.py`) le dira « en retard » alors
qu'il a la dernière version. Seule une v0.5.5 reconstruite avec le numéro
corrigé règle ça pour de bon.

---

## Les huit pièges découverts en jouant

**Aucun n'était visible sur des captures d'écran fixes**, et chacun suffisait
à lui seul pour qu'aucune quête ne soit jamais mesurée. C'est la leçon
principale du projet : un jeu de test figé valide la lecture d'une image, pas
le comportement d'une interface vivante.

Les trois derniers, trouvés le 5 août, ne se voyaient même pas sur une capture
du jeu : il fallait que **d'autres programmes tournent à côté**, l'un d'eux
posé **par-dessus** la fenêtre, et que le joueur ait épinglé ses propres quêtes
de métier. Un poste de développement propre ne les aurait jamais montrés.

### 1. L'icône du bandeau se déplace

La barre s'adapte à la longueur du nom et reste ancrée à droite : son icône
bouge de **150 pixels** d'une quête à l'autre. Elle est cherchée par glissement
horizontal, jamais à une position fixe. La hauteur, elle, ne bouge pas.

### 2. Le seuil de reconnaissance plafonne à 0,90 en jeu

Sur captures fixes il vaut 0,99, mais le bandeau est semi-transparent et le
décor bouge derrière. Un seuil calé sur les captures aurait raté la moitié des
bandeaux **même bien placé**. Il est à 0,70.

### 3. La reconnaissance avale les espaces

« Ce qui s'est passé » est rendu « Cequi s'estpasse ». Aucun traitement des
accents ne rattrape un mot recollé au suivant. Les noms sont donc comparés sans
espaces **ni ponctuation du tout**, des deux côtés. Coût mesuré : zéro
ambiguïté supplémentaire.

### 4. Un bandeau d'objectif porte une ligne de trop

Après le nom vient la description de l'objectif, que rien ne distingue d'une
suite de nom puisque les noms longs passent aussi à la ligne. Les recollages
sont essayés du plus long au plus court.

### 5. Le panneau de choix coupe le préfixe de région

L'écran affiche « [Carrefour] Du côté de Valks » là où le catalogue porte
« [Calpheon][Carrefour] Du côté de Valks ». 76 quêtes principales sont dans ce
cas, retrouvées par la fin de leur nom.

### 6. Le titre de la fenêtre ne désigne pas le jeu

Trouvé le 5 août 2026, et c'est le plus coûteux de tous parce qu'il annulait
tout le reste.

`find_game_window` cherchait une fenêtre visible dont le **titre** contient
« black desert », et prenait la première. Or Chrome jouait une vidéo intitulée
« RETOUR SUR BLACK DESERT ! ... - YouTube ». La recherche rendait donc la
fenêtre du navigateur, pendant que le jeu tournait à côté.

Conséquence : `rubin verifier` répondait **« fenêtre du jeu... 2560x1392 »**
puis **« tout est en ordre »**, en pointant Chrome. La session qui suivait
capturait un coin de navigateur et ne mesurait jamais rien, sans dire pourquoi.

Un joueur de Black Desert qui regarde une vidéo de Black Desert n'est pas un
cas tordu, c'est le cas courant. C'est désormais le **programme propriétaire**
de la fenêtre qui tranche, jamais le titre, et `verifier` liste ce qu'il a
retenu et ce qu'il a écarté.

### 7. Le panneau de suivi ne dit pas quelle quête est en cours

L'intuition est pourtant juste : la quête active y porte un bandeau vert, sous
la minimap, affiché en permanence. Deux mesures en jeu la démentent.

**Le bandeau vert rend son propre texte illisible.** Sur un panneau où le
joueur suivait « [Calpheon] En avançant » (21139/113), la reconnaissance n'a pas
lu ce nom **du tout** : sur sept lignes rendues, la quête active était absente.
La capture est en niveaux de gris, et le vert du bandeau y a exactement la même
luminance que les lettres. C'est précisément la ligne qu'on veut lire qui
disparaît.

**Les quêtes de métier épinglées volent la chaîne.** Sur les lignes qui se
lisent, ce sont les quêtes de récolte et d'artisanat que le joueur garde
épinglées. Sur un panneau réel, « Tissu haut de gamme » (type 5) et « Vie
citadine » (type 2) mettaient en minorité, à deux voix contre une, la seule
quête principale présente. Le panneau annonçait la chaîne 3500 là où le joueur
était dans la 21139.

Le panneau est donc restreint aux **quêtes principales**, seul périmètre
mesuré, et se tait quand il n'en reconnaît aucune. Le silence coûte une
information manquante ; une chaîne inventée coûte une liste de quêtes entière
qui pointe ailleurs, et que le joueur croira.

Piste non explorée, notée pour ne pas la redécouvrir : **capturer cette zone en
couleur** rendrait le bandeau vert trivial à isoler, et donnerait du même coup
l'ancrage qui manque pour savoir laquelle des lignes est l'active. Le gris jette
exactement le signal qui identifie la quête en cours.

### 8. Une fenêtre posée sur le jeu est capturée à sa place

`mss` capture **l'écran**, pas le tampon de rendu de la fenêtre. Tout ce qui est
affiché au-dessus du jeu est donc capturé à sa place, et le logiciel lit un
navigateur en croyant lire une quête.

Mesuré : la fenêtre du jeu était bien trouvée, 2560x1440 en (−1280,−17), mais
Chrome en occupait la moitié gauche. La zone du panneau de suivi tombait dessus,
et l'excès de vert du bandeau y valait 0,6 au lieu de plusieurs dizaines.

Ce n'est pas un défaut à corriger, c'est une **limite de la méthode**, et elle a
une conséquence directe sur l'usage : on ne bascule pas sur un navigateur
pendant que Rubin mesure. Elle est écrite dans le README, au même endroit que la
commande qui lance une session.

Une session ainsi occultée ne mesure rien, mais depuis la rétention des lectures
ratées, elle laisse au moins les images qui permettent de comprendre pourquoi.

### Ce que ces pièges ont coûté, et ce qui a changé depuis

Les cinq ont dû être trouvés à la main, écran sous les yeux, parce que le
logiciel ne gardait aucune trace de ce qu'il n'arrivait pas à lire. Une image
jugée digne d'être lue dont aucun bandeau ne sortait était jetée sur place.
Résultat : « aucune quête mesurée » disait la même chose que le jeu n'ait rien
montré ou que la lecture ait échoué sur tous les bandeaux.

Ce n'est plus le cas. Les images et les lignes lues sont gardées dans `echecs/`,
et `rubin echecs` les compte. **Rien ne part sur le réseau** : le joueur qui veut
aider fabrique une archive et l'envoie lui-même, ce qui rend la question du
consentement sans objet. Les plafonds des trois destinations sont dans
`failures.py`, en une seule table.

### Piste ouverte, pas confirmée : une alerte de boss mondial se pose sur le bandeau

Constaté en jouant le 5 août 2026, vers 18h32, pendant une session qui ne
mesurait déjà plus rien depuis 18h04. Une notification du jeu, « [Vell]
apparaîtra dans 30 min », s'est affichée en bas à droite de l'écran, avec une
icône et une croix de fermeture, **exactement sur la zone du bandeau**.

⚠️ **Elle n'explique pas la panne principale** : la zone était aveugle vingt-
huit minutes avant que cette notification apparaisse. Elle a pu s'ajouter
par-dessus un défaut déjà présent, sans en être la cause.

Ce que ça vaut quand même : les alertes de boss mondial reviennent
régulièrement, calées sur l'horaire du jeu, et occupent ce coin de l'écran
pendant qu'elles sont affichées. Contrairement au piège n°8, ce n'est pas une
fenêtre externe posée sur le jeu, c'est une superposition **du jeu lui-même**,
donc `mss` la capture normalement ; le problème serait que le vrai bandeau, s'il
apparaît au même instant, se trouve masqué ou décalé par elle.

À vérifier la prochaine fois qu'une alerte de ce type apparaît : est-ce qu'un
bandeau attendu à ce moment-là est bien manqué, ou la coïncidence du 5 août
était-elle sans rapport.

### Piste ouverte, pas explorée : les filtres du journal de quêtes en jeu

Repérée en jouant le 5 août 2026 au soir. Le journal de quêtes du jeu porte
neuf icônes de filtre, dans l'ordre : toutes, **principale**, esprit occulte,
général, aventure, profession, contenu, événement, répétable. Il affiche
aussi, en tête, « Quêtes terminées X/Y (Famille : … / Personnage : …) ».

Deux pistes que ça ouvre, aucune vérifiée :

- filtrer sur « principale » donnerait, côté jeu, un compte de référence
  indépendant de tout ce que Rubin lit par ailleurs, utile pour vérifier
  qu'aucune quête principale n'est oubliée ;
- le compteur « Personnage » pourrait recouper le total mesuré par Rubin pour
  ce personnage, si jamais ce nombre est lisible et stable.

Rien de tout cela n'est codé. Le principe du projet s'applique comme
ailleurs : une mesure faite à partir de ce panneau devra être vérifiée en
jeu avant d'entrer dans quoi que ce soit qui compte.

### ✅ Fait le 06/08/2026 : la liste par chaîne suit le vrai ordre du jeu

Maxime a montré son propre écran (panneau « Principales » du journal,
défilé en entier, 178 captures) le temps d'observer l'ordre réel :
Balenos → Serendia → Calpheon → Mediah → Valencia → Kamasylvia → Drieghan →
O'dyllita → Abyss One → Terre du matin radieux → Ulukita → Edania. Capture
OCR complète dans `D:\DEV\bdo\echantillons\observations\_lecture_ocr.txt`.

`GAME_REGION_ORDER` (`interface/presentation.py`) code cet ordre à partir de
`Chain.region`, une vraie valeur du référentiel, jamais un texte reconstruit
à la main. `group_chains_by_game_order` trie dessus, testé sur les 349
vraies chaînes : 178 tombent dans l'ordre confirmé, 61 sont les chaînes de
classe (inchangé), et **110 restent sans région connue ou avec une région
jamais vue en jeu** (Eilton, entre autres). Sur demande explicite de
Maxime : ces 110 vont dans un nouvel onglet replié « Autres chaînes
(position non confirmée) » plutôt que d'être placées au hasard dans l'ordre
confirmé — ce sont de vraies quêtes, on ne sait juste pas où elles se
rangent. Vérifié en vrai fenêtre Tk (technique de capture, section 2ter de
CLAUDE.md), pas seulement par les tests.

### ✅ Corrigé : le panneau de suivi était illisible de nuit

Il n'a aucun fond opaque, contrairement au bandeau. La luminance de toute la
zone plafonnait à **19 sur 255** et la reconnaissance n'y trouvait rien.
Corrigé par `stretch_contrast` (`reading/ocr.py`), appliqué sans condition à
toute lecture avant l'agrandissement : neuf lignes trouvées après étirement
contre zéro avant, mesuré en jeu de nuit. Sans effet mesurable sur une image
déjà contrastée, donc appliqué à toutes les lectures sans distinction plutôt
que seulement à celle-ci.

### Piste ouverte, pas prouvée : une session ne mesure presque rien, alors qu'un témoin externe voit tout

Constaté le 05/08/2026 au soir : cinq sessions consécutives n'ont vu que 0 à 2
bandeaux, contre 14 à 47 vus par un témoin externe observant la même zone au
même moment. Dix-sept causes ont été éliminées une par une, chacune par une
mesure, pas par un raisonnement. Une corrélation forte est apparue avec le
chat du jeu ouvert ou fermé (fermé pendant les sessions aveugles, rouvert
juste avant que la mesure reprenne), mais **jamais prouvée par un test strict
fermé-ouvert-fermé dans une même session**. C'est aujourd'hui la plus grosse
inconnue du projet.

Les outils construits ce soir pour la prochaine fois que ça arrive : la
fenêtre affiche en direct `images capturées / bandeaux vus / lectures`
(`Watching`, `interface/presentation.py`), une image est gardée sur le disque
dans `echecs/` après deux minutes de silence même sans lecture ratée
(`_keep_if_blind`, `interface/session.py`), et les captures qui se répètent
sont comptées (`WatchStats.repeats`, `watching.py`).

---

## Les pièges de l'empaquetage

Deux de plus, trouvés non pas en jouant mais en **publiant**, à travers les
propres tentatives d'installation de Maxime. Ils ont coûté trois releases
correctives (v0.5.0 à v0.5.2 pour le premier, une release de plus pour le
second) avant d'être identifiés.

### 9. L'archive publiée en LZMA est illisible par les outils Windows natifs

`ZIP_LZMA` compresse mieux que `ZIP_DEFLATED`, mais ni l'explorateur Windows
ni `Expand-Archive` de PowerShell ne savent le décompresser : ce sont des
outils limités à la méthode `Deflate`, la seule que le format zip garantit
vraiment. Trois releases (v0.5.0 à v0.5.2) publiées avant de trouver la cause,
après avoir éliminé un téléchargement tronqué (sha256 vérifié), un antivirus
(exclusion ajoutée, rien n'a changé), et le marquage Windows « vient
d'internet » (retiré, rien n'a changé). `Expand-Archive` a fini par rendre le
message d'erreur exact citant l'algorithme non supporté ; l'explorateur
Windows ne rendait qu'une erreur générique (`_asyncio.pyd`, 0x80004005).

Corrigé en `empaquetage/construire.py` : `zipfile.ZIP_DEFLATED,
compresslevel=9`.

### 10. `console=True` ouvrait un terminal noir à côté de la fenêtre

Un double-clic sur l'exécutable ouvrait une fenêtre de console vide en plus de
la fenêtre Tk, que le joueur devait fermer lui aussi sans en comprendre
l'utilité. Rien ne la justifiait pour ce chemin : la fenêtre graphique dit
tout ce qu'il faut. Corrigé par `console=False` dans `rubin.spec`, avec
`AttachConsole` dans `empaquetage/point_entree.py` pour que les commandes de
terminal (`rubin verifier`, `rubin suivre`, `rubin echecs`) gardent leur texte
quand elles sont lancées depuis un vrai terminal. ⚠️ Vérifié que
`AttachConsole` réussit techniquement ; **pas vérifié qu'un vrai terminal
humain affiche le texte**, les outils automatisés utilisés pour tester n'ayant
pas de vraie console à eux pour le prouver.

---

## Décisions de conception, et pourquoi

**Un journal d'événements, pas un chronomètre.** Le bandeau de fin se rate
quand on enchaîne vite. Un chronomètre resterait bloqué sur une quête terminée ;
le journal déduit la fin par la position dans la chaîne et marque la mesure
comme déduite.

**Capture et lecture dans deux fils séparés.** Une reconnaissance prend 300 à
1 000 ms, pendant lesquelles la boucle simple cessait de regarder l'écran. Un
bandeau apparu dans cet intervalle était perdu en silence.

**L'instant retenu est celui de la capture**, jamais celui de la lecture. Sinon
chaque mesure serait allongée de la durée de sa propre reconnaissance, et les
quêtes courtes seraient les plus faussées.

**Le classement se fait sur la médiane, jamais sur le record.** Un temps envoyé
par un client local est une affirmation, pas une observation. Un tricheur
s'empare d'un record en un envoi ; il ne déplace pas une médiane.

**Deux chiffres qu'il ne faut pas confondre.** Le débit au rythme médian sert à
comparer des chaînes. La somme des médianes sert à prévoir une durée. Sur une
session réelle : 77 quêtes/heure au rythme médian, 36 réellement produites.

**Rien n'est envoyé sans `--envoyer`.** Transmettre les données de quelqu'un
sans qu'il l'ait demandé serait une décision prise à sa place.

**En revanche, du réseau part bien pendant que le joueur joue**, et il faut le
dire parce que le contraire a longtemps été écrit dans `protocol.py` et
`upload.py` : « en fin de session et non au fil de l'eau, cela évite toute
requête réseau pendant que le joueur joue ». C'était faux. `ReferenceClient`
interroge le serveur **à chaque quête**, pendant la partie, pour afficher les
temps des autres. Les mesures partent donc elles aussi après chaque quête
terminée, sur le même fil, sans ouvrir aucune catégorie de risque nouvelle.

**Chaque mesure est écrite sur le disque dès qu'elle existe**, dans un journal
en ajout, et **seules les mesures jamais transmises sont envoyées**. Les deux
règles répondent à des dangers opposés : la première à la session perdue, quand
le processus est tué, que Windows redémarre ou que le logiciel plante ; la
seconde au **double comptage**, qui est le seul risque réel du fil de l'eau.
Une mesure reçue deux fois gonfle `samples`, entre deux fois dans la médiane, et
rien ne la distingue de deux mesures réelles.

**Aucune interaction avec le jeu.** Pas de lecture mémoire, pas d'injection,
pas de surcouche, pas de touche simulée. C'est une limite de conception, pas
une étape à franchir plus tard. Une proposition qui la franchit est refusée,
quel que soit son intérêt.

---

## Ce qui reste

### Fait le 06/08/2026 : Discord en ligne, rattachement et robot

- **Le rattachement de compte.** `GET /v1/discord/connexion` envoie vers
  Discord, `GET /v1/discord/retour` reçoit le code et rattache le compte.
  Politique de confidentialité mise à jour d'abord (dépôt `maxyull.fr`, PR
  fusionnée), puis application créée sur le portail développeur Discord
  (portée `identify` seule), puis `RUBIN_DISCORD_ID` et
  `RUBIN_DISCORD_SECRET` posés dans `D:\DEV\secrets\rubin-bdo.env` et
  `bash serveur/deploiement/deployer.sh` rejoué. Vérifié en production par
  `curl` : redirection 307 avec le bon `client_id`, la bonne `redirect_uri`,
  la bonne portée.

- **Le robot de consultation.** Application Discord distincte (jeton de bot,
  jamais le secret OAuth du rattachement), `Intents.none()`, Public Bot
  décoché, permissions **0** à l'invitation. Jeton copié par le
  presse-papiers (jamais recopié à l'œil depuis une capture, un écart d'un
  seul caractère a été observé une fois entre les deux) dans
  `D:\DEV\secrets\rubin-bot.env`, séparé de `rubin-bdo.env`. Déployé par
  `bash bot/deploiement/deployer.sh` (nouveau, PR #101, sur le modèle de
  `serveur/deploiement/deployer.sh`, refuse de s'exécuter sans jeton), en
  service systemd `rubin-bot.service` propre, sans bloc Caddy puisque le
  robot ne fait que des connexions sortantes vers la passerelle Discord.
  Vérifié actif (`systemctl is-active`) et connecté (`journalctl` : « Shard
  ID None has connected to Gateway »). Reste à Maxime : ouvrir le lien
  d'invitation et choisir le serveur Discord privé où l'installer ; les
  commandes `/rapides /chaine /quete` apparaîtront quelques instants après.

  Le `measured_total_seconds` de l'API n'y est **pas lu du tout**, avec un
  test qui casse si quelqu'un l'ajoute : un champ jamais lu ne peut pas
  s'afficher par mégarde, et la somme des médianes ment d'un facteur deux.

### À écrire

- ✅ **Le noyau partagé `bdo-ocr-core`, extrait le 06/08/2026.** Nouveau dépôt
  public [Maxyull/bdo-ocr-core](https://github.com/Maxyull/bdo-ocr-core)
  (MIT, sa propre CI), avec `normalize`, `scroll` et `stability`. Branché
  côté butin (PR #58/#59, 696 tests toujours verts, aucun test modifié).
  ⚠️ **Pas branché côté rubin** : mesuré sur les 18 999 quêtes réelles avant
  de décider (pas de suppositions), remplacer `fold` de rubin par celui du
  socle casserait 27 quêtes du référentiel FR jamais traduites du coréen
  (elles s'effondrent toutes sur la même clé vide, le fold partagé ne
  gardant que `[a-z0-9 ]`). `fold` de rubin reste donc inchangé, et `scroll`
  /`stability` n'ont aujourd'hui aucun usage ici (rien n'y suit un
  défilement de texte à l'écran) : la dépendance n'a pas été ajoutée pour
  ne pas être un import mort. Détail complet dans `../COORDINATION.md`.
- **Un site de consultation.** Le classement n'existe qu'en JSON. C'est ce qui
  fera venir les joueurs, mais il n'aura d'intérêt qu'avec de la matière à
  montrer.

### Ce qu'aucun code ne peut résoudre

Ces trous se comblent par l'usage, pas par de la programmation :

- **82 chaînes ont des trous de numérotation**, et le jeu compte 19 235 quêtes
  quand le référentiel en connaît 18 999.
- **69 quêtes sont des embranchements**, réparties sur 38 chaînes. On sait
  lesquelles, mais pas lesquelles s'excluent entre elles : deux carrefours
  indépendants y sont indiscernables d'un choix à quatre branches. Deux
  branches jamais faites par la même personne sont probablement exclusives.
- **La base ne contient encore que peu de matière.** Vérifié en direct le
  05/08/2026 au soir via `GET /v1/couverture` : **30 quêtes mesurées**, seuil
  « bien mesurée » à 5 échantillons, **aucune ne l'atteint encore**
  (`well_measured: 0`). Ce sont des mesures, pas encore des références.

---

## Conventions

Celles de `butin-bdo`, qui partage ce dossier et partagera son noyau :

- **français** pour tout ce que lit un humain, y compris les messages de
  commit ; **anglais** pour le code ;
- une branche par changement, jamais de poussée directe sur `main` ;
- **deux tests par changement** : un unitaire, un de régression dont la
  docstring raconte le cas réel rencontré ;
- les tests emploient de **vraies** quêtes avec leurs vrais identifiants, et
  les sorties réelles de la reconnaissance, défauts compris.

Le principe qui tranche les arbitrages :

> **Rater une mesure donne un chiffre incomplet. En inventer une donne un
> chiffre faux.** Un chiffre incomplet reste exploitable ; un chiffre faux
> entre dans les médianes et n'en ressort jamais.

## Vérifier que tout va bien

```bash
rubin verifier --serveur https://rubin.maxyull.fr
```

Elle contrôle le moteur de reconnaissance, le référentiel, la version et la
fenêtre du jeu. Dans une version empaquetée, un fichier manquant ne se voit
sinon qu'au milieu d'une session.
