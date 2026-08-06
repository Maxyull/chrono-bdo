# Images de la fenêtre

⚠️ **Deux conditions pour qu'une image d'ici arrive chez un joueur**, et
oublier l'une des deux ne produit aucune erreur :

1. **être suivie par git.** `.gitignore` ignore `*.png` dans tout le dépôt,
   parce que les captures de jeu portent des pseudonymes de joueurs tiers.
   Toute exception se déclare une par une, après avoir vérifié le contenu.
2. **être déclarée dans `donnees`**, au début de `empaquetage/rubin.spec`,
   sans quoi elle ne sera pas dans l'exécutable. Le dossier entier y a manqué
   jusqu'au 06/08/2026.

`tests/test_empaquetage.py` vérifie la seconde. La première ne se voit qu'en
regardant `git ls-files`, ce que personne ne fait spontanément.

| Fichier | Rôle | Suivi ? |
|---|---|---|
| `rubin.ico` | icône de `rubin.exe`, de l'installateur et de la fenêtre | oui |
| `discord-logo.png` | le bouton « Rejoindre le Discord » | oui, par exception |
| `exemple-bandeau.png` | illustration du guide | **non**, voir plus bas |
| `exemple-suivi.png` | illustration du guide | **non**, voir plus bas |
| `icone_principale.png` | plus employé par aucun code | non |

## Les deux illustrations du guide ne sont pas dans le dépôt

Ce sont des captures du jeu. Elles ne sont donc pas suivies par git, et
n'arrivent chez aucun joueur : le guide affiche son texte sans elles, sans le
dire, parce que `help.py` garde le coup par un `chemin.is_file()`.

Les committer demande de vérifier d'abord qu'aucun pseudonyme de joueur tiers
n'y figure, puis d'ajouter une exception dans `.gitignore`. C'est une décision
qui appartient à Maxime, pas au code : la règle du dépôt existe pour protéger
des gens qui n'ont rien demandé.

## `discord-logo.png` n'appartient pas à ce projet

C'est la marque de Discord Inc., pas la nôtre, et la licence MIT de ce dépôt
ne s'y applique pas. Elle est employée pour ce à quoi une marque sert :
désigner Discord, sur un bouton qui mène à un serveur Discord, ce que les
règles de marque de Discord prévoient explicitement. Rubin n'est ni affilié à
Discord ni approuvé par lui.

`rubin.ico`, lui, vient du kit visuel commun aux projets BDO,
`D:\DEV\bdo\logos\kit`, regénérable par `build_kit.py`.
