"""Ce que la recette d'empaquetage doit déclarer, vérifié depuis les tests.

⚠️ **Un exécutable qui se construit sans erreur ne contient pas forcément ce
qu'on croit.** C'est le défaut le plus coûteux de ce projet, rencontré deux
fois :

- `tkinter` mis dans les `excludes` de `rubin.spec` : l'exécutable se
  construisait, et ne contenait simplement jamais la fenêtre (#77) ;
- le dossier `src/rubin/interface/data` jamais déclaré dans `donnees` : les
  images du guide n'ont été dans **aucune** version publiée, et `help.py`
  garde le coup par un `chemin.is_file()`, donc rien ne l'a jamais dit.

Les deux se voient en lisant le fichier de recette, ce que ces tests font,
et aucun ne se voit en lançant la suite de tests ordinaire, qui tourne sur
les sources et non sur l'exécutable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
# `empaquetage` n'est pas un paquet installé : il vit à la racine du dépôt.
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))
SPEC = RACINE / "empaquetage" / "rubin.spec"
ISS = RACINE / "empaquetage" / "rubin.iss"
SOURCES = RACINE / "src" / "rubin"


def dossiers_de_donnees() -> list[Path]:
    """Tous les dossiers `data` du paquet, ceux qui doivent être déclarés."""
    return sorted(chemin for chemin in SOURCES.rglob("data") if chemin.is_dir())


def recette_sans_commentaires() -> str:
    """La recette privée de ses commentaires.

    ⚠️ **Indispensable, et découvert en piégeant ce test.** La première
    version cherchait le chemin dans le fichier entier : elle passait encore
    après avoir retiré la déclaration, parce qu'un commentaire voisin cite le
    même chemin en toutes lettres. Un test vert qui ne sait pas dire non ne
    prouve rien, et celui-ci gardait précisément le défaut qui a laissé
    passer le dossier manquant.
    """
    lignes = SPEC.read_text(encoding="utf-8").splitlines()
    return "\n".join(ligne for ligne in lignes if not ligne.lstrip().startswith("#"))


class TestDonneesDeclarees:
    def test_le_paquet_a_bien_des_dossiers_de_donnees(self) -> None:
        # Garde-fou du test suivant : une recherche qui ne trouve rien passerait
        # sinon pour un succès, et ce fichier entier ne vérifierait plus rien.
        assert dossiers_de_donnees()

    @pytest.mark.parametrize("dossier", dossiers_de_donnees(), ids=lambda p: p.parent.name)
    def test_chaque_dossier_de_donnees_est_declare(self, dossier: Path) -> None:
        """Régression : `src/rubin/interface/data` a manqué à `donnees` depuis
        toujours, découvert le 06/08/2026 en fouillant l'archive publiée. Les
        images du guide (`exemple-bandeau.png`, `exemple-suivi.png`) n'étaient
        dans aucun exécutable, et `help.py` affichait le texte sans rien dire,
        parce qu'il garde le coup par `chemin.is_file()`.

        Ce test tombe désormais dès qu'un dossier de données est ajouté sans
        être déclaré, c'est-à-dire avant que la version ne sorte, et non des
        mois après en fouillant un zip.
        """
        recette = recette_sans_commentaires()
        relatif = dossier.relative_to(RACINE / "src")
        # La destination telle que `donnees` l'écrit, entre guillemets : le
        # chemin source, lui, est épelé partie par partie par `Path`, donc
        # il ne se cherche pas comme une chaîne.
        attendu = '"' + "/".join(relatif.parts) + '"'
        assert attendu in recette, (
            f"{dossier} n'est pas déclaré dans rubin.spec : il ne sera PAS "
            f"dans l'exécutable, sans la moindre erreur de construction"
        )


class TestIcones:
    def test_licone_existe_la_ou_la_recette_la_cherche(self) -> None:
        assert (SOURCES / "interface" / "data" / "rubin.ico").is_file()

    def test_la_recette_de_lexecutable_pose_licone(self) -> None:
        recette = SPEC.read_text(encoding="utf-8")
        assert "icon=" in recette
        assert "rubin.ico" in recette

    def test_linstallateur_pose_la_meme_icone(self) -> None:
        """Régression : les deux se règlent à des endroits différents, et n'en
        régler qu'un laisse la moitié du chemin avec l'icône par défaut. Un
        testeur voit l'installateur AVANT l'exécutable."""
        assert "SetupIconFile=" in ISS.read_text(encoding="utf-8")

    def test_licone_porte_les_petites_tailles(self) -> None:
        """Windows pioche une taille différente selon l'endroit, et 16 px est
        celle de la barre de titre. Un `.ico` qui ne porterait que du 256
        laisserait Tk réduire lui-même, ce qui rend le diamant illisible :
        constaté en photographiant la barre de titre le 06/08/2026."""
        from PIL import Image

        with Image.open(SOURCES / "interface" / "data" / "rubin.ico") as icone:
            tailles = set(icone.info["sizes"])
        assert (16, 16) in tailles
        assert (32, 32) in tailles


class TestLogoDiscord:
    def test_le_logo_est_present_et_petit(self) -> None:
        """Le VRAI logo Discord, pas un dessin qui lui ressemble : demandé par
        Maxime le 06/08/2026, « avec l'icône Discord pas un truc dessiné ».
        Une marque approximative se lit comme une imitation."""
        from PIL import Image

        with Image.open(SOURCES / "interface" / "data" / "discord-logo.png") as logo:
            assert logo.size == (20, 20)
            assert logo.mode == "RGBA"


class TestVersionWindows:
    """Le numéro que Windows lit dans l'exécutable.

    ⚠️ **`VS_FIXEDFILEINFO` porte EXACTEMENT quatre entiers.** Ni plus ni
    moins, et le « plus » ne lève rien : trouvé le 07/08/2026, le passage du
    numéro de version à quatre nombres a fait produire un quintuplet
    `(0, 6, 3, 0, 0)` à l'ancienne écriture, qui complétait par un zéro. La
    construction n'a pas bronché, PyInstaller non plus, et Windows affichait
    le bon numéro parce que le cinquième était **tronqué en silence**.

    Compter sur une troncature silencieuse pour obtenir le bon résultat est
    exactement ce que ce projet refuse partout ailleurs.
    """

    def test_un_numero_a_quatre_nombres_passe_tel_quel(self) -> None:
        from empaquetage.construire import version_windows

        assert version_windows("0.6.3.0") == (0, 6, 3, 0)

    def test_un_numero_a_trois_nombres_est_complete(self) -> None:
        """Toutes les versions publiées avant le 07/08/2026 en ont trois."""
        from empaquetage.construire import version_windows

        assert version_windows("0.6.2") == (0, 6, 2, 0)

    def test_rend_toujours_quatre_nombres(self) -> None:
        """Régression du défaut lui-même : c'est le COMPTE qui casse, pas les
        valeurs, et c'est pour ça que personne ne l'a vu."""
        from empaquetage.construire import version_windows

        for numero in ("1", "0.6", "0.6.2", "0.6.3.0", "1.2.3.4.5"):
            assert len(version_windows(numero)) == 4, numero
