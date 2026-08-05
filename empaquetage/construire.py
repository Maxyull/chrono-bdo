"""Construit l'exécutable Windows.

    python empaquetage/construire.py

Le résultat est un dossier `dist/chrono/` contenant `chrono.exe` et ses
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
            str(RACINE / "empaquetage" / "chrono.spec"),
        ],
        cwd=RACINE,
        check=False,
    )
    if resultat.returncode != 0:
        return resultat.returncode

    cible = RACINE / "dist" / "chrono"
    poids = sum(f.stat().st_size for f in cible.rglob("*") if f.is_file())
    print(f"--- {poids / 1e6:.0f} Mo dans {cible}")

    print("--- archive")
    # LZMA plutôt que la compression par défaut du zip : sur des binaires de
    # cette taille, elle rend une archive environ deux fois plus petite, pour
    # quelques dizaines de secondes de plus à la construction. C'est ce que les
    # gens téléchargent, donc c'est là que le poids compte le plus.
    archive = RACINE / "dist" / "chrono-windows.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_LZMA) as zf:
        for fichier in sorted(cible.rglob("*")):
            if fichier.is_file():
                zf.write(fichier, fichier.relative_to(cible))
    # L'empreinte accompagne l'archive : elle ne calme aucun antivirus, mais
    # elle permet à qui le souhaite de vérifier que le fichier téléchargé est
    # bien celui qui a été construit ici.
    empreinte = hashlib.sha256(archive.read_bytes()).hexdigest()
    # Le format est celui de `sha256sum`, pour que la vérification soit une
    # commande et non un travail de comparaison à l'œil.
    (RACINE / "dist" / "chrono-windows.zip.sha256").write_text(
        f"{empreinte}  chrono-windows.zip" + "\n", encoding="utf-8"
    )
    print(f"--- {archive.stat().st_size / 1e6:.0f} Mo : {archive}")
    print(f"--- sha256 : {empreinte}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
