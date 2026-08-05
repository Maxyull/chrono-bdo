"""Le record personnel local, lu dans les sessions déjà écrites sur ce poste.

Répond à une demande explicite de Maxime, une fois le meilleur temps connu
affiché pendant la partie (#72) : voir aussi SON PROPRE record sur la quête en
cours, jamais reçu du serveur qui ne garde rien par joueur (voir
`references.py`). Ces tests couvrent le seul risque réel de ce module : rater
un fichier ne doit jamais faire disparaître le reste de l'historique, et une
mesure implausible glissée dans un fichier ne doit jamais devenir un record.
"""

from __future__ import annotations

from pathlib import Path

from rubin.history import personal_best
from rubin.protocol import MeasurePayload, SessionPayload
from rubin.reference import QuestId
from rubin.upload import JOURNAL_SUFFIX, SessionJournal

#: De vraies quêtes de la chaîne 21136, celle que Maxime a mesurée en jeu.
JERON = QuestId(21136, 1)
HARPIES = QuestId(21136, 2)


def écrire_session(dossier: Path, nom: str, mesures: list[MeasurePayload]) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    payload = SessionPayload(
        player="abc123", language="fr", catalog_date="2026-08-05", measures=tuple(mesures)
    )
    (dossier / nom).write_text(payload.to_json(), encoding="utf-8")


class TestPersonalBest:
    def test_rend_la_seconde_de_la_seule_mesure_connue(self, tmp_path: Path) -> None:
        écrire_session(
            tmp_path / "sessions",
            "session-1.json",
            [MeasurePayload(quest="21136/1", seconds=42.5, quality="exacte", confidence=0.97)],
        )

        assert personal_best(tmp_path, JERON) == 42.5

    def test_rend_none_pour_une_quete_jamais_faite(self, tmp_path: Path) -> None:
        écrire_session(
            tmp_path / "sessions",
            "session-1.json",
            [MeasurePayload(quest="21136/1", seconds=42.5, quality="exacte", confidence=0.97)],
        )

        assert personal_best(tmp_path, HARPIES) is None

    def test_rend_none_quand_le_dossier_sessions_n_existe_pas_encore(
        self, tmp_path: Path
    ) -> None:
        # Un joueur qui vient d'installer Rubin n'a encore rien mesuré : le
        # dossier lui-même n'existe pas, ce n'est pas une panne à signaler.
        assert personal_best(tmp_path, JERON) is None


class TestToleranceAuxFichiersAbimes:
    def test_ignore_un_fichier_illisible_sans_perdre_le_reste(self, tmp_path: Path) -> None:
        """Cas réel visé par `upload.read_journal` : un processus tué en pleine
        écriture laisse un fichier tronqué. Le refuser en bloc ferait perdre le
        record d'une session par ailleurs valide, ce qui reviendrait à inventer
        une absence là où une mesure existe.
        """
        dossier = tmp_path / "sessions"
        dossier.mkdir()
        (dossier / "session-cassee.json").write_text("{ceci n'est pas du json", encoding="utf-8")
        écrire_session(
            dossier,
            "session-2.json",
            [MeasurePayload(quest="21136/1", seconds=20.0, quality="exacte", confidence=0.9)],
        )

        assert personal_best(tmp_path, JERON) == 20.0

    def test_ignore_une_mesure_hors_des_bornes_plausibles(self, tmp_path: Path) -> None:
        # Une durée de 0,1 s ne peut être qu'une double lecture ou un fichier
        # trafiqué : la laisser entrer produirait un record faux, pire qu'un
        # record absent.
        écrire_session(
            tmp_path / "sessions",
            "session-1.json",
            [MeasurePayload(quest="21136/1", seconds=0.1, quality="exacte", confidence=0.9)],
        )

        assert personal_best(tmp_path, JERON) is None


class TestRegression:
    def test_deux_passages_de_la_meme_quete_le_record_est_le_plus_rapide(
        self, tmp_path: Path
    ) -> None:
        """Jéron faite deux fois, sur deux sessions, à 42,5 s puis 31,8 s : le
        record personnel affiché doit être 31,8 s, le meilleur essai, jamais le
        premier ni une moyenne. C'est exactement la demande de Maxime, « Ton
        meilleur temps », pas « ton dernier temps ».
        """
        écrire_session(
            tmp_path / "sessions",
            "session-1.json",
            [MeasurePayload(quest="21136/1", seconds=42.5, quality="exacte", confidence=0.97)],
        )
        écrire_session(
            tmp_path / "sessions",
            "session-2.json",
            [MeasurePayload(quest="21136/1", seconds=31.8, quality="deduite", confidence=0.94)],
        )

        assert personal_best(tmp_path, JERON) == 31.8

    def test_voit_le_record_d_une_session_interrompue_jamais_fermee(
        self, tmp_path: Path
    ) -> None:
        """Une session tuée en plein jeu (plantage, redémarrage Windows) ne
        laisse qu'un journal `.jsonl`, jamais transformé en `.json` puisque la
        fermeture normale n'a jamais eu lieu. Si le record personnel ignorait
        ces journaux, un joueur verrait « jamais mesurée » pour une quête qu'il
        a pourtant faite, plus vite que son record affiché : un chiffre qui
        ignore une mesure réelle sans le dire, exactement ce que ce projet
        interdit.
        """
        entête = SessionPayload(player="abc123", language="fr", catalog_date="2026-08-05")
        journal = SessionJournal(
            tmp_path / "sessions" / f"session-1{JOURNAL_SUFFIX}", entête
        )
        journal.record(
            MeasurePayload(quest="21136/1", seconds=15.0, quality="exacte", confidence=0.9)
        )

        assert personal_best(tmp_path, JERON) == 15.0
