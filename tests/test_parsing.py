from __future__ import annotations

from typing import Any

import pytest

from rubin.reference import QuestId, clean_text, parse_payload, parse_row, split_prefix

# Une ligne conforme, calquée sur le format réel : onze colonnes, un identifiant
# et une région servis comme objets `{display, sort_value}`, un nom noyé dans du
# balisage d'affichage.
VALID_ROW: list[Any] = [
    {"display": "21136/1", "sort_value": "211360001"},
    '<div class="iconset_wrapper_big"><img src="/items/quest/x.webp"></div>',
    '<a href="/fr/quest/21136/1/" class="qtooltip"><b>[Calpheon] Jeron, la tacticienne</b></a>',
    1,
    {"display": "Nord de Calpheon", "sort_value": 5},
    {"display": "0", "sort_value": 0},
    {"display": "0", "sort_value": 0},
    "100",
    "",
    "[26]",
    1,
]


class TestCleanText:
    def test_retire_le_balisage(self) -> None:
        assert clean_text("<b>Esprit de Mudang</b>") == "Esprit de Mudang"

    def test_rend_les_entites_html(self) -> None:
        # Sans cette étape, la région d'O'dyllita ne correspond à rien de ce que
        # le jeu affiche, et aucune quête de la zone n'est jamais reconnue.
        assert clean_text("O&#39;dyllita") == "O'dyllita"

    def test_rend_les_entites_nommees(self) -> None:
        assert clean_text("Roc &amp; pierre") == "Roc & pierre"

    def test_supprime_les_espaces_de_bord(self) -> None:
        assert clean_text("  <i> Serendia </i>  ") == "Serendia"


class TestSplitPrefix:
    def test_separe_le_prefixe_entre_crochets(self) -> None:
        assert split_prefix("[Calpheon] Jeron, la tacticienne") == (
            "Calpheon",
            "Jeron, la tacticienne",
        )

    def test_laisse_intact_un_nom_sans_prefixe(self) -> None:
        assert split_prefix("Jeron, la tacticienne") == (None, "Jeron, la tacticienne")

    def test_ne_prend_que_le_premier_groupe_de_crochets(self) -> None:
        # Cas réel du journal : `[Mediah][I] L'ancienne famille royale de Mediah`.
        # Le premier groupe est la région, le second un numéro de partie. Les
        # avaler tous les deux effacerait une information.
        assert split_prefix("[Mediah][I] L'ancienne famille royale") == (
            "Mediah",
            "[I] L'ancienne famille royale",
        )

    def test_tolere_l_absence_d_espace_apres_le_prefixe(self) -> None:
        assert split_prefix("[Serendia]Statue du dragon noir") == (
            "Serendia",
            "Statue du dragon noir",
        )


class TestParseRow:
    def test_lit_une_ligne_conforme(self) -> None:
        quest = parse_row(VALID_ROW)
        assert quest.id == QuestId(21136, 1)
        assert quest.name == "[Calpheon] Jeron, la tacticienne"
        assert quest.prefix == "Calpheon"
        assert quest.title == "Jeron, la tacticienne"
        assert quest.region == "Nord de Calpheon"
        assert quest.is_main

    def test_traduit_la_region_tous_en_absence_de_region(self) -> None:
        # « Tous » concerne plus de la moitié du catalogue. En faire une région
        # à part entière donnerait une région majoritaire absurde à presque
        # toutes les chaînes.
        row = list(VALID_ROW)
        row[4] = {"display": "Tous", "sort_value": 0}
        assert parse_row(row).region is None

    @pytest.mark.parametrize("count", [10, 12])
    def test_refuse_un_nombre_de_colonnes_inattendu(self, count: int) -> None:
        # Le jour où le site ajoute une colonne, on veut un échec net au
        # chargement, pas des niveaux lus dans la colonne des régions.
        row = (VALID_ROW * 2)[:count]
        with pytest.raises(ValueError, match="colonnes"):
            parse_row(row)

    def test_refuse_une_quete_sans_nom(self) -> None:
        row = list(VALID_ROW)
        row[2] = "<b></b>"
        with pytest.raises(ValueError, match="sans nom"):
            parse_row(row)

    def test_refuse_un_identifiant_malforme(self) -> None:
        row = list(VALID_ROW)
        row[0] = {"display": "21136", "sort_value": "x"}
        with pytest.raises(ValueError, match="illisible"):
            parse_row(row)


class TestParsePayload:
    def test_lit_toutes_les_lignes_valides(self) -> None:
        assert len(parse_payload({"aaData": [VALID_ROW, VALID_ROW]})) == 2

    def test_ecarte_les_lignes_illisibles_sans_tout_perdre(self) -> None:
        # Une quête cassée en amont ne doit pas priver l'utilisateur des
        # 18 998 autres.
        payload = {"aaData": [VALID_ROW, ["cassée"], VALID_ROW, []]}
        assert len(parse_payload(payload)) == 2

    def test_refuse_une_reponse_sans_tableau(self) -> None:
        with pytest.raises(ValueError, match="aaData"):
            parse_payload({"erreur": "maintenance"})
