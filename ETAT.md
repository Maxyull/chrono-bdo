# État du projet, au 5 août 2026 (0.4.0 publiée)

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
| Exécutable Windows | ✅ **0.4.0 publiée**, 59 Mo |
| Vérification de version | ✅ le serveur annonce 0.4.0 |
| Rétention des lectures ratées | ✅ local, envoi manuel |
| Interface graphique | ✅ 3 onglets, zones réglables |
| Rattachement Discord | ⏸ en ligne, **503** faute d'identifiants |
| Robot Discord de consultation | ⏸ écrit et testé, jamais lancé |

## En ligne

| | |
|---|---|
| Serveur | **https://rubin.maxyull.fr** |
| Dépôt | https://github.com/Maxyull/rubin-bdo |
| Release | **v0.4.0**, https://github.com/Maxyull/rubin-bdo/releases |
| Confidentialité | https://maxyull.fr/confidentialite.html |

Le serveur tourne en systemd sur le VPS OVH, dans `/opt/rubin`, base Postgres
dédiée, derrière Caddy. Redéploiement et mise à jour :
`bash serveur/deploiement/deployer.sh`, rejouable sans rien détruire.

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

### En prime : le panneau de suivi est illisible de nuit

Il n'a aucun fond opaque, contrairement au bandeau. La luminance de toute la
zone plafonnait à **19 sur 255** et la reconnaissance n'y trouvait rien.
Étirement du contraste obligatoire avant toute lecture.

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

### Branché, mais éteint

- **Le rattachement Discord.** Ce fichier a longtemps annoncé « écrit et
  testé » ; c'était faux sur un point qui comptait. Le module
  `serveur/src/rubin_serveur/discord.py` existait bien, avec ses tests
  unitaires, mais **aucune adresse ne l'appelait** : rien ne l'importait dans
  l'application, et `https://rubin.maxyull.fr/v1/discord/retour` rendait 404.
  Un module non branché ressemble à s'y méprendre à une fonctionnalité prête.

  C'est fait depuis : `GET /v1/discord/connexion` envoie vers Discord,
  `GET /v1/discord/retour` reçoit le code et rattache le compte. Les deux
  rendent **503** tant que `RUBIN_DISCORD_ID` et `RUBIN_DISCORD_SECRET` sont
  absents, ce qui est l'état de la production aujourd'hui, et le reste du
  serveur n'en sait rien.

  Reste à faire, dans cet ordre, et rien de tout cela n'est du code :

  1. ⚠️ **ajouter le pseudonyme Discord à la politique de confidentialité**,
     qui promet aujourd'hui qu'aucun pseudonyme n'est transmis. La politique
     vit dans un autre dépôt, celui de `maxyull.fr` ;
  2. créer l'application sur le portail développeur Discord, portée `identify`
     seule, et y déclarer l'URL de retour
     `https://rubin.maxyull.fr/v1/discord/retour` ;
  3. poser les identifiants dans `D:\DEV\secrets\rubin-bdo.env` et rejouer
     `bash serveur/deploiement/deployer.sh`, qui les porte jusqu'au service.

  Et ce que ce n'est pas : un **robot** Discord. Il n'y a ici ni jeton de
  robot, ni passerelle, ni présence dans un salon. C'est un rattachement de
  compte par OAuth2, qui lit un pseudonyme une fois et jette le jeton.

### Le robot, écrit mais jamais lancé

Un dossier `bot/` à part, avec son venv et son propre job d'intégration
continue. Trois commandes en lecture seule sur l'API publique : `/rapides`,
`/chaine`, `/quete`. `Intents.none()`, aucune intention privilégiée, aucun
pouvoir d'administration, permissions **0** à l'invitation.

Il n'a **jamais tourné** : il attend `RUBIN_BOT_JETON`. Et contrairement au
serveur web, un robot tient une connexion sortante permanente, donc il lui faut
un service systemd propre que `deployer.sh` ne couvre pas. Ne pas activer
l'unité avant que le jeton soit posé, sinon boucle de redémarrage.

Le `measured_total_seconds` de l'API n'y est **pas lu du tout**, avec un test
qui casse si quelqu'un l'ajoute : un champ jamais lu ne peut pas s'afficher par
mégarde, et la somme des médianes ment d'un facteur deux.

### À écrire

- **Le noyau partagé `bdo-ocr-core`**, jamais extrait. Butin et Rubin ont
  chacun leur normalisation, et une correction faite ici ne profite pas à
  l'autre. Voir `../COORDINATION.md`, l'autre session a répondu.
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
- **La base ne contient que 11 mesures**, toutes d'un seul joueur sur une seule
  chaîne. Ce sont des mesures, pas encore des références.

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
