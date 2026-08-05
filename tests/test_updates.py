from __future__ import annotations

from typing import Any

import pytest
import requests

from chrono.updates import UpdateStatus, check_for_update, parse_version


class FakeResponse:
    def __init__(self, status: int, body: Any = None) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("pas de JSON")
        return self._body


def statut(current: str, latest: str, minimum: str) -> UpdateStatus:
    return UpdateStatus(current, latest, minimum, "https://exemple.test/telecharger")


class TestParseVersion:
    def test_compare_des_nombres_et_non_des_lettres(self) -> None:
        """Régression : « 0.10.0 » passait pour plus ancien que « 0.9.0 ».

        L'ordre alphabétique place « 1 » avant « 9 ». Une comparaison de
        chaînes rendrait donc la dixième version périmée face à la neuvième,
        et l'erreur ne se verrait qu'à la dixième version, longtemps après
        avoir été écrite.
        """
        assert parse_version("0.10.0") > parse_version("0.9.0")

    def test_survit_a_un_numero_incomprehensible(self) -> None:
        assert parse_version("inconnue") == (0,)


class TestUpdateStatus:
    def test_ne_dit_rien_quand_tout_va_bien(self) -> None:
        assert statut("0.1.0", "0.1.0", "0.1.0").message() is None

    def test_signale_une_version_plus_recente_sans_insister(self) -> None:
        message = statut("0.1.0", "0.2.0", "0.1.0").message()
        assert message is not None
        assert "disponible" in message
        assert "⚠" not in message  # une version dépassée fonctionne encore

    def test_avertit_quand_le_serveur_va_refuser(self) -> None:
        message = statut("0.1.0", "0.3.0", "0.2.0").message()
        assert message is not None
        assert "refusera" in message
        assert "https://" in message  # dire quoi faire, pas seulement quoi craindre

    def test_distingue_depasse_et_refuse(self) -> None:
        depasse = statut("0.1.0", "0.2.0", "0.1.0")
        refuse = statut("0.1.0", "0.2.0", "0.2.0")
        assert depasse.outdated and not depasse.rejected
        assert refuse.outdated and refuse.rejected


class TestCheckForUpdate:
    def test_ne_fait_rien_sans_serveur(self) -> None:
        assert check_for_update(None) is None

    def test_lit_la_reponse_du_serveur(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = {
            "derniere": "9.9.9",
            "minimale": "0.1.0",
            "telechargement": "https://exemple.test/z.zip",
        }
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(200, body))
        status = check_for_update("https://exemple.test")
        assert status is not None
        assert status.latest == "9.9.9"
        assert status.outdated

    @pytest.mark.parametrize(
        "reponse",
        [requests.ConnectionError("coupé"), FakeResponse(500), FakeResponse(200, None)],
    )
    def test_un_echec_ne_dit_rien_plutot_que_n_importe_quoi(
        self, monkeypatch: pytest.MonkeyPatch, reponse: Any
    ) -> None:
        # Savoir si une mise à jour existe est utile, mais jamais au point de
        # retarder une session ni d'inventer un avertissement.
        def fake_get(*_a: Any, **_k: Any) -> Any:
            if isinstance(reponse, Exception):
                raise reponse
            return reponse

        monkeypatch.setattr(requests, "get", fake_get)
        assert check_for_update("https://exemple.test") is None
