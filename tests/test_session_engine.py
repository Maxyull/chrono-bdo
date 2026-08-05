"""Le moteur de mesure, éprouvé sans écran ni réseau.

Rien ici ne capture l'écran ni ne joint le serveur : ce sont des fichiers qui
entrent et des envois simulés qui sortent. C'est justement ce qui rend
vérifiable ce qu'aucune session de jeu ne montrerait, à savoir ce qui se passe
quand la session n'est jamais close.

⚠️ Aucun de ces tests ne parle à `https://rubin.maxyull.fr`. La production reçoit
de vraies mesures, et un doublon injecté depuis un test fausserait ses médianes
pour de bon.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from rubin.failures import FailureStore
from rubin.interface import session as moteur
from rubin.interface.session import BLIND_AFTER, MeasuringSession
from rubin.protocol import MeasurePayload, SessionPayload
from rubin.reading import BannerKind, BannerReading
from rubin.reference import Catalog
from rubin.settings import Settings
from rubin.timing import Timeline
from rubin.upload import JOURNAL_SUFFIX, IncrementalSender, SessionJournal, UploadResult

JERON = "[Calpheon] Jeron, la tacticienne"
HARPIES = "[Calpheon] Cris stridents des harpies"
COUP_DE_MAIN = "[Calpheon] Coup de main tant desiré"

MESURE_1 = MeasurePayload(quest="21136/1", seconds=42.5, quality="exacte", confidence=0.97)
MESURE_2 = MeasurePayload(quest="21136/2", seconds=118.0, quality="exacte", confidence=0.94)


class Serveur:
    """Retient les lots présentés, sans jamais rien envoyer."""

    def __init__(self, réponse: UploadResult | None = None) -> None:
        self.lots: list[SessionPayload] = []
        self.réponse = réponse

    def __call__(
        self, payload: SessionPayload, url: str, *args: Any, **kwargs: Any
    ) -> UploadResult:
        self.lots.append(payload)
        if self.réponse is not None:
            return self.réponse
        return UploadResult(ok=True, detail="accepté", stored=len(payload.measures), answered=True)

    @property
    def quêtes_reçues(self) -> list[str]:
        return [m.quest for lot in self.lots for m in lot.measures]


class Journal:
    """Ce que le moteur a publié vers la fenêtre."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, Any]] = []

    def __call__(self, sujet: str, valeur: Any) -> None:
        self.messages.append((sujet, valeur))

    def états(self) -> list[str]:
        return [str(v) for s, v in self.messages if s == "etat"]


@pytest.fixture
def publie() -> Journal:
    return Journal()


def moteur_pour(
    tmp_path: Path, catalog: Catalog, publie: Journal, server: str | None = None
) -> MeasuringSession:
    return MeasuringSession(
        home=tmp_path,
        catalog=catalog,
        settings=Settings(),
        publish=publie,
        server=server,
    )


def journal_orphelin(tmp_path: Path, mesures: int = 2, envoyées: int = 0) -> Path:
    """Fabrique le journal d'une session que rien n'a close."""
    dossier = tmp_path / "sessions"
    dossier.mkdir(parents=True, exist_ok=True)
    entête = SessionPayload(player="abc123", language="fr", catalog_date="2026-08-05")
    journal = SessionJournal(dossier / f"session-1{JOURNAL_SUFFIX}", entête)
    for mesure in (MESURE_1, MESURE_2)[:mesures]:
        journal.record(mesure)
    if envoyées:
        journal.mark_sent(envoyées)
    return journal.path


