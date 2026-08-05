"""Construit l'exécutable Windows.

    python empaquetage/construire.py

Le résultat est un dossier `dist/rubin/` contenant `rubin.exe` et ses
dépendances, plus une archive prête à distribuer.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def main() -> int:
    python = sys.executable
    print("--- nettoyage")
    for dossier in ("build", "dist"):
        shutil.rmtree(RACINE / dossier, ignore_errors=True)

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
    archive = RACINE / "dist" / "rubin-windows.zip"
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
    (RACINE / "dist" / "rubin-windows.zip.sha256").write_text(
        f"{empreinte}  rubin-windows.zip" + "\n", encoding="utf-8"
    )
    print(f"--- {archive.stat().st_size / 1e6:.0f} Mo : {archive}")
    print(f"--- sha256 : {empreinte}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
