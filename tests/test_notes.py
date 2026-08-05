"""Les notes personnelles du joueur sur une quête.

Répond à une demande explicite de Maxime le 05/08/2026 au soir : de quoi
noter, à côté d'une quête, le monstre à tuer, l'instance, le choix pris à un
carrefour, ou un mot ou un nombre relevé dans le chat. Ces tests couvrent le
même risque que `history.py` : un fichier absent ou abîmé ne doit jamais
empêcher Rubin de démarrer, et une clé mal formée ne doit jamais faire
disparaître les autres notes.
"""

from __future__ import annotations

from pathlib import Path

from rubin.notes import load_notes, save_note
from rubin.reference import QuestId

#: De vraies quêtes de la chaîne 21136, celle que Maxime a mesurée en jeu.
JERON = QuestId(21136, 1)
HARPIES = QuestId(21136, 2)


class TestSaveEtLoad:
    def test_une_note_ecrite_se_relit_identique(self, tmp_path: Path) -> None:
        save_note(tmp_path, JERON, "tuer 3 harpies avant le PNJ")

        assert load_notes(tmp_path) == {JERON: "tuer 3 harpies avant le PNJ"}

    def test_rend_un_dictionnaire_vide_quand_rien_n_a_ete_ecrit(self, tmp_path: Path) -> None:
        # Un joueur qui vient d'installer Rubin n'a encore rien noté : le
        # fichier lui-même n'existe pas, ce n'est pas une panne à signaler.
        assert load_notes(tmp_path) == {}

    def test_une_note_vide_efface_la_note_existante(self, tmp_path: Path) -> None:
        save_note(tmp_path, JERON, "un premier essai")
        save_note(tmp_path, JERON, "   ")

        assert load_notes(tmp_path) == {}

    def test_deux_quetes_gardent_chacune_leur_propre_note(self, tmp_path: Path) -> None:
        save_note(tmp_path, JERON, "note de Jéron")
        save_note(tmp_path, HARPIES, "note des Harpies")

        assert load_notes(tmp_path) == {
            JERON: "note de Jéron",
            HARPIES: "note des Harpies",
        }


class TestToleranceAuxFichiersAbimes:
    def test_ignore_un_fichier_qui_n_est_pas_du_json(self, tmp_path: Path) -> None:
        (tmp_path / "notes.json").write_text("{ceci n'est pas du json", encoding="utf-8")

        assert load_notes(tmp_path) == {}

    def test_ignore_une_cle_qui_n_est_pas_chaine_position(self, tmp_path: Path) -> None:
        # Un fichier modifié à la main, ou d'un format futur : la clé lisible
        # doit survivre, la clé illisible doit simplement disparaître.
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes.json").write_text(
            '{"pas-un-identifiant": "texte", "21136/1": "vraie note"}',
            encoding="utf-8",
        )

        assert load_notes(tmp_path) == {JERON: "vraie note"}

    def test_ignore_une_valeur_qui_n_est_pas_du_texte(self, tmp_path: Path) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes.json").write_text('{"21136/1": 42}', encoding="utf-8")

        assert load_notes(tmp_path) == {}


class TestRegression:
    def test_reecrire_une_note_ne_perd_pas_les_autres(self, tmp_path: Path) -> None:
        """Cas réel visé : `save_note` relit puis réécrit le fichier entier
        (voir sa docstring). Une implémentation qui écrirait un objet à une
        seule clé, au lieu de fusionner avec l'existant, effacerait en
        silence toutes les notes déjà prises sur les autres quêtes.
        """
        save_note(tmp_path, JERON, "note de Jéron")

        save_note(tmp_path, HARPIES, "note des Harpies")

        assert load_notes(tmp_path) == {
            JERON: "note de Jéron",
            HARPIES: "note des Harpies",
        }
