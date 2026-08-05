# Empaquetage

```bash
python empaquetage/construire.py
```

Produit `dist/rubin/` et `dist/rubin-windows-{version}.zip` (par exemple
`rubin-windows-0.5.4.zip`, la version vient de `rubin.__version__`), prêt à
distribuer. Personne n'a besoin d'installer Python pour s'en servir.

## Poids

| | Dossier | Archive |
|---|---|---|
| première tentative | 233 Mo | 99 Mo |
| **après nettoyage** | **182 Mo** | **59 Mo** |

Le poids restant vient presque entièrement des bibliothèques natives de la
reconnaissance de caractères, qu'on ne peut pas alléger :

| Paquet | Poids | Pourquoi il est là |
|---|---|---|
| OpenCV | 71 Mo | RapidOCR s'en sert pour préparer les images |
| onnxruntime | 33 Mo | exécute les modèles |
| modèles | 15 Mo | la reconnaissance elle-même |
| numpy | 26 Mo | avec sa bibliothèque d'algèbre linéaire |

## Ce qui a été retiré, et pourquoi c'est sans risque

Le décodeur vidéo d'OpenCV (30 Mo), ses détecteurs de visages (3,6 Mo) et les
décodeurs d'images AVIF et WebP. Ces fichiers ne sont chargés qu'au moment où
la fonction correspondante sert : ce logiciel n'ouvre ni vidéo, ni fichier
image, seulement des captures d'écran.

⚠️ La variante « headless » d'OpenCV **n'est pas suffisante** : elle retire
l'interface graphique, pas le décodage vidéo. Il faut écarter le fichier
explicitement, ce que fait la recette.

## Vérifier le résultat

```bash
dist\rubin\rubin.exe verifier
```

Un fichier manquant dans un exécutable ne se voit qu'au moment où il sert,
c'est-à-dire au milieu d'une session de jeu. Cette commande le découvre avant,
et sert aussi de diagnostic chez quelqu'un d'autre : « ça ne marche pas » n'est
pas un diagnostic, il faut savoir quelle étape a échoué.

## Sur la compression

L'archive est en LZMA et non dans le format par défaut du zip : sur des
binaires de cette taille, elle rend une archive presque deux fois plus petite
pour quelques dizaines de secondes de plus à la construction. C'est ce que les
gens téléchargent, donc c'est là que le poids compte.

UPX n'est pas utilisé : le gain est faible et il déclenche des faux positifs
d'antivirus, ce qui coûterait bien plus cher que les méga-octets économisés.
