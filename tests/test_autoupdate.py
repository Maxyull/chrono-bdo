"""Télécharge et lance l'installateur d'une mise à jour, en un clic.

Demandé par Maxime le 06/08/2026, après `updates.py`, qui se contentait de
comparer deux numéros. Le seul risque réel de ce module : exécuter un fichier
corrompu ou mal reçu avec les mêmes droits que Rubin. Ces tests vérifient donc
surtout que l'empreinte est prise au sérieux, jamais contournée.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from rubin.autoupdate import download_installer, installer_url, launch_installer


class FakeResponse:
    def __init__(self, content: bytes = b"", text: str = "", status: int = 200) -> None:
        self.content = content
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class TestInstallerUrl:
    def test_construit_l_adresse_depuis_la_version(self) -> None:
        url = installer_url("0.5.5")

        assert url == (
            "https://github.com/Maxyull/rubin-bdo/releases/download/"
            "v0.5.5/rubin-installateur-0.5.5.exe"
        )


class TestDownloadInstaller:
    def test_ecrit_le_fichier_quand_l_empreinte_correspond(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contenu = b"faux installateur"
        empreinte = hashlib.sha256(contenu).hexdigest()

        def fake_get(url: str, **_kwargs: Any) -> FakeResponse:
            if url.endswith(".sha256"):
                return FakeResponse(text=f"{empreinte}  rubin-installateur-0.5.5.exe")
            return FakeResponse(content=contenu)

        monkeypatch.setattr(requests, "get", fake_get)
        cible = tmp_path / "installateur.exe"

        assert download_installer("0.5.5", cible) is True
        assert cible.read_bytes() == contenu

    def test_refuse_d_ecrire_si_l_empreinte_ne_correspond_pas(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression du risque central de ce module : un fichier reçu intact,
        au sens TLS, n'est pas forcément le bon fichier. Une construction
        interrompue ou une release mal publiée ne doivent jamais être
        exécutées silencieusement.
        """

        fausse_empreinte = "0" * 64

        def fake_get(url: str, **_kwargs: Any) -> FakeResponse:
            if url.endswith(".sha256"):
                return FakeResponse(text=f"{fausse_empreinte}  x")
            return FakeResponse(content=b"contenu inattendu")

        monkeypatch.setattr(requests, "get", fake_get)
        cible = tmp_path / "installateur.exe"

        assert download_installer("0.5.5", cible) is False
        assert not cible.exists()

    def test_rend_false_sur_une_panne_reseau(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_get(*_a: Any, **_k: Any) -> FakeResponse:
            raise requests.ConnectionError("coupé")

        monkeypatch.setattr(requests, "get", fake_get)

        assert download_installer("0.5.5", tmp_path / "installateur.exe") is False

    def test_rend_false_si_le_fichier_sha256_est_vide(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Cas réel possible : une release publiée sans son fichier .sha256.
        # Une empreinte vide ne doit jamais se comparer par accident à une
        # vérification bâclée qui l'accepterait.
        def fake_get(url: str, **_kwargs: Any) -> FakeResponse:
            if url.endswith(".sha256"):
                return FakeResponse(text="")
            return FakeResponse(content=b"peu importe")

        monkeypatch.setattr(requests, "get", fake_get)

        assert download_installer("0.5.5", tmp_path / "installateur.exe") is False


class TestLaunchInstaller:
    def test_lance_l_installateur_avec_les_indicateurs_silencieux(self, tmp_path: Path) -> None:
        installateur = tmp_path / "rubin-installateur-0.5.5.exe"

        with patch("rubin.autoupdate.subprocess.Popen") as popen:
            launch_installer(installateur)

        appel = popen.call_args
        commande = appel.args[0]
        assert commande[0] == str(installateur)
        assert "/VERYSILENT" in commande
        assert "/SUPPRESSMSGBOXES" in commande
        # Windows ne doit jamais redémarrer, seule l'application est
        # relancée : les deux indicateurs ne se confondent pas.
        assert "/NORESTART" in commande
        # ⛔ /RELANCER depuis le 07/08/2026 : la relance ne passe plus par le
        # Gestionnaire de redémarrage, qui ne la faisait pas. Voir
        # tests/test_relance.py et empaquetage/rubin.iss.
        assert "/RELANCER" in commande

    def test_ne_bloque_pas_en_attendant_l_installateur(self, tmp_path: Path) -> None:
        """Régression attendue : `Popen`, jamais `run` ni `call`. Attendre la
        fin de l'installateur bloquerait le fil de Tk, puisque c'est
        l'installateur qui va fermer Rubin lui-même.
        """
        installateur = tmp_path / "rubin-installateur-0.5.5.exe"
        faux_processus = MagicMock()

        with patch("rubin.autoupdate.subprocess.Popen", return_value=faux_processus) as popen:
            launch_installer(installateur)

        popen.assert_called_once()
        faux_processus.wait.assert_not_called()
