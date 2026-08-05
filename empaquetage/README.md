# Empaquetage

```bash
python empaquetage/construire.py
```

Produit `dist/rubin/`, l'archive `dist/rubin-windows-{version}.zip`, et
l'installateur `dist/rubin-installateur-{version}.exe` s'il trouve Inno Setup
(sinon un message le dit, sans faire échouer la construction). La version
vient de `rubin.__version__`, la même source pour les deux noms de fichier,
`metadonnees.txt` (régénéré à chaque fois) et `RUBIN_LATEST` côté serveur.
Personne n'a besoin d'installer Python pour se servir de l'un ou l'autre.

## L'installateur

`empaquetage/rubin.iss`, compilé par [Inno Setup](https://jrsoftware.org/isinfo.php)
(`ISCC.exe`, cherché aux emplacements usuels par `construire.py`). Installe
**par utilisateur**, jamais dans Program Files : c'est ce qui permet à Rubin
de proposer sa propre mise à jour en un clic, depuis la fenêtre
(`autoupdate.py`), sans jamais demander les droits administrateur.

`CloseApplications=force` et `RestartApplications=yes`, dans le `.iss`,
laissent l'installateur fermer et relancer Rubin lui-même via le Gestionnaire
de redémarrage de Windows, silencieusement (`/VERYSILENT /SUPPRESSMSGBOXES
/NORESTART /RESTARTAPPLICATIONS`).

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

⚠️ L'archive est en **Deflate** (`ZIP_DEFLATED`), pas en LZMA malgré une
archive presque deux fois plus grosse : ni l'explorateur Windows ni
`Expand-Archive` de PowerShell ne savent décompresser une méthode LZMA dans
un zip, seulement Deflate, la seule que le format garantit vraiment. Trouvé
le 5 août 2026 au soir, quand Maxime n'arrivait pas à extraire les trois
premières releases (v0.5.0 à v0.5.2), publiées avant ce correctif.

UPX n'est pas utilisé : le gain est faible et il déclenche des faux positifs
d'antivirus, ce qui coûterait bien plus cher que les méga-octets économisés.
