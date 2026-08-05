# Recette d'empaquetage de Chrono en exécutable Windows.
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
    (str(RACINE / "src" / "chrono" / "capture" / "data"), "chrono/capture/data"),
]

# onnxruntime apporte des bibliothèques natives que l'analyse statique ne suit
# pas jusqu'au bout.
binaires = collect_dynamic_libs("onnxruntime")

a = Analysis(
    [str(RACINE / "empaquetage" / "point_entree.py")],
    pathex=[str(RACINE / "src")],
    binaries=binaires,
    datas=donnees,
    hiddenimports=["chrono", "chrono.capture", "chrono.reading", "chrono.reference"],
    hookspath=[],
    runtime_hooks=[],
    # Rien de tout cela ne sert au chronomètre, et chacun pèse lourd. Les
    # écarter divise la taille finale par plus de deux.
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "setuptools"],
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
print(f"[chrono] {avant - len(a.binaries) - len(a.datas)} fichiers inutiles écartés")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="chrono",
    debug=False,
    strip=False,
    upx=False,  # UPX déclenche des faux positifs d'antivirus, pour peu de gain
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="chrono",
)
