from __future__ import annotations

import json
from pathlib import Path

import pytest

from rubin.protocol import (
    MAX_SECONDS,
    PROTOCOL_VERSION,
    MeasurePayload,
    PlayerIdentity,
    SessionPayload,
    build_session,
)
from rubin.reading import BannerKind, BannerReading
from rubin.reference import Catalog
from rubin.timing import Timeline

JERON = "[Calpheon] Jeron, la tacticienne"
HARPIES = "[Calpheon] Cris stridents des harpies"


def lecture(kind: BannerKind, nom: str, score: float = 0.97) -> BannerReading:
    return BannerReading(kind=kind, quest_name=nom, confidence=score)


@pytest.fixture
def timeline(catalog: Catalog) -> Timeline:
    return Timeline(catalog=catalog)


class TestMeasurePayload:
    def test_juge_plausible_une_duree_normale(self) -> None:
        payload = MeasurePayload(quest="21136/1", seconds=42.5, quality="exacte", confidence=0.97)
        assert payload.is_plausible

    @pytest.mark.parametrize("seconds", [0.0, 0.5, MAX_SECONDS + 1, 86400.0])
    def test_ecarte_une_duree_invraisemblable(self, seconds: float) -> None:
        # Sous la seconde, aucune quête ne peut être acceptée puis rendue.
        # Au-delà de six heures, le joueur a laissé tourner en faisant autre
        # chose. Ni l'un ni l'autre n'est une durée de quête.
        payload = MeasurePayload(quest="21136/1", seconds=seconds, quality="exacte", confidence=0.9)
        assert not payload.is_plausible

    def test_ecarte_une_confiance_hors_bornes(self) -> None:
        payload = MeasurePayload(quest="21136/1", seconds=42.0, quality="exacte", confidence=1.5)
        assert not payload.is_plausible


class TestSessionPayload:
    def test_fait_l_aller_retour_en_json(self) -> None:
        # Client et serveur relisent la même définition : c'est le seul moyen
        # d'éviter des mesures acceptées puis mal interprétées.
        original = SessionPayload(
            player="abc123",
            language="fr",
            catalog_date="2026-08-05",
            measures=(MeasurePayload("21136/1", 42.5, "exacte", 0.97),),
        )
        relu = SessionPayload.from_dict(json.loads(original.to_json()))
        assert relu == original

    def test_porte_la_version_du_protocole(self) -> None:
        payload = SessionPayload(player="a", language="fr", catalog_date="2026-08-05")
        assert payload.protocol == PROTOCOL_VERSION

    def test_n_emporte_aucune_donnee_personnelle(self) -> None:
        """Régression : le lot ne doit contenir ni pseudonyme ni horaire.

        Le classement n'a besoin que de durées. Ce qu'on n'envoie pas ne peut
        ni fuiter, ni être exigé plus tard. Ce test échoue si un champ portant
        une date ou un nom est ajouté sans y avoir réfléchi.
        """
        champs = set(json.loads(SessionPayload("a", "fr", "2026-08-05").to_json()))
        assert champs == {
            "player",
            "language",
            "catalog_date",
            "measures",
            "protocol",
            "client",
            "dropped",
        }

    def test_une_mesure_ne_porte_pas_d_horodatage(self) -> None:
        mesure = json.loads(SessionPayload.to_json(
            SessionPayload("a", "fr", "2026-08-05", (MeasurePayload("1/1", 10.0, "exacte", 0.9),))
        ))["measures"][0]
        assert set(mesure) == {"quest", "seconds", "quality", "confidence"}


class TestBuildSession:
    def test_reprend_les_mesures_du_journal(self, timeline: Timeline) -> None:
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        timeline.record(lecture(BannerKind.COMPLETED, JERON), at=42.5)
        lot = build_session(timeline, player="abc", catalog_date="2026-08-05")
        assert len(lot.measures) == 1
        assert lot.measures[0].quest == "21136/1"
        assert lot.measures[0].seconds == pytest.approx(42.5)

    def test_ecarte_les_durees_invraisemblables(self, timeline: Timeline) -> None:
        # Le client filtre par honnêteté, pour ne pas polluer les médianes des
        # autres avec ses propres ratés. Le serveur refiltrera, lui, parce
        # qu'il ne peut faire confiance à aucun client.
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        timeline.record(lecture(BannerKind.COMPLETED, JERON), at=0.2)
        lot = build_session(timeline, player="abc", catalog_date="2026-08-05")
        assert lot.measures == ()
        assert lot.dropped == 1

    def test_compte_ensemble_les_pertes_du_journal_et_du_filtre(self, timeline: Timeline) -> None:
        # Un chiffre incomplet qui s'annonce reste utilisable.
        timeline.record(lecture(BannerKind.ACCEPTED, JERON), at=0.0)
        timeline.record(lecture(BannerKind.ACCEPTED, "[X] Inconnue"), at=10.0)
        timeline.record(lecture(BannerKind.ACCEPTED, HARPIES), at=20.0)
        lot = build_session(timeline, player="abc", catalog_date="2026-08-05")
        assert lot.dropped >= 1


class TestPlayerIdentity:
    def test_tire_un_identifiant_au_sort(self) -> None:
        assert len(PlayerIdentity().value) == 32

    def test_conserve_le_meme_identifiant_entre_deux_lancements(self, tmp_path: Path) -> None:
        chemin = tmp_path / "identite"
        premier = PlayerIdentity.load_or_create(chemin)
        assert PlayerIdentity.load_or_create(chemin).value == premier.value

    def test_reste_utilisable_si_le_disque_refuse(self, tmp_path: Path) -> None:
        # Mieux vaut compter le joueur deux fois que perdre ses mesures.
        impossible = tmp_path / "fichier" / "identite"
        impossible.parent.write_text("ceci est un fichier, pas un dossier", encoding="utf-8")
        assert len(PlayerIdentity.load_or_create(impossible).value) == 32
