"""Construit l'exécutable Windows.

    python empaquetage/construire.py

Le résultat est un dossier `dist/rubin/` contenant `rubin.exe` et ses
dépendances, plus une archive prête à distribuer.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))
from rubin import __version__  # noqa: E402


def version_windows(version: str) -> tuple[int, int, int, int]:
    """Le numéro de version au format que Windows exige : EXACTEMENT quatre.

    `VS_FIXEDFILEINFO` porte quatre entiers de seize bits, ni plus ni moins.

    ⚠️ **Ce n'était pas le cas, et rien ne le disait.** L'ancienne écriture
    complétait par un zéro, `(*decoupe, 0)`, ce qui convenait aux versions à
    trois nombres. Le 07/08/2026, le passage à quatre nombres
    (`0.IMPORTANTE.SECONDAIRE.NÉGLIGEABLE`) lui en a fait produire **cinq** :
    `(0, 6, 3, 0, 0)`. La construction n'a pas bronché, PyInstaller non plus,
    et Windows a affiché « 0.6.3.0 » — juste, mais par chance, le cinquième
    nombre étant tronqué en silence.

    Compter sur une troncature silencieuse pour obtenir le bon résultat, c'est
    exactement ce que ce projet refuse ailleurs. Ici, le compte est fait
    explicitement : on complète par des zéros, et on coupe à quatre.
    """
    nombres = tuple(int(n) for n in version.split(".") if n.isdigit())
    complete = (*nombres, 0, 0, 0, 0)[:4]
    return (complete[0], complete[1], complete[2], complete[3])


def _ecrire_metadonnees() -> None:
    """Régénère `metadonnees.txt` avec le vrai numéro de version.

    Trouvé le 06/08/2026 : ce fichier portait encore « 0.4.0 » en dur, alors
    que `rubin.__version__` avait déjà dérivé jusqu'à 0.5.4 sans que personne
    ne le remarque, exactement le même défaut que `RUBIN_LATEST` côté
    serveur. Le régénérer à chaque construction, à partir de la même source
    que le nom de l'archive, ferme cette source d'oubli pour de bon plutôt
    que de la corriger une fois de plus.
    """
    quadruplet = version_windows(__version__)
    contenu = f"""# Métadonnées Windows de l'exécutable.
