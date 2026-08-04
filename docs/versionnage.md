# Versionnage

Chrono suit [SemVer 2.0.0](https://semver.org/lang/fr/) et tient son journal des
modifications au format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

Ces deux conventions sont l'usage courant, mais elles ont été pensées pour des
bibliothèques dont on ne casse que l'interface de programmation. Chrono est
autre chose : un logiciel installé chez des joueurs, qui envoie des mesures à un
serveur, et qui s'appuie sur des données appartenant à un jeu qui évolue sans
nous prévenir.

Trois choses versionnent donc séparément, et les confondre serait une erreur.

## 1. La version du logiciel

Le numéro classique, `MAJEUR.MINEUR.CORRECTIF`, dans `pyproject.toml` et
`chrono.__version__`.

| Incrément | Quand | Exemple concret |
|---|---|---|
| **CORRECTIF** | une mesure était fausse, elle devient juste | un bandeau sur deux lignes n'était pas recollé |
| **MINEUR** | le logiciel sait faire quelque chose de plus | il reconnaît les quêtes du Esprit Noir |
| **MAJEUR** | ce qui était mesuré avant ne se compare plus à ce qui est mesuré après | on cesse de compter le temps de trajet dans la durée |

Ce dernier point mérite l'attention. Pour une bibliothèque, un changement majeur
casse le code des autres. Ici, il casse la **comparabilité des mesures**, ce qui
est bien pire : personne ne voit d'erreur, les chiffres continuent de s'afficher,
et un classement mélange deux définitions du même mot.

**Toute redéfinition de ce que « le temps d'une quête » signifie est un
changement majeur**, même si aucune ligne d'interface ne bouge.

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

Le catalogue des quêtes vient de bdocodex et suit **le jeu**, pas Chrono. Il
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
préavis, comme le prévoit SemVer. Chrono passera en `1.0.0` le jour où un temps
mesuré par un joueur pourra être comparé à celui d'un autre sans réserve. Ce
n'est pas une question de fonctionnalités, c'est une question de confiance dans
le chiffre.
