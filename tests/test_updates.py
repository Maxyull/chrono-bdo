from __future__ import annotations

import pathlib
from typing import Any

import pytest
import requests

from rubin.updates import (
    IMPORTANT,
    NEGLIGEABLE,
    SECONDAIRE,
    UPDATE_HEADLINES,
    UpdateStatus,
    check_for_update,
    parse_version,
    update_importance,
)


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

    def test_une_mise_a_jour_secondaire_ne_crie_pas(self) -> None:
        """Le troisième chiffre bouge : affichage et confort. Recommandée,
        jamais annoncée comme une alerte.

        ⚠️ Le mot « disponible » a disparu le 07/08/2026, et c'est le sujet
        même du changement. Demandé par Maxime : « il faut afficher mise à
        jour importante, secondaires, pas du tout importante ». Répéter
        « une version est disponible » du même ton pour un changement de
        reconnaissance et pour un mot corrigé use l'avertissement : le jour
        où il compte, plus personne ne le lit."""
        message = statut("0.6.2.0", "0.6.3.0", "0.1.0").message()
        assert message is not None
        assert "secondaire" in message
        assert "⚠" not in message  # une version dépassée fonctionne encore

    def test_une_mise_a_jour_importante_le_dit_et_dit_pourquoi(self) -> None:
        """Le deuxième chiffre bouge : la reconnaissance a changé. Le message
        dit ce qu'un joueur RISQUE, pas ce qui a changé dans le code : « OCR »
        ne veut rien dire pour lui, « vos mesures peuvent être fausses » si."""
        message = statut("0.6.2.0", "0.7.0.0", "0.1.0").message()
        assert message is not None
        assert "IMPORTANTE" in message
        assert "fausses" in message
        assert "⚠" in message

    def test_une_mise_a_jour_negligeable_ne_reclame_rien(self) -> None:
        message = statut("0.6.2.0", "0.6.2.1", "0.1.0").message()
        assert message is not None
        assert "rien qui presse" in message
        assert "⚠" not in message

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


class TestImportanceDesMisesAJour:
    """Le niveau d'une mise à jour se lit dans son NUMÉRO.

    Le barème a été fixé par Maxime le 07/08/2026 : « on va passer en 0.X.X.X
    pour ajouter le dernier chiffre maj vraiment pas importante ».

        0 . IMPORTANTE . SECONDAIRE . NÉGLIGEABLE

    ⚠️ **Aucun champ « importance » n'est servi par le serveur, et c'est
    voulu.** Un champ à côté du numéro pourrait annoncer « mineure » sur une
    version qui change la reconnaissance, et rien ne le rattraperait. Ici,
    publier une version dont le deuxième chiffre bouge EST l'annonce : les
    deux ne peuvent pas se contredire parce qu'ils sont la même chose.
    """

    def test_le_deuxieme_chiffre_est_important(self) -> None:
        assert update_importance("0.6.2.0", "0.7.0.0") == IMPORTANT

    def test_le_troisieme_chiffre_est_secondaire(self) -> None:
        assert update_importance("0.6.2.0", "0.6.3.0") == SECONDAIRE

    def test_le_quatrieme_chiffre_est_negligeable(self) -> None:
        assert update_importance("0.6.2.0", "0.6.2.1") == NEGLIGEABLE

    def test_le_passage_en_1_0_est_important(self) -> None:
        """Le premier rang vaut 0 aujourd'hui, mais le jour où Rubin passera
        en 1.0, ce ne sera pas une broutille."""
        assert update_importance("0.9.9.9", "1.0.0.0") == IMPORTANT

    def test_les_anciennes_versions_a_trois_chiffres_se_comparent_quand_meme(self) -> None:
        """Régression : toutes les versions publiées avant le 07/08/2026 n'ont
        que trois chiffres. Un joueur en 0.6.2 face à une 0.6.2.1 ne doit pas
        voir une alerte parce que les longueurs diffèrent : les manquants
        valent zéro, donc les deux ne diffèrent qu'au quatrième rang."""
        assert update_importance("0.6.2", "0.6.2.1") == NEGLIGEABLE
        assert update_importance("0.6.2", "0.6.3.0") == SECONDAIRE
        assert update_importance("0.6.2", "0.7.0.0") == IMPORTANT

    def test_cest_le_PREMIER_chiffre_qui_differe_qui_tranche(self) -> None:
        """Une version qui change à la fois le deuxième et le quatrième rang
        est importante, pas négligeable : le plus grave gagne, et il est
        toujours à gauche."""
        assert update_importance("0.6.2.0", "0.7.9.9") == IMPORTANT

    def test_deux_versions_identiques_ne_reclament_rien(self) -> None:
        # `UpdateStatus.importance` filtre déjà ce cas par `outdated`, mais la
        # fonction doit rester honnête si on l'appelle directement.
        assert update_importance("0.6.2.0", "0.6.2.0") == NEGLIGEABLE

    def test_le_statut_ne_rend_aucun_niveau_quand_tout_est_a_jour(self) -> None:
        assert statut("0.6.2.0", "0.6.2.0", "0.1.0").importance is None

    def test_chaque_niveau_a_sa_propre_phrase(self) -> None:
        """Trois niveaux qui se liraient pareil ne serviraient à rien."""
        assert len(set(UPDATE_HEADLINES.values())) == 3


class TestBaremeEtDocumentationDaccord:
    """Le barème vit à deux endroits : le code et `docs/versionnage.md`.

    Deux endroits finissent toujours par diverger, et celui-ci divergerait en
    silence : la doc est ce que Maxime relit pour rédiger une annonce Discord,
    le code est ce que le joueur voit dans sa fenêtre. Les deux se
    contredisant, l'annonce et la fenêtre diraient des choses différentes de
    la même version.
    """

    CHEMIN = pathlib.Path(__file__).resolve().parents[1] / "docs" / "versionnage.md"

    def test_la_doc_existe(self) -> None:
        # Garde-fou : un fichier déplacé rendrait les tests suivants verts
        # sans rien vérifier.
        assert self.CHEMIN.is_file()

    @pytest.mark.parametrize("niveau", [IMPORTANT, SECONDAIRE, NEGLIGEABLE])
    def test_chaque_phrase_du_code_est_dans_la_doc(self, niveau: str) -> None:
        """Régression : la phrase montrée au joueur et celle écrite dans la
        doc doivent être la MÊME, pas deux reformulations voisines."""
        doc = self.CHEMIN.read_text(encoding="utf-8")
        assert UPDATE_HEADLINES[niveau] in doc, (
            f"la phrase du niveau {niveau} n'est pas dans docs/versionnage.md : "
            "l'annonce Discord et la fenêtre diraient deux choses différentes"
        )

    def test_la_doc_annonce_les_quatre_rangs(self) -> None:
        doc = self.CHEMIN.read_text(encoding="utf-8")
        assert "0.IMPORTANTE.SECONDAIRE.NÉGLIGEABLE" in doc

    def test_la_doc_donne_le_gabarit_des_annonces(self) -> None:
        """Demandé par Maxime le 07/08/2026 : le barème « doit être expliqué
        aussi sur Discord, et lors des sorties release Discord et GitHub ».
        Un barème que seul le code connaît ne sert à personne au moment de
        rédiger l'annonce."""
        doc = self.CHEMIN.read_text(encoding="utf-8")
        assert "Sur la release GitHub" in doc
        assert "Sur Discord" in doc
