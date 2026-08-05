# Où va le projet

Ce fichier note l'intention, pas un plan de travail. Il existe parce qu'une idée
discutée puis non écrite se redécouvre six mois plus tard, avec ses pièges
intacts.

L'ordre des sections est l'ordre de construction, et il n'est pas arbitraire :
chaque étape produit la matière dont la suivante a besoin.

---

## La finalité

Un joueur donne son nombre de personnages et son objectif de quêtes. Le logiciel
lui dit **quelle quête faire, sur quel personnage, dans quel ordre**, pour y
arriver le plus vite.

C'est le seul but. Tout le reste est l'infrastructure qui permet d'y répondre
sans mentir.

---

## 1. La liste des quêtes suivantes — ✅ faite

Pendant qu'on joue, le logiciel montre les quêtes qui viennent, avec leur temps
et la solidité de ce temps. Une quête finie fait avancer la liste toute seule.

Écrite dans `src/rubin/upcoming.py`, affichée après chaque mesure, réglable par
`--suivantes N`.

Trois pièges y étaient, et le module les documente en détail :

- **les embranchements interdisent de promettre un chemin unique.** 69 quêtes
  principales sur 38 chaînes sont des branches d'un choix. On sait lesquelles
  sont des branches, pas lesquelles s'excluent entre elles. Elles sont marquées,
  jamais présentées comme une suite à faire dans l'ordre ;
- **les trous de numérotation** touchent 82 chaînes sur 349. Supposer que la
  quête suivante porte la position juste après ferait disparaître la suite de
  ces chaînes dès le premier trou. Les positions sont donc prises telles que le
  référentiel les connaît, et le trou est signalé plutôt qu'enjambé en silence ;
- **une quête jamais mesurée le dit.** Une colonne vide ou un zéro se lirait
  comme « instantané » au lieu de « inconnu ».

Noter que le traitement des trous est **l'inverse** de celui de la déduction
d'une fin manquée, dans `timing.py`, et que la différence est délibérée.
Déduire exige la contiguïté, parce qu'un trou peut cacher une quête réellement
faite dont on inclurait le temps par erreur : ce serait une mesure fausse.
Afficher n'exige rien, puisque montrer la suite connue n'invente aucun chiffre.

## 2. Le score de confiance

Chaque temps affiché porte une note sur cent qui dit à quel point il est solide.
Un chiffre nu laisse croire qu'il vaut ce qu'il affiche, quel que soit ce qu'il
y a derrière.

Trois règles, sans lesquelles la note devient elle-même un chiffre faux.

**Le score se dérive de faits comptables, et les faits restent affichés.**

```
[Calpheon] Cris stridents des harpies   4 min 12 s   score 38
                                        6 joueurs, 14 mesures, écart ±22 s
```

Le score sert à trier. Les trois nombres derrière sont la vérité. Si le score
disparaissait, rien ne serait perdu ; l'inverse est faux.

**Le plafond est fixé par le nombre de joueurs distincts, jamais par le nombre
de mesures.** Refaire une quête cinquante fois converge vers le temps de celui
qui la refait, pas vers celui des joueurs. Un joueur seul ne doit donc jamais
dépasser un plafond bas, quel que soit son acharnement, sinon le premier arrivé
fige une référence que personne n'a confrontée.

C'est le manque précis côté serveur : [`QuestStats.samples`](../serveur/src/rubin_serveur/storage.py)
compte les mesures, pas les joueurs distincts. Le `player` est sur la table
`sessions`, donc c'est une jointure.

**Le maillon faible, pas la moyenne.** `score = min(part_joueurs, part_précision)`.
Une moyenne laisserait vingt joueurs très dispersés produire une bonne note.

Et **cent doit rester hors de portée en pratique** : un score plein dit
« arrêtez de mesurer », ce qui gèlerait la donnée.

### Pourquoi pas un système de vote

Un vote est une **affirmation**, pas une observation, et le projet a déjà tranché
contre les affirmations : le classement se fait sur la médiane et jamais sur le
record, parce qu'un temps envoyé par un client local est falsifiable. Un vote est
plus faible encore, c'est une opinion sans mesure derrière, et un compte neuf
suffit à en produire cent.

Le besoin réel qu'exprimait l'idée du vote est bon, et il se règle autrement :
**le vote implicite est le nombre de joueurs distincts qui ont mesuré**. Douze
personnes qui ne se connaissent pas et dont les médianes se ressemblent, c'est
plus fort que douze clics « c'est bon », et ça arrive sans que personne vote.

Le corollaire est une économie réelle : **une quête dont le score est haut n'a
plus besoin d'être envoyée**, le client peut cesser de la transmettre.

## 3. Le classement

Pseudonyme, temps, et le nom du personnage. Top dix ou top cent.

⚠️ **C'est une décision, pas une fonctionnalité.** L'identifiant est aujourd'hui
un UUID anonyme, et le README comme la politique de confidentialité *promettent*
qu'aucun pseudonyme ne part. Un nom de personnage BDO est unique, public en jeu,
et rattaché à un nom de famille : c'est une donnée personnelle.

Ordre obligatoire : **politique de confidentialité d'abord, code ensuite**,
opt-in, éteint par défaut. C'est la forme déjà retenue pour le rattachement
Discord.

## 4. Le planificateur

Le but final. Il n'est pas bloqué par du code.

Trier les chaînes par quêtes/heure et les enchaîner donne à peu près l'optimum,
et tient dans une après-midi. **Ce qui manque, ce sont les mesures.**

| | |
|---|---|
| Quêtes principales | 3 924 |
| Mesures pour une médiane crédible | 5 par quête |
| Mesures nécessaires | 19 620 |
| Débit réellement observé | 36 quêtes/heure |
| **Temps de jeu, quêtes principales seules** | **545 heures** |
| Le même pour les 18 999 quêtes du référentiel | 2 639 heures |

545 heures seul. À dix joueurs, 55 heures chacun. À cent joueurs, cinq heures et
demie.

**Le planificateur est donc bloqué par le nombre de joueurs, pas par le code.**
C'est ce qui fixe l'ordre de ce fichier : ce qui recrute doit sortir avant ce qui
consomme. La liste des quêtes suivantes est utile dès aujourd'hui, avec onze
mesures, parce qu'un score bas est une information et une invitation.

### Le piège qui attend dedans

**La somme des médianes ment d'un facteur deux.** Sur une session réelle, le
débit au rythme médian annonçait 77 quêtes/heure là où la session en avait
produit 36. Trajets, dialogues, marché, mort.

Un planificateur qui somme des médianes promettra 30 000 quêtes en moitié moins
de temps que la réalité. C'est le chiffre faux dans sa forme la plus nuisible :
plausible, précis, et faux du simple au double. Il doit prédire à partir du
**débit de session observé**, jamais de la somme des médianes.

---

## Ce qui ne changera pas

Aucune interaction avec le jeu. Pas de lecture mémoire, pas d'injection, pas de
surcouche, pas de touche simulée. Une proposition qui franchit cette limite est
refusée, quel que soit son intérêt.

Et l'arbitrage qui tranche tout le reste :

> **Rater une mesure donne un chiffre incomplet. En inventer une donne un chiffre
> faux.** Un chiffre incomplet reste exploitable ; un chiffre faux entre dans les
> médianes et n'en ressort jamais.
