# Sécurité

Rubin lit l'écran, ne touche jamais au jeu, et envoie des mesures de temps à
`https://rubin.maxyull.fr`. Voir `bot/README.md` et `serveur/` pour le détail
de ce qui part et ce qui reste local.

## Versions suivies

Projet à releases fréquentes, une seule version compte : **la dernière
publiée**. Les versions plus anciennes ne reçoivent pas de correctif dédié,
mettez à jour plutôt qu'attendre un rétroportage.

## Signaler une faille

Pas d'issue publique pour une faille non corrigée : utilisez l'onglet
**Security** du dépôt GitHub (*Report a vulnerability*), qui ouvre un
échange privé avec le mainteneur. Si l'onglet n'est pas accessible, une issue
minimale ("faille de sécurité, contactez-moi") suffit pour amorcer un canal
privé, sans détail technique dedans.

Ce qui aide dans le signalement : la version de Rubin (`rubin --version` ou
le titre de la fenêtre), les étapes pour reproduire, et l'impact envisagé
(exécutable, serveur, robot Discord).

## Hors périmètre

Le principe du projet ([ETAT.md](ETAT.md), section "ce que Rubin ne fera
jamais") exclut toute interaction avec le jeu : lecture mémoire, injection,
automatisation des touches. Un rapport qui demanderait d'en ajouter pour
"corriger" quelque chose sera refusé, quel que soit le motif.
