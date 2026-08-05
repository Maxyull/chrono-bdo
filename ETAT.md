# État du projet, au 5 août 2026

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
| Serveur, classement, envoi | ✅ **en ligne** |
| Exécutable Windows | ✅ 59 Mo |
| Vérification de version | ✅ |
| Rétention des lectures ratées | ✅ local, envoi manuel |
| Rattachement Discord | ⏸ écrit, en attente d'identifiants |

## En ligne

| | |
|---|---|
| Serveur | **https://rubin.maxyull.fr** |
| Dépôt | https://github.com/Maxyull/rubin-bdo |
| Release | https://github.com/Maxyull/rubin-bdo/releases |
| Confidentialité | https://maxyull.fr/confidentialite.html |

Le serveur tourne en systemd sur le VPS OVH, dans `/opt/rubin`, base Postgres
dédiée, derrière Caddy. Redéploiement et mise à jour :
`bash serveur/deploiement/deployer.sh`, rejouable sans rien détruire.

---

## Les cinq pièges découverts en jouant

**Aucun n'était visible sur des captures d'écran fixes**, et chacun suffisait
à lui seul pour qu'aucune quête ne soit jamais mesurée. C'est la leçon
principale du projet : un jeu de test figé valide la lecture d'une image, pas
le comportement d'une interface vivante.

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

### Ce que ces cinq pièges ont coûté, et ce qui a changé depuis

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

**Aucune interaction avec le jeu.** Pas de lecture mémoire, pas d'injection,
pas de surcouche, pas de touche simulée. C'est une limite de conception, pas
une étape à franchir plus tard. Une proposition qui la franchit est refusée,
quel que soit son intérêt.

---

## Ce qui reste

### Prêt à brancher

- **Le rattachement Discord.** Le code est écrit et testé. Il attend
  `RUBIN_DISCORD_ID` et `RUBIN_DISCORD_SECRET`, et l'URL de retour à déclarer
  est `https://rubin.maxyull.fr/v1/discord/retour`. ⚠️ Activer implique
  d'ajouter le pseudonyme Discord à la politique de confidentialité.

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
