from __future__ import annotations

from rubin.reference import Catalog, QuestId, fold, is_roman_numeral


class TestFold:
    def test_ignore_les_accents(self) -> None:
        assert fold("Quête accomplie") == fold("Quete accomplie")

    def test_ignore_la_casse(self) -> None:
        assert fold("STATUE DU DRAGON NOIR") == fold("statue du dragon noir")

    def test_supprime_tous_les_espaces(self) -> None:
        """Régression : la reconnaissance recolle les mots entre eux.

        Relevé en jeu : « Ce qui s'est passé » est rendu « Cequi s'estpasse ».
        Le découpage est imprévisible d'une lecture à l'autre, donc la seule
        forme stable est celle où les espaces ont disparu des deux côtés.
        """
        assert fold("  Vent   de  panique ") == "ventdepanique"
        assert fold("Cequi s'estpasse") == fold("Ce qui s'est passé")

    def test_ignore_une_virgule_recollee(self) -> None:
        assert fold("Jeron,la tacticienne") == fold("Jeron, la tacticienne")

    def test_ignore_les_crochets_du_prefixe(self) -> None:
        assert fold("[Calpheon] Statue") == fold("Calpheon Statue")

    def test_ignore_une_apostrophe_espacee(self) -> None:
        assert fold("L' ancienne famille") == fold("L'ancienne famille")

    def test_ramene_le_chiffre_romain_unicode_aux_lettres(self) -> None:
        """Le jeu emploie « Ⅱ » (U+2161), un caractère à part entière.

        La reconnaissance le rend tel quel, alors que le catalogue porte
        « II », deux lettres. La décomposition NFKD les réunit, sans quoi le
        chiffre lu ne correspondrait à aucun nom.
        """
        assert fold("Ⅱ") == fold("II") == "ii"
        assert fold("Les marchands d'Altinova Ⅱ") == fold("Les marchands d'Altinova II")


class TestIsRomanNumeral:
    """Sur des fragments déjà repliés, donc en minuscules et sans espace."""

    def test_accepte_les_chiffres_rencontres_en_fin_de_nom(self) -> None:
        for numeral in ("i", "ii", "iii", "iv", "v", "vi"):
            assert is_roman_numeral(numeral)

    def test_refuse_ce_qui_n_en_est_pas_un(self) -> None:
        # « ic » et « iiii » n'emploient que des lettres de chiffres romains
        # sans en être : les vérifier lettre à lettre ne suffirait pas.
        for text in ("", "ic", "iiii", "vx", "harpies", "ii2"):
            assert not is_roman_numeral(text)


class TestCatalog:
    def test_charge_les_deux_langues(self, catalog: Catalog) -> None:
        assert set(catalog.languages) == {"fr", "en"}

    def test_les_deux_langues_portent_les_memes_identifiants(self, catalog: Catalog) -> None:
        # C'est toute la raison pour laquelle le classement peut être commun aux
        # clients français et anglais : la clé n'est pas le nom, c'est la paire
        # chaîne/position, qui ne dépend pas de la langue.
        chains_fr = catalog.chains("fr", kind=None)
        chains_en = catalog.chains("en", kind=None)
        assert chains_fr.keys() == chains_en.keys()

    def test_traduit_une_quete_d_une_langue_a_l_autre(self, catalog: Catalog) -> None:
        quest_id = QuestId(21136, 1)
        francais = catalog.get(quest_id, "fr")
        anglais = catalog.get(quest_id, "en")
        assert francais is not None and anglais is not None
        assert francais.name != anglais.name

    def test_retrouve_une_quete_par_son_nom(self, catalog: Catalog) -> None:
        assert catalog.resolve("[Calpheon] Jeron, la tacticienne") == QuestId(21136, 1)

    def test_retrouve_une_quete_malgre_accents_et_casse(self, catalog: Catalog) -> None:
        assert catalog.resolve("[SERENDIA] STATUE DU DRAGON NOIR") == QuestId(21130, 147)

    def test_ne_trouve_rien_pour_un_nom_inconnu(self, catalog: Catalog) -> None:
        assert catalog.resolve("[Calpheon] Quête qui n'existe pas") is None

    def test_refuse_de_trancher_un_nom_ambigu(self) -> None:
        # Le jeu réemploie des libellés d'une région à l'autre. Rendre le
        # premier résultat venu fausserait le classement de tout le monde ;
        # ne rien rendre ne fait que perdre une mesure. Les deux erreurs ne
        # coûtent pas la même chose.
        rows = [
            [
                {"display": f"{chain}/1"},
                "",
                "<b>[Test] Chasse aux gobelins</b>",
                1,
                {"display": "Tous"},
                {"display": "0"},
                {"display": "0"},
                "0",
                "",
                "[26]",
                1,
            ]
            for chain in (100, 200)
        ]
        catalog = Catalog.from_payloads({"fr": {"aaData": rows}})
        assert catalog.resolve("[Test] Chasse aux gobelins") is None
        assert len(catalog.ambiguous_names("fr")) == 1

    def test_regroupe_les_quetes_en_chaines(self, catalog: Catalog) -> None:
        chains = catalog.chains("fr")
        assert 21136 in chains
        assert [q.id.position for q in chains[21136].quests] == [1, 2, 3]

    def test_ne_garde_que_les_quetes_principales_par_defaut(self, catalog: Catalog) -> None:
        principales = catalog.chains("fr")
        toutes = catalog.chains("fr", kind=None)
        assert len(principales) < len(toutes)
        assert all(q.is_main for chain in principales.values() for q in chain.quests)

    def test_ordonne_les_quetes_dans_une_chaine(self, catalog: Catalog) -> None:
        for chain in catalog.chains("fr").values():
            positions = [q.id.position for q in chain.quests]
            assert positions == sorted(positions)
