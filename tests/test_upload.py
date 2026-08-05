"""Écriture au fil de l'eau, et envoi incrémental.

Ces tests couvrent le seul risque réel de ce chantier, et il vaut la peine de
l'écrire en tête de fichier : **le double comptage**. Une mesure reçue deux fois
par le serveur gonfle `samples` et entre deux fois dans la médiane, et rien ne
la distingue de deux mesures réelles. C'est le chiffre faux qui n'en ressort
jamais.

Le principe du projet s'applique ici tel quel : rater une mesure donne un
chiffre incomplet, en inventer une donne un chiffre faux.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rubin import upload
from rubin.protocol import MeasurePayload, SessionPayload
from rubin.upload import (
    JOURNAL_SUFFIX,
    IncrementalSender,
    SessionJournal,
    UploadResult,
    orphan_journals,
    read_journal,
    send_session,
)

#: De vraies quêtes de la chaîne 21136, celle que Maxime a mesurée en jeu.
JERON = MeasurePayload(quest="21136/1", seconds=42.5, quality="exacte", confidence=0.97)
HARPIES = MeasurePayload(quest="21136/2", seconds=118.0, quality="deduite", confidence=0.94)
COUP_DE_MAIN = MeasurePayload(quest="21136/3", seconds=73.25, quality="exacte", confidence=0.96)


def entete(player: str = "abc123") -> SessionPayload:
    return SessionPayload(player=player, language="fr", catalog_date="2026-08-05")


class Serveur:
    """Un serveur de test qui retient tout ce qu'on lui présente.

    Il ne part sur aucun réseau, et c'est délibéré : la production reçoit de
    vraies mesures, et un doublon injecté depuis un test fausserait des médianes
    pour de bon.
    """

    def __init__(self, réponse: UploadResult | None = None) -> None:
        self.lots: list[SessionPayload] = []
        self.réponse = réponse

    def __call__(self, payload: SessionPayload, url: str) -> UploadResult:
        self.lots.append(payload)
        if self.réponse is not None:
            return self.réponse
        return UploadResult(ok=True, detail="accepté", stored=len(payload.measures), answered=True)

    @property
    def quêtes_reçues(self) -> list[str]:
        return [m.quest for lot in self.lots for m in lot.measures]


class TestJournalAuFilDeLEau:
    def test_ecrit_une_ligne_par_mesure_des_qu_elle_existe(self, tmp_path: Path) -> None:
        journal = SessionJournal(tmp_path / f"session-1{JOURNAL_SUFFIX}", entete())
        journal.record(JERON)
        journal.record(HARPIES)
        lignes = journal.path.read_text(encoding="utf-8").splitlines()
        assert len(lignes) == 3  # l'en-tête, puis une ligne par mesure
        assert json.loads(lignes[0])["kind"] == "session"
        assert [json.loads(ligne)["quest"] for ligne in lignes[1:]] == ["21136/1", "21136/2"]

    def test_se_relit_avec_l_entete_de_la_session(self, tmp_path: Path) -> None:
        journal = SessionJournal(tmp_path / f"session-1{JOURNAL_SUFFIX}", entete("def456"))
        journal.record(JERON)
        contenu = read_journal(journal.path)
        assert contenu is not None
        assert contenu.payload.player == "def456"
        assert contenu.payload.catalog_date == "2026-08-05"
        assert contenu.payload.measures == (JERON,)

    def test_une_session_tuee_en_pleine_ecriture_garde_tout_le_reste(
        self, tmp_path: Path
    ) -> None:
        """Régression : deux heures de jeu ne doivent pas tenir à une ligne coupée.

        Le cas réel visé par tout ce chantier : le processus est tué, Windows
        redémarre, ou le logiciel plante. Aucun événement de fermeture n'arrive,
        et la dernière ligne du journal reste à moitié écrite. Refuser le
        fichier entier pour elle reviendrait à perdre la session que ce journal
        existe précisément pour sauver, et une partie ne se rejoue pas.
        """
        chemin = tmp_path / f"session-1{JOURNAL_SUFFIX}"
        journal = SessionJournal(chemin, entete())
        journal.record(JERON)
        journal.record(HARPIES)
        with chemin.open("a", encoding="utf-8") as fichier:
            fichier.write('{"kind": "measure", "quest": "21136/3", "sec')  # tuée ici

        contenu = read_journal(chemin)
        assert contenu is not None
        assert [m.quest for m in contenu.payload.measures] == ["21136/1", "21136/2"]

    def test_sans_entete_le_journal_n_est_pas_relu(self, tmp_path: Path) -> None:
        chemin = tmp_path / f"session-1{JOURNAL_SUFFIX}"
        chemin.write_text('{"kind": "measure", "quest": "21136/1", "seconds": 42.5,'
                          ' "quality": "exacte", "confidence": 0.97}\n', encoding="utf-8")
        # Sans en-tête, on ne sait ni de qui ni de quand vient cette mesure :
        # l'envoyer serait l'attribuer au hasard.
        assert read_journal(chemin) is None

    def test_un_journal_absent_ne_leve_pas(self, tmp_path: Path) -> None:
        assert read_journal(tmp_path / "jamais-ecrit.jsonl") is None

    def test_un_dossier_qui_refuse_ne_fait_pas_echouer_la_mesure(self, tmp_path: Path) -> None:
        # Le journal est un filet de sécurité : le perdre est un moindre mal
        # devant perdre la session elle-même.
        obstacle = tmp_path / "sessions"
        obstacle.write_text("ceci est un fichier, pas un dossier", encoding="utf-8")
        journal = SessionJournal(obstacle / f"session-1{JOURNAL_SUFFIX}", entete())
        journal.record(JERON)
        assert journal.broken

    def test_garde_le_plus_grand_nombre_de_mesures_perdues(self, tmp_path: Path) -> None:
        journal = SessionJournal(tmp_path / f"session-1{JOURNAL_SUFFIX}", entete())
        journal.record(JERON, dropped=1)
        journal.record(HARPIES, dropped=3)
        contenu = read_journal(journal.path)
        assert contenu is not None
        assert contenu.payload.dropped == 3

    def test_efface_le_journal_quand_la_session_est_close(self, tmp_path: Path) -> None:
        journal = SessionJournal(tmp_path / f"session-1{JOURNAL_SUFFIX}", entete())
        journal.record(JERON)
        journal.discard()
        assert not journal.path.exists()


class TestOrphelins:
    def test_trouve_les_journaux_restes_en_place(self, tmp_path: Path) -> None:
        for nom in ("session-2.jsonl", "session-1.jsonl"):
            (tmp_path / nom).write_text("", encoding="utf-8")
        assert [p.name for p in orphan_journals(tmp_path)] == [
            "session-1.jsonl",
            "session-2.jsonl",
        ]

    def test_ne_confond_pas_un_lot_final_avec_un_journal(self, tmp_path: Path) -> None:
        (tmp_path / "session-1.json").write_text("{}", encoding="utf-8")
        assert orphan_journals(tmp_path) == []

    def test_un_journal_ecrit_a_l_instant_n_est_pas_orphelin(self, tmp_path: Path) -> None:
        """Régression : deux Rubin ouverts ne doivent pas se voler leur journal.

        Rien n'empêche d'ouvrir la fenêtre deux fois. Le second Rubin verrait
        alors le journal VIVANT du premier comme un orphelin, en renverrait les
        mesures, et le premier renverrait les siennes à l'arrêt : les deux
        curseurs s'ignorant, la même mesure partirait deux fois. Un journal
        qu'on vient d'écrire n'appartient à personne d'autre.
        """
        frais = tmp_path / "session-1.jsonl"
        frais.write_text("", encoding="utf-8")
        assert orphan_journals(tmp_path, min_age=60.0) == []
        # Le même fichier, une heure plus tard, est bien un orphelin.
        vieux = frais.stat().st_mtime + 3600
        assert orphan_journals(tmp_path, min_age=60.0, now=vieux) == [frais]

    def test_un_dossier_inexistant_ne_leve_pas(self, tmp_path: Path) -> None:
        assert orphan_journals(tmp_path / "jamais-cree") == []


class TestEnvoiIncremental:
    def test_n_envoie_que_les_mesures_nouvelles(self, tmp_path: Path) -> None:
        serveur = Serveur()
        envoyeur = IncrementalSender("https://exemple.invalide", entete(), send=serveur)
        envoyeur.flush([JERON])
        envoyeur.flush([JERON, HARPIES])
        assert [lot.measures for lot in serveur.lots] == [(JERON,), (HARPIES,)]

    def test_un_envoi_repete_n_envoie_pas_deux_fois_la_meme_mesure(self) -> None:
        """Régression : le double comptage, le seul chiffre faux de ce chantier.

        Le cas réel : une session de deux heures envoie après chaque quête
        terminée. À la trentième quête, un envoi du lot ENTIER ferait recevoir
        au serveur la première mesure trente fois. Elle gonflerait `samples`,
        entrerait trente fois dans la médiane de la quête 21136/1, et rien ne la
        distinguerait de trente mesures réelles : la correction serait
        impossible, faute même de savoir qu'il y a quelque chose à corriger.

        Rater une mesure donne un chiffre incomplet. En inventer une donne un
        chiffre faux.
        """
        serveur = Serveur()
        envoyeur = IncrementalSender("https://exemple.invalide", entete(), send=serveur)
        mesures = [JERON, HARPIES, COUP_DE_MAIN]
        for combien in (1, 2, 3, 3, 3):
            envoyeur.flush(mesures[:combien])
        assert serveur.quêtes_reçues == ["21136/1", "21136/2", "21136/3"]
        assert len(serveur.quêtes_reçues) == len(set(serveur.quêtes_reçues))

    def test_ne_presente_rien_quand_il_n_y_a_rien_de_neuf(self) -> None:
        serveur = Serveur()
        envoyeur = IncrementalSender("https://exemple.invalide", entete(), send=serveur)
        envoyeur.flush([JERON])
        assert envoyeur.flush([JERON]) is None
        assert len(serveur.lots) == 1

    def test_un_serveur_qui_repond_une_erreur_laisse_la_mesure_en_attente(self) -> None:
        # Le serveur a répondu : il n'a rien enregistré, donc réessayer ne peut
        # fabriquer aucun doublon.
        refus = Serveur(UploadResult(ok=False, detail="refusé (503)", answered=True))
        envoyeur = IncrementalSender("https://exemple.invalide", entete(), send=refus)
        envoyeur.flush([JERON])
        assert envoyeur.sent == 0
        envoyeur.flush([JERON, HARPIES])
        assert refus.quêtes_reçues == ["21136/1", "21136/1", "21136/2"]

    def test_un_serveur_muet_ne_fait_jamais_reessayer(self) -> None:
        """Régression : une réponse perdue ne doit pas devenir un doublon.

        Le serveur peut avoir enregistré le lot puis voir sa réponse se perdre,
        et rien ne permet de le savoir depuis le client. Réessayer fabriquerait
        peut-être une mesure ; ne pas réessayer en perd peut-être une. Le lot
        complet reste sur le disque, donc la perte se rattrape et le doublon,
        lui, ne se rattraperait jamais.
        """
        muet = Serveur(UploadResult(ok=False, detail="serveur injoignable", answered=False))
        envoyeur = IncrementalSender("https://exemple.invalide", entete(), send=muet)
        envoyeur.flush([JERON])
        envoyeur.flush([JERON, HARPIES])
        assert muet.quêtes_reçues == ["21136/1", "21136/2"]

    def test_les_mesures_perdues_partent_en_ecart_et_non_en_total(self) -> None:
        # Sans quoi le serveur additionnerait plusieurs fois le même total.
        serveur = Serveur()
        envoyeur = IncrementalSender("https://exemple.invalide", entete(), send=serveur)
        envoyeur.flush([JERON], dropped=2)
        envoyeur.flush([JERON, HARPIES], dropped=5)
        assert [lot.dropped for lot in serveur.lots] == [2, 3]

    def test_garde_l_identite_et_la_date_du_referentiel(self) -> None:
        serveur = Serveur()
        envoyeur = IncrementalSender("https://exemple.invalide", entete("xyz"), send=serveur)
        envoyeur.flush([JERON])
        assert serveur.lots[0].player == "xyz"
        assert serveur.lots[0].catalog_date == "2026-08-05"

    def test_marque_dans_le_journal_ce_qui_est_parti(self, tmp_path: Path) -> None:
        journal = SessionJournal(tmp_path / f"session-1{JOURNAL_SUFFIX}", entete())
        journal.record(JERON)
        envoyeur = IncrementalSender(
            "https://exemple.invalide", entete(), send=Serveur(), journal=journal
        )
        envoyeur.flush([JERON])
        contenu = read_journal(journal.path)
        assert contenu is not None
        assert contenu.sent == 1
        assert contenu.unsent.measures == ()


class TestRepriseApresPlantage:
    def test_ne_reprend_que_ce_qui_n_est_jamais_parti(self, tmp_path: Path) -> None:
        """Régression : reprendre un journal ne doit rien renvoyer deux fois.

        Le cas réel : le joueur enchaîne trois quêtes, les deux premières
        partent au fil de l'eau, puis Windows redémarre. Au démarrage suivant,
        relire le journal en entier renverrait 21136/1 et 21136/2, déjà
        enregistrées. Le curseur écrit dans le journal est ce qui l'en empêche.
        """
        journal = SessionJournal(tmp_path / f"session-1{JOURNAL_SUFFIX}", entete())
        journal.record(JERON)
        journal.record(HARPIES)
        journal.mark_sent(2)
        journal.record(COUP_DE_MAIN)  # mesurée, jamais envoyée : le plantage suit

        contenu = read_journal(journal.path)
        assert contenu is not None
        assert len(contenu.payload.measures) == 3
        assert [m.quest for m in contenu.unsent.measures] == ["21136/3"]

    def test_un_curseur_plus_grand_que_le_journal_ne_rend_pas_tout(self, tmp_path: Path) -> None:
        # Une marque écrite puis un journal tronqué avant elle : borner le
        # curseur évite un reste négatif, qui se lirait « tout reste à envoyer ».
        chemin = tmp_path / f"session-1{JOURNAL_SUFFIX}"
        journal = SessionJournal(chemin, entete())
        journal.record(JERON)
        journal.mark_sent(7)
        contenu = read_journal(chemin)
        assert contenu is not None
        assert contenu.sent == 1
        assert contenu.unsent.measures == ()

    def test_le_reste_ne_recompte_pas_les_pertes_deja_transmises(self, tmp_path: Path) -> None:
        journal = SessionJournal(tmp_path / f"session-1{JOURNAL_SUFFIX}", entete())
        journal.record(JERON, dropped=2)
        journal.mark_sent(1, dropped=2)
        journal.record(HARPIES, dropped=5)
        contenu = read_journal(journal.path)
        assert contenu is not None
        assert contenu.unsent.dropped == 3


class Réponse:
    """Ce que `requests` rend, réduit à ce que `send_session` en lit."""

    def __init__(self, status_code: int, body: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self._body = body

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("réponse illisible")
        return self._body


class TestReponseDuServeur:
    def test_un_lot_accepte_est_compte(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            upload.requests,
            "post",
            lambda *a, **k: Réponse(200, {"enregistrees": 3, "refusees": 1}),
        )
        résultat = send_session(entete(), "https://exemple.invalide")
        assert (résultat.ok, résultat.stored, résultat.refused) == (True, 3, 1)
        assert résultat.answered

    def test_une_reponse_meme_en_erreur_reste_une_reponse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `answered` ne dit pas que ça a marché : il dit qu'on SAIT ce que le
        # serveur a fait du lot, ce qui est la condition d'un réessai sans
        # doublon.
        monkeypatch.setattr(
            upload.requests, "post", lambda *a, **k: Réponse(413, {"detail": "trop de mesures"})
        )
        résultat = send_session(entete(), "https://exemple.invalide")
        assert not résultat.ok
        assert résultat.answered
        assert "trop de mesures" in résultat.detail

    def test_un_serveur_injoignable_n_a_rien_repondu(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def tombe(*args: Any, **kwargs: Any) -> Réponse:
            raise upload.requests.ConnectionError("nom de domaine introuvable")

        monkeypatch.setattr(upload.requests, "post", tombe)
        résultat = send_session(entete(), "https://exemple.invalide")
        assert not résultat.ok
        assert not résultat.answered
