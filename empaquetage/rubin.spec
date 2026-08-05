# Recette d'empaquetage de Rubin en exécutable Windows.
#
# Lancée par `empaquetage/construire.py`, jamais à la main : ce fichier suppose
# des chemins que le script calcule.
#
# Trois choses ne se devinent pas et doivent être déclarées ici, faute de quoi
# l'exécutable se construit sans erreur et échoue au premier lancement.
#
# 1. **Les modèles de reconnaissance**, seize méga-octets de fichiers `.onnx`
#    que RapidOCR charge par chemin et non par import. Aucun analyseur de
#    dépendances ne peut les voir.
# 2. **Sa configuration**, un `config.yaml` qui désigne ces modèles.
# 3. **Le gabarit de l'icône du bandeau**, notre propre donnée, chargée elle
#    aussi par chemin.
#
# Le mode retenu est un dossier et non un fichier unique. Un exécutable unique
# de cette taille se décompresse dans un dossier temporaire à chaque lancement,
# ce qui ajoute une dizaine de secondes d'attente avant le premier affichage,
# et certains antivirus voient d'un mauvais œil un binaire qui s'auto-extrait.

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

RACINE = Path(SPECPATH).parent
SITE = Path(SPECPATH).parent / ".venv" / "lib" / "site-packages"

donnees = [
    (str(SITE / "rapidocr_onnxruntime" / "models"), "rapidocr_onnxruntime/models"),
    (str(SITE / "rapidocr_onnxruntime" / "config.yaml"), "rapidocr_onnxruntime"),
    (str(RACINE / "src" / "rubin" / "capture" / "data"), "rubin/capture/data"),
]

# onnxruntime apporte des bibliothèques natives que l'analyse statique ne suit
# pas jusqu'au bout.
binaires = collect_dynamic_libs("onnxruntime")

a = Analysis(
    [str(RACINE / "empaquetage" / "point_entree.py")],
    pathex=[str(RACINE / "src")],
    binaries=binaires,
    datas=donnees,
    hiddenimports=[
        "rubin",
        "rubin.capture",
        "rubin.reading",
        "rubin.reference",
        # La fenêtre, importée à l'intérieur de `command_interface` et non en
        # tête de module. PyInstaller la suit très bien à travers le
        # `try/except ImportError`, mais un import différé reste moins visible
        # qu'un import de tête, et l'oubli aurait le même symptôme que
        # `tkinter` retiré d'`excludes` ci-dessous : silencieux jusqu'au
        # lancement.
        "rubin.interface",
        "rubin.interface.app",
    ],
    hookspath=[],
    runtime_hooks=[],
    # Rien de tout cela ne sert au chronomètre, et chacun pèse lourd. Les
    # écarter divise la taille finale par plus de deux.
    #
    # ⚠️ `tkinter` a longtemps été dans cette liste, et c'est pourquoi la
    # 0.4.0 publiée le 5 août 2026 ne contient pas la fenêtre : `excludes`
    # retire un module même quand du code le réclame, contrairement à un
    # import simplement jamais atteint par l'analyse statique. L'exécutable se
    # construisait sans erreur, et `rubin fenetre` échouait au premier
    # lancement avec « interface graphique indisponible ». Retiré ici sur
    # demande explicite de Maxime le 5 août au soir : la fenêtre doit
    # accompagner la prochaine version publiée.
    excludes=["matplotlib", "scipy", "pandas", "IPython", "pytest", "setuptools"],
    noarchive=False,
)

# Rien de ce qui suit n'est chargé par le chronomètre, et chacun pèse lourd.
# OpenCV emporte un décodeur vidéo de trente méga-octets et des détecteurs de
# visages, y compris dans sa variante « headless » : celle-ci retire l'interface
# graphique, pas la vidéo. Pillow emporte des décodeurs de formats d'image que
# nous n'ouvrons jamais, puisque tout vient de captures d'écran.
#
# Ces fichiers ne sont chargés qu'à l'usage de la fonction correspondante. Les
# retirer ne casse donc rien tant que personne n'ouvre de vidéo ni de fichier
# AVIF, ce que ce logiciel ne fait pas.
INUTILES = (
    "opencv_videoio_ffmpeg",
    "haarcascade",
    "_avif",
    "_webp",
    "opencv_world",
)


def sans_inutiles(entrees):
    return [e for e in entrees if not any(motif in e[0].lower() for motif in INUTILES)]


avant = len(a.binaries) + len(a.datas)
a.binaries = sans_inutiles(a.binaries)
a.datas = sans_inutiles(a.datas)
print(f"[rubin] {avant - len(a.binaries) - len(a.datas)} fichiers inutiles écartés")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="rubin",
    debug=False,
    strip=False,
    upx=False,  # UPX déclenche des faux positifs d'antivirus, pour peu de gain
    console=True,
    # Un binaire anonyme est doublement pénalisé : les antivirus s'en méfient
    # davantage, et la signature de code exige un nom de produit et une version.
    version=str(RACINE / "empaquetage" / "metadonnees.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="rubin",
)
