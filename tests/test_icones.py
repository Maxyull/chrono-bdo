"""Les images de la fenêtre, et ce qui arrive quand elles manquent.

⚠️ **Elles manquent pour de vrai chez des joueurs.** Tout exécutable publié
avant le 07/08/2026 ne contient pas `rubin/interface/data` du tout : le
dossier n'était déclaré nulle part dans `rubin.spec`, voir
`test_empaquetage.py`. Un joueur qui n'a pas encore mis à jour tourne donc
exactement dans ce cas, et une fenêtre qui refuserait de s'ouvrir faute
d'icône échangerait un défaut cosmétique contre une panne.

Aucune fenêtre n'est ouverte ici, même idiome que
`test_interface_app_threading.py` : un porteur minimal avec les seuls
attributs que la méthode lit. Les chemins qui touchent réellement à Tk sont
remplacés, ce qui rend ces tests exécutables en intégration continue, où
`tk.Tk()` plante faute d'écran.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from rubin.interface import app as module_app
from rubin.interface.app import RubinApp


class _RacineFactice:
    """Le `tk.Tk` réduit à ce que `_load_icons` lui demande."""

    def __init__(self, casse: bool = False) -> None:
        self.icones: list[str] = []
        self._casse = casse

    def iconbitmap(self, default: str) -> None:
        if self._casse:
            raise module_app.tk.TclError("bitmap non pris en charge ici")
        self.icones.append(default)


class _Porteur:
    """Le strict nécessaire que `_load_icons` et `_image` lisent sur `self`."""

    def __init__(self, racine: _RacineFactice) -> None:
        self.root = racine
        self._discord_logo: Any = None

    def _image(self, nom: str) -> Any:
        # La vraie méthode, appelée sur ce porteur : c'est bien le code de
        # `RubinApp` qu'on éprouve, pas une imitation.
        return RubinApp._image(self, nom)  # type: ignore[arg-type]


class TestImageManquante:
    def test_une_image_absente_rend_none_sans_lever(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Régression : c'est l'état de tout exécutable publié avant le
        07/08/2026, dont le dossier `data` n'a jamais été empaqueté."""
        monkeypatch.setattr(module_app, "DATA", tmp_path)

        assert RubinApp._image(_Porteur(_RacineFactice()), "absente.png") is None  # type: ignore[arg-type]

    def test_une_image_presente_est_chargee(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "logo.png").write_bytes(b"pas vraiment un png")
        monkeypatch.setattr(module_app, "DATA", tmp_path)
        vus: list[str] = []
        monkeypatch.setattr(
            module_app.tk, "PhotoImage", lambda file: vus.append(file) or "image"
        )

        rendu = RubinApp._image(_Porteur(_RacineFactice()), "logo.png")  # type: ignore[arg-type]

        assert rendu == "image"
        assert vus == [str(tmp_path / "logo.png")]

    def test_un_fichier_illisible_rend_none_sans_lever(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Régression : le fichier est là mais Tk le refuse, un PNG tronqué
        par un téléchargement interrompu par exemple. Même arbitrage que
        l'absence : on se passe de l'image, jamais de la fenêtre."""
        (tmp_path / "logo.png").write_bytes(b"tronque")
        monkeypatch.setattr(module_app, "DATA", tmp_path)

        def refuse(file: str) -> Any:
            raise module_app.tk.TclError("format d'image inconnu")

        monkeypatch.setattr(module_app.tk, "PhotoImage", refuse)

        assert RubinApp._image(_Porteur(_RacineFactice()), "logo.png") is None  # type: ignore[arg-type]


class TestPoseDeLIcone:
    def test_pose_le_ico_quand_il_est_la(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "rubin.ico").write_bytes(b"pas vraiment un ico")
        monkeypatch.setattr(module_app, "DATA", tmp_path)
        monkeypatch.setattr(module_app.tk, "PhotoImage", lambda file: "image")
        racine = _RacineFactice()

        RubinApp._load_icons(_Porteur(racine))  # type: ignore[arg-type]

        assert racine.icones == [str(tmp_path / "rubin.ico")]

    def test_sans_ico_la_fenetre_souvre_quand_meme(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Régression, l'état réel de tout exécutable publié avant le
        07/08/2026 : le dossier `data` n'y est pas, donc pas d'icône. La
        fenêtre doit s'ouvrir sans, sans lever et sans se plaindre."""
        monkeypatch.setattr(module_app, "DATA", tmp_path)
        racine = _RacineFactice()
        porteur = _Porteur(racine)

        RubinApp._load_icons(porteur)  # type: ignore[arg-type]

        assert racine.icones == []
        assert porteur._discord_logo is None

    def test_un_tk_qui_refuse_le_ico_nempeche_pas_la_fenetre(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`iconbitmap` n'accepte le format `.ico` que sous Windows. Ailleurs,
        il lève, et une exception ici tomberait dans le constructeur, donc
        avant le moindre composant : pas de fenêtre du tout, pour une icône."""
        (tmp_path / "rubin.ico").write_bytes(b"pas vraiment un ico")
        monkeypatch.setattr(module_app, "DATA", tmp_path)
        monkeypatch.setattr(module_app.tk, "PhotoImage", lambda file: "image")

        RubinApp._load_icons(_Porteur(_RacineFactice(casse=True)))  # type: ignore[arg-type]

    def test_le_logo_discord_est_charge_pour_len_tete(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`_build_header` construit le bouton Discord juste après, et lit
        `_discord_logo` : le charger plus tard donnerait un bouton sans son
        logo, sans erreur, ce qui est précisément le genre de silence que ce
        projet traque."""
        (tmp_path / "discord-logo.png").write_bytes(b"pas vraiment un png")
        monkeypatch.setattr(module_app, "DATA", tmp_path)
        monkeypatch.setattr(module_app.tk, "PhotoImage", lambda file: "logo")
        porteur = _Porteur(_RacineFactice())

        RubinApp._load_icons(porteur)  # type: ignore[arg-type]

        assert porteur._discord_logo == "logo"


class TestLisibiliteDuIco:
    """Le `.ico` livré doit rester lisible aux petites tailles.

    ⚠️ Régression datée. La première icône posée dans ce dépôt était un seul
    dessin de 256 px que Pillow redimensionnait vers les six autres tailles.
    Le trait de la marque est un filaire fin : le redimensionnement le
    moyenne avec le fond sombre, et la marque s'éteint à mesure qu'elle
    rétrécit. Mesuré sur le fichier d'alors, pic de luminance par taille :

        256 → 255    64 → 255    32 → 211    16 → **131**

    Soit exactement là où Windows la montre le plus, barre des tâches et vue
    en liste de l'explorateur, un pâté sombre. Le générateur rend désormais
    chaque taille séparément, en épaississant le trait avant de réduire.

    Ce test échoue sur l'ancien fichier à 16, 24 et 32 px. Il ne juge pas le
    dessin, seulement qu'il reste visible.
    """

    CHEMIN = Path(__file__).resolve().parents[1] / "src/rubin/interface/data/rubin.ico"
    PIC_MINIMAL = 230

    def test_chaque_taille_du_ico_reste_visible(self) -> None:
        Image = pytest.importorskip("PIL.Image", reason="Pillow arrive avec l'extra capture")

        with Image.open(self.CHEMIN) as ico:
            tailles = sorted(ico.ico.sizes())

        assert tailles, "le .ico ne déclare aucune taille"

        pics: dict[int, int] = {}
        for largeur, _ in tailles:
            with Image.open(self.CHEMIN) as image:
                image.size = (largeur, largeur)
                image.load()
                pics[largeur] = max(
                    max(pixel) for pixel in image.convert("RGB").get_flattened_data()
                )

        eteintes = {t: p for t, p in pics.items() if p < self.PIC_MINIMAL}
        assert not eteintes, (
            f"tailles trop sombres pour être lues : {eteintes} "
            f"(pic minimal exigé {self.PIC_MINIMAL}, mesures complètes {pics})"
        )

    def test_le_ico_porte_les_sept_tailles_attendues(self) -> None:
        """Windows en choisit une différente selon l'endroit : en manquer une
        le renvoie à un redimensionnement à la volée, ce que ce dépôt a déjà
        payé une fois."""
        Image = pytest.importorskip("PIL.Image", reason="Pillow arrive avec l'extra capture")

        with Image.open(self.CHEMIN) as ico:
            tailles = {largeur for largeur, _ in ico.ico.sizes()}

        assert tailles == {16, 24, 32, 48, 64, 128, 256}
