# Versionnage

Rubin suit [SemVer 2.0.0](https://semver.org/lang/fr/) et tient son journal des
modifications au format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

Ces deux conventions sont l'usage courant, mais elles ont été pensées pour des
bibliothèques dont on ne casse que l'interface de programmation. Rubin est
autre chose : un logiciel installé chez des joueurs, qui envoie des mesures à un
serveur, et qui s'appuie sur des données appartenant à un jeu qui évolue sans
nous prévenir.

Trois choses versionnent donc séparément, et les confondre serait une erreur.

## 1. La version du logiciel

Quatre nombres depuis le 07/08/2026, `0.IMPORTANTE.SECONDAIRE.NÉGLIGEABLE`,
dans `pyproject.toml` et `rubin.__version__`.

Le quatrième a été demandé par Maxime, avec sa raison : « pour ajouter le
dernier chiffre maj vraiment pas importante ». Les trois nombres de SemVer ne
distinguaient pas une correction qui change les mesures d'un mot corrigé dans
une infobulle, et les deux arrivaient au joueur sur le même ton.

| Rang | Nom | Ce qui bouge | Ce que le joueur doit faire |
|---|---|---|---|
| 1er | — | le passage en 1.0 | mettre à jour |
| 2e | **IMPORTANTE** | la reconnaissance, ou tout ce qui change une mesure | **mettre à jour**, sinon ses mesures peuvent être fausses |
| 3e | **SECONDAIRE** | affichage, placement, confort | recommandé, pas indispensable |
| 4e | **NÉGLIGEABLE** | texte, couleur, détail sans conséquence | rien ne presse |

### Le niveau se lit dans le numéro, et nulle part ailleurs

⚠️ **Aucun champ « importance » n'est servi par le serveur, et c'est un
choix.** Un champ posé à côté du numéro pourrait annoncer « mineure » sur une
version qui change la reconnaissance, et rien ne rattraperait la
contradiction. Ici, publier une version dont le deuxième chiffre bouge **est**
l'annonce : les deux ne peuvent pas se contredire parce qu'ils sont la même
chose.

Le calcul est dans `rubin/updates.py`, `update_importance` : le rang du
**premier chiffre qui diffère** donne le niveau. Les numéros de longueurs
différentes sont comparés en complétant par des zéros, parce que toutes les
versions publiées avant le 07/08/2026 n'ont que trois chiffres : `0.6.2` et
`0.6.2.1` ne diffèrent qu'au quatrième rang, donc négligeable, ce qui est
exact.

### Ce que le joueur voit

L'en-tête de la fenêtre et le bouton changent de texte **et de couleur** selon
le niveau (`format_update_offer`, `interface/presentation.py`) :

| Niveau | En-tête | Bouton | Couleur |
|---|---|---|---|
| importante | ⚠ Mise à jour IMPORTANTE, la reconnaissance a changé : sans elle vos mesures peuvent être fausses | Mettre à jour, important | alerte |
| secondaire | Mise à jour secondaire, affichage et confort : recommandée, pas indispensable | Mettre à jour | moyen |
| négligeable | Mise à jour mineure : rien qui presse | Mettre à jour, sans urgence | faible |

⚠️ **Chaque phrase dit ce qu'il faut FAIRE**, jamais seulement ce qui a
changé. Un joueur ne sait pas ce qu'« OCR » veut dire pour lui ; il sait ce
que « vos mesures peuvent être fausses » veut dire.

Le but est qu'un avertissement garde sa valeur. Répéter « une version est
disponible » du même ton pour un changement de reconnaissance et pour un mot
corrigé use l'alerte : le jour où elle compte, plus personne ne la lit.

### Ce qu'un changement MAJEUR veut dire ici

Pour une bibliothèque, il casse le code des autres. Ici, il casse la
**comparabilité des mesures**, ce qui est bien pire : personne ne voit
d'erreur, les chiffres continuent de s'afficher, et un classement mélange deux
définitions du même mot.

**Toute redéfinition de ce que « le temps d'une quête » signifie est un
changement important**, même si aucune ligne d'interface ne bouge.

### À dire à chaque publication, partout

Le niveau doit être annoncé **au même endroit que la version**, sur les deux
canaux, sans quoi le barème ne sert à rien pour ceux qui lisent l'annonce
plutôt que la fenêtre.

**Sur la release GitHub**, en toute première ligne des notes :

```markdown
> **Mise à jour secondaire.** Affichage et confort : recommandée, pas
> indispensable.
```

**Sur Discord**, dans le salon d'annonces, la même phrase et rien de plus
technique :

```
🔴 **Rubin v0.7.0.0 — mise à jour IMPORTANTE**
La reconnaissance a changé. Sans cette version, vos mesures peuvent être
fausses. Un bouton de mise à jour apparaît dans la fenêtre.

🟠 **Rubin v0.6.3.0 — mise à jour secondaire**
Affichage et confort. Recommandée, rien d'indispensable.

⚪ **Rubin v0.6.2.1 — mise à jour mineure**
Un détail corrigé. Rien qui presse, mettez à jour quand ça vous arrange.
```

Une pastille de couleur par niveau, la même que dans la fenêtre : rouge pour
importante, orange pour secondaire, blanche pour négligeable. Un lecteur qui
ne lit que l'emoji doit déjà savoir s'il doit agir.

## 2. La version du protocole d'envoi

Un entier, incrémenté seul, transmis dans chaque lot envoyé au serveur.

Il est séparé de la version du logiciel parce que les deux ne vivent pas au même
rythme : le logiciel se met à jour chez chaque joueur quand il le veut, le
serveur se met à jour d'un coup. À tout instant, le serveur reçoit des lots
émis par plusieurs versions du logiciel à la fois.

Règle : **le serveur accepte la version courante et la précédente.** Un joueur
qui n'a pas mis à jour depuis un mois continue de contribuer. Au-delà, le lot
est refusé avec un message qui dit quoi faire, plutôt qu'accepté et mal
interprété.

Une mesure mal interprétée entre dans les médianes et n'en ressort jamais.

## 3. La version du référentiel

Le catalogue des quêtes vient de bdocodex et suit **le jeu**, pas Rubin. Il
change quand Pearl Abyss ajoute, retire ou renomme des quêtes, ce qui ne
demande à personne son avis.

Chaque mesure enregistre donc la date du référentiel qui a servi à identifier la
quête. Sans ça, une quête renommée en cours de route donnerait deux séries de
temps sous deux noms différents, sans qu'aucun moyen n'existe de savoir qu'il
s'agit de la même.

C'est aussi pourquoi l'identifiant stocké est toujours la paire
`chaîne/position`, jamais le nom : le nom change, l'identifiant non.

## Étiquettes git

Une version publiée porte une étiquette `vMAJEUR.MINEUR.CORRECTIF`, posée sur le
commit qui met à jour le journal des modifications.

```bash
git tag -a v0.1.0 -m "Référentiel des quêtes"
git push origin v0.1.0
```

## Avant 1.0.0

Tant que le numéro majeur vaut zéro, rien n'est stable et tout peut changer sans
préavis, comme le prévoit SemVer. Rubin passera en `1.0.0` le jour où un temps
mesuré par un joueur pourra être comparé à celui d'un autre sans réserve. Ce
n'est pas une question de fonctionnalités, c'est une question de confiance dans
le chiffre.