#
# Régénéré par construire.py à partir de rubin.__version__ : ne pas modifier
# à la main, la prochaine construction écraserait le changement.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={quadruplet!r},
    prodvers={quadruplet!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040C04B0',
        [
          StringStruct('CompanyName', 'Maxime Lacoste'),
          StringStruct('FileDescription', 'Rubin, chronomètre de quêtes pour Black Desert Online'),
          StringStruct('FileVersion', '{__version__}'),
          StringStruct('InternalName', 'rubin'),
          StringStruct('LegalCopyright', 'Copyright (c) 2026 Maxime Lacoste. Licence MIT.'),
          StringStruct('OriginalFilename', 'rubin.exe'),
          StringStruct('ProductName', 'Rubin'),
          StringStruct('ProductVersion', '{__version__}'),
        ],
      )
    ]),
    # 0x040C est le français, 1200 la page de codes Unicode.
    VarFileInfo([VarStruct('Translation', [0x040C, 1200])]),
  ],
)
"""
    (RACINE / "empaquetage" / "metadonnees.txt").write_text(contenu, encoding="utf-8")


def main() -> int:
    python = sys.executable
    print("--- nettoyage")
    for dossier in ("build", "dist"):
        shutil.rmtree(RACINE / dossier, ignore_errors=True)

    _ecrire_metadonnees()

    print("--- construction")
    # Ni l'interpréteur ni le chemin de la recette ne viennent de l'extérieur :
    # le premier est celui qui exécute ce script, le second est calculé à côté.
    resultat = subprocess.run(  # noqa: S603
        [
            python,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(RACINE / "empaquetage" / "rubin.spec"),
        ],
        cwd=RACINE,
        check=False,
    )
    if resultat.returncode != 0:
        return resultat.returncode

    cible = RACINE / "dist" / "rubin"
    poids = sum(f.stat().st_size for f in cible.rglob("*") if f.is_file())
    print(f"--- {poids / 1e6:.0f} Mo dans {cible}")

    print("--- archive")
    # ⚠️ ZIP_DEFLATED, jamais ZIP_LZMA. La LZMA rendait l'archive environ deux
    # fois plus petite, mais ni l'explorateur Windows ni `Expand-Archive` de
    # PowerShell ne savent décompresser une méthode LZMA dans un zip : ce sont
    # des outils natifs, limités à la compression Deflate du format, la seule
    # que le zip lui-même garantit. Trouvé le 5 août 2026 au soir, quand Maxime
    # n'arrivait pas à extraire les trois premières releases : l'explorateur
    # rendait « erreur non spécifiée » sur un fichier au hasard,
    # `Expand-Archive` était plus clair, « méthode de compression non prise en
    # charge ». Les trois releases publiées ce soir avant ce correctif, v0.5.0
    # à v0.5.2, sont donc illisibles par les outils Windows natifs.
    # Le numéro de version est dans le nom du fichier, pas seulement dans la
    # release GitHub qui le porte : un joueur qui a plusieurs zips dans ses
    # téléchargements ne peut sinon pas dire lequel est le plus récent sans
    # les ouvrir un par un.
    nom_archive = f"rubin-windows-{__version__}.zip"
    archive = RACINE / "dist" / nom_archive
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for fichier in sorted(cible.rglob("*")):
            if fichier.is_file():
                zf.write(fichier, fichier.relative_to(cible))
    # L'empreinte accompagne l'archive : elle ne calme aucun antivirus, mais
    # elle permet à qui le souhaite de vérifier que le fichier téléchargé est
    # bien celui qui a été construit ici.
    empreinte = hashlib.sha256(archive.read_bytes()).hexdigest()
    # Le format est celui de `sha256sum`, pour que la vérification soit une
    # commande et non un travail de comparaison à l'œil.
    (RACINE / "dist" / f"{nom_archive}.sha256").write_text(
        f"{empreinte}  {nom_archive}" + "\n", encoding="utf-8"
    )
    print(f"--- {archive.stat().st_size / 1e6:.0f} Mo : {archive}")
    print(f"--- sha256 : {empreinte}")

    print("--- installateur")
    iscc = _trouver_iscc()
    if iscc is None:
        # Ne fait pas échouer la construction : le zip seul reste un livrable
        # complet, et Inno Setup n'a aucune raison d'être posé sur un poste
        # de CI qui ne construit jamais l'exécutable.
        print("[rubin] Inno Setup introuvable, installateur non construit")
        return 0
    resultat = subprocess.run(  # noqa: S603
        [
            str(iscc),
            f"/DVersion={__version__}",
            str(RACINE / "empaquetage" / "rubin.iss"),
        ],
        cwd=RACINE,
        check=False,
    )
    if resultat.returncode != 0:
        return resultat.returncode
    installateur = RACINE / "dist" / f"rubin-installateur-{__version__}.exe"
    empreinte_installateur = hashlib.sha256(installateur.read_bytes()).hexdigest()
    (RACINE / "dist" / f"{installateur.name}.sha256").write_text(
        f"{empreinte_installateur}  {installateur.name}" + "\n", encoding="utf-8"
    )
    print(f"--- {installateur.stat().st_size / 1e6:.0f} Mo : {installateur}")
    print(f"--- sha256 : {empreinte_installateur}")
    return 0


def _trouver_iscc() -> Path | None:
    """Cherche le compilateur Inno Setup aux emplacements usuels.

    Installé par utilisateur (comme Rubin lui-même) ou par machine selon ce
    qu'a choisi qui l'a posé : les deux se rencontrent, donc les deux se
    cherchent, avant de renoncer.
    """
    candidats = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
    ]
    for candidat in candidats:
        if candidat.is_file():
            return candidat
    return None


if __name__ == "__main__":
    raise SystemExit(main())