class TestJournalDeSession:
    def test_ouvre_un_journal_des_le_demarrage(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        journal, _ = moteur_pour(tmp_path, catalog, publie)._open_journal()
        assert journal is not None
        assert journal.path.suffix == JOURNAL_SUFFIX
        assert journal.path.exists()

    def test_sans_serveur_rien_n_est_jamais_envoye(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        # Transmettre les données de quelqu'un sans qu'il l'ait demandé serait
        # une décision prise à sa place. Le journal, lui, reste local.
        journal, envoyeur = moteur_pour(tmp_path, catalog, publie)._open_journal()
        assert journal is not None
        assert envoyeur is None


class TestRepriseDUneSessionInterrompue:
    def test_relit_et_envoie_ce_qui_n_etait_jamais_parti(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serveur = Serveur()
        monkeypatch.setattr(moteur, "send_session", serveur)
        chemin = journal_orphelin(tmp_path, mesures=2, envoyées=0)

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._replay_now([chemin])

        assert serveur.quêtes_reçues == ["21136/1", "21136/2"]
        assert not chemin.exists()

    def test_ne_renvoie_pas_ce_qui_etait_deja_parti(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression : reprendre une session plantée ne doit rien compter deux fois.

        Le cas réel : le joueur mesure deux quêtes, la première part au fil de
        l'eau, puis Windows redémarre. Au démarrage suivant, envoyer le journal
        entier ferait recevoir 21136/1 une seconde fois. Elle gonflerait
        `samples` et entrerait deux fois dans la médiane, sans que rien ne
        distingue le doublon d'une vraie mesure.
        """
        serveur = Serveur()
        monkeypatch.setattr(moteur, "send_session", serveur)
        chemin = journal_orphelin(tmp_path, mesures=2, envoyées=1)

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._replay_now([chemin])

        assert serveur.quêtes_reçues == ["21136/2"]

    def test_remet_la_session_interrompue_au_format_normal(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(moteur, "send_session", Serveur())
        chemin = journal_orphelin(tmp_path)

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._replay_now([chemin])

        lot = chemin.with_suffix(".json")
        assert lot.exists()
        assert '"21136/1"' in lot.read_text(encoding="utf-8")

    def test_sans_serveur_le_journal_reste_et_le_dit(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serveur = Serveur()
        monkeypatch.setattr(moteur, "send_session", serveur)
        chemin = journal_orphelin(tmp_path)

        moteur_pour(tmp_path, catalog, publie)._replay_now([chemin])

        assert serveur.lots == []
        assert chemin.exists()
        assert any("session interrompue" in m for m in publie.états())

    def test_un_serveur_qui_repond_une_erreur_laisse_le_journal_en_place(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Le serveur a répondu, donc il n'a rien enregistré : réessayer plus
        # tard ne peut fabriquer aucun doublon.
        refus = Serveur(UploadResult(ok=False, detail="refusé (503) : maintenance", answered=True))
        monkeypatch.setattr(moteur, "send_session", refus)
        chemin = journal_orphelin(tmp_path)

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._replay_now([chemin])

        assert chemin.exists()

    def test_un_serveur_muet_ne_laisse_pas_le_journal_repartir(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sort inconnu : le lot a pu arriver. Le journal disparaît, la copie
        # complète en JSON reste. Une mesure peut-être perdue vaut mieux qu'une
        # mesure peut-être inventée.
        muet = Serveur(UploadResult(ok=False, detail="serveur injoignable", answered=False))
        monkeypatch.setattr(moteur, "send_session", muet)
        chemin = journal_orphelin(tmp_path)

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._replay_now([chemin])

        assert not chemin.exists()
        assert chemin.with_suffix(".json").exists()

    def test_un_journal_illisible_est_mis_de_cote_et_non_efface(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(moteur, "send_session", Serveur())
        dossier = tmp_path / "sessions"
        dossier.mkdir(parents=True)
        chemin = dossier / f"session-9{JOURNAL_SUFFIX}"
        chemin.write_text("ceci n'est pas du JSON\n", encoding="utf-8")

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._replay_now([chemin])

        assert not chemin.exists()
        assert (dossier / f"session-9{JOURNAL_SUFFIX}.illisible").exists()

    def test_un_journal_deja_entierement_envoye_disparait(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serveur = Serveur()
        monkeypatch.setattr(moteur, "send_session", serveur)
        chemin = journal_orphelin(tmp_path, mesures=2, envoyées=2)

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._replay_now([chemin])

        assert serveur.lots == []
        assert not chemin.exists()

    def test_ne_reprend_pas_le_journal_de_la_session_en_cours(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        # Le relevé est fait avant que le journal de cette session existe, et un
        # journal écrit à l'instant n'est de toute façon pas tenu pour orphelin.
        journal_orphelin(tmp_path)
        moteur_pour(tmp_path, catalog, publie)._replay_orphans()
        assert (tmp_path / "sessions" / f"session-1{JOURNAL_SUFFIX}").exists()


def journal_de_deux_quetes(catalog: Catalog) -> Timeline:
    ligne = Timeline(catalog=catalog)
    for kind, nom, instant in (
        (BannerKind.ACCEPTED, JERON, 0.0),
        (BannerKind.COMPLETED, JERON, 42.5),
        (BannerKind.ACCEPTED, HARPIES, 50.0),
        (BannerKind.COMPLETED, HARPIES, 168.0),
    ):
        ligne.record(BannerReading(kind=kind, quest_name=nom, confidence=0.96), at=instant)
    return ligne


class TestBilanDeFin:
    def test_n_envoie_a_l_arret_que_ce_qui_n_est_pas_deja_parti(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        """Régression : l'arrêt ne doit pas renvoyer la session entière.

        Le cas réel que l'envoi au fil de l'eau introduit : les mesures partent
        après chaque quête terminée, puis le joueur ferme la fenêtre. L'ancien
        bilan de fin envoyait le lot ENTIER, donc une seconde fois tout ce qui
        venait de partir. Deux heures de jeu auraient doublé toutes leurs
        mesures d'un coup, et la médiane de chaque quête aurait absorbé le
        doublon sans que rien ne le signale.
        """
        serveur = Serveur()
        ligne = journal_de_deux_quetes(catalog)
        entête = SessionPayload(player="abc123", language="fr", catalog_date="2026-08-05")
        envoyeur = IncrementalSender("https://exemple.invalide", entête, send=serveur)
        envoyeur.flush([MESURE_1, MESURE_2])  # les deux sont déjà parties
        assert serveur.quêtes_reçues == ["21136/1", "21136/2"]

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._finish(
            ligne, 168.0, None, envoyeur
        )

        assert serveur.quêtes_reçues == ["21136/1", "21136/2"]
        assert any("déjà envoyé au fil de l'eau" in m for m in publie.états())

    def test_envoie_a_l_arret_la_quete_que_le_reseau_avait_ratee(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        serveur = Serveur()
        ligne = journal_de_deux_quetes(catalog)
        entête = SessionPayload(player="abc123", language="fr", catalog_date="2026-08-05")
        envoyeur = IncrementalSender("https://exemple.invalide", entête, send=serveur)
        envoyeur.flush([MESURE_1])

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._finish(
            ligne, 168.0, None, envoyeur
        )

        assert serveur.quêtes_reçues == ["21136/1", "21136/2"]

    def test_ecrit_le_lot_complet_et_efface_le_journal(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        ligne = journal_de_deux_quetes(catalog)
        entête = SessionPayload(player="abc123", language="fr", catalog_date="2026-08-05")
        journal = SessionJournal(tmp_path / "sessions" / f"session-1{JOURNAL_SUFFIX}", entête)
        journal.record(MESURE_1)

        moteur_pour(tmp_path, catalog, publie)._finish(ligne, 168.0, journal, None)

        assert not journal.path.exists()
        lots = list((tmp_path / "sessions").glob("session-*.json"))
        assert len(lots) == 1
        assert '"21136/2"' in lots[0].read_text(encoding="utf-8")

    def test_une_session_sans_mesure_n_ecrit_aucun_lot(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        entête = SessionPayload(player="abc123", language="fr", catalog_date="2026-08-05")
        journal = SessionJournal(tmp_path / "sessions" / f"session-1{JOURNAL_SUFFIX}", entête)

        moteur_pour(tmp_path, catalog, publie)._finish(Timeline(catalog=catalog), 12.0, journal)

        assert not journal.path.exists()
        assert list((tmp_path / "sessions").glob("*.json")) == []
        assert any("aucune quête mesurée" in m for m in publie.états())

    def test_sans_journal_le_lot_entier_part_comme_avant(
        self, tmp_path: Path, catalog: Catalog, publie: Journal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Journal indisponible : rien n'est parti pendant la session, donc le
        # lot entier peut partir sans risque de doublon.
        serveur = Serveur()
        monkeypatch.setattr(moteur, "send_session", serveur)

        moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")._finish(
            journal_de_deux_quetes(catalog), 168.0, None, None
        )

        assert serveur.quêtes_reçues == ["21136/1", "21136/2"]


class TestEnvoiSansBlocage:
    def test_l_envoi_ne_tourne_jamais_sur_le_fil_de_mesure(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        """Régression : un serveur lent ne doit faire rater aucun bandeau.

        Le cas réel qu'il faut éviter : `send_session` attend jusqu'à trente
        secondes une réponse. Appelé depuis la boucle de mesure, il cesserait de
        regarder l'écran pendant tout ce temps, et un bandeau apparu dans
        l'intervalle serait perdu en silence. C'est exactement le défaut que la
        capture différée a corrigé, et le réintroduire par l'envoi serait un
        comble.
        """
        import threading

        parti = threading.Event()
        relâché = threading.Event()

        def lent(payload: SessionPayload, url: str) -> UploadResult:
            parti.set()
            relâché.wait(timeout=5.0)
            return UploadResult(ok=True, detail="accepté", stored=1, answered=True)

        entête = SessionPayload(player="abc123", language="fr", catalog_date="2026-08-05")
        envoyeur = IncrementalSender("https://exemple.invalide", entête, send=lent)
        session = moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")

        session._send_apart(envoyeur, [MESURE_1], 0)
        assert parti.wait(timeout=5.0)  # l'envoi court ailleurs
        assert envoyeur.sent == 0  # et l'appelant n'a rien attendu

        relâché.set()
        assert session._sending is not None
        session._sending.join(timeout=5.0)
        assert envoyeur.sent == 1

    def test_un_seul_envoi_a_la_fois(
        self, tmp_path: Path, catalog: Catalog, publie: Journal
    ) -> None:
        import threading

        relâché = threading.Event()
        appels = []

        def lent(payload: SessionPayload, url: str) -> UploadResult:
            appels.append(payload)
            relâché.wait(timeout=5.0)
            return UploadResult(ok=True, detail="accepté", stored=1, answered=True)

        entête = SessionPayload(player="abc123", language="fr", catalog_date="2026-08-05")
        envoyeur = IncrementalSender("https://exemple.invalide", entête, send=lent)
        session = moteur_pour(tmp_path, catalog, publie, "https://exemple.invalide")

        session._send_apart(envoyeur, [MESURE_1], 0)
        session._send_apart(envoyeur, [MESURE_1, MESURE_2], 0)  # abandonné, le premier court
        relâché.set()
        assert session._sending is not None
        session._sending.join(timeout=5.0)
        assert len(appels) == 1


class TestGardeAAveugle:
    """Le câblage : quand la session garde une image, et surtout quand non."""

    def _session(self, tmp_path: Path) -> tuple[MeasuringSession, list[tuple[str, object]]]:
        messages: list[tuple[str, object]] = []
        session = MeasuringSession(
            home=tmp_path,
            catalog=None,  # type: ignore[arg-type]
            settings=Settings(),
            publish=lambda genre, charge: messages.append((genre, charge)),
        )
        return session, messages

    def _guetteur(self) -> object:
        class Guetteur:
            last_frame = np.full((115, 349), 83, dtype=np.uint8)

        return Guetteur()

    def test_rien_n_est_garde_pendant_le_silence_ordinaire(self, tmp_path: Path) -> None:
        # Un trajet ou un combat, c'est du silence normal. Garder des images là
        # remplirait le dossier de preuves de rien.
        session, _messages = self._session(tmp_path)
        magasin = FailureStore(tmp_path / "echecs")

        garde = session._keep_if_blind(
            self._guetteur(),  # type: ignore[arg-type]
            magasin,
            last_banner=time.monotonic() - 30.0,
            started=time.monotonic() - 30.0,
            last_kept=None,
        )

        assert garde is None
        assert not list((tmp_path / "echecs").glob("*.webp"))

    def test_une_image_est_gardee_apres_un_silence_long(self, tmp_path: Path) -> None:
        session, messages = self._session(tmp_path)
        magasin = FailureStore(tmp_path / "echecs")

        garde = session._keep_if_blind(
            self._guetteur(),  # type: ignore[arg-type]
            magasin,
            last_banner=None,
            started=time.monotonic() - (BLIND_AFTER + 5.0),
            last_kept=None,
        )

        assert garde is not None
        assert len(list((tmp_path / "echecs").glob("*.webp"))) == 1
        # Et le joueur l'apprend : une image gardée en douce ne sert que celui
        # qui sait déjà qu'elle existe.
        assert any("gardée dans echecs/" in str(charge) for _genre, charge in messages)

    def test_regression_une_session_aveugle_n_ecrit_pas_huit_images_par_seconde(
        self, tmp_path: Path
    ) -> None:
        """Régression attendue : l'espacement, sans lequel le remède est pire.

        Le silence dure des minutes entières, et la boucle tourne huit fois par
        seconde. Sans délai entre deux gardes, la session du 5 août 2026 aurait
        écrit plus de vingt mille lignes de journal en une heure, pour la même
        image. L'empreinte évite le doublon sur le DISQUE, pas la ligne de
        journal ni le message à l'écran.
        """
        session, messages = self._session(tmp_path)
        magasin = FailureStore(tmp_path / "echecs")
        garde = time.monotonic()

        for _ in range(50):
            garde = session._keep_if_blind(  # type: ignore[assignment]
                self._guetteur(),  # type: ignore[arg-type]
                magasin,
                last_banner=None,
                started=time.monotonic() - (BLIND_AFTER + 5.0),
                last_kept=garde,
            )

        assert messages == []
