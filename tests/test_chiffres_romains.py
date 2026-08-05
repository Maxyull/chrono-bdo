"""Régression : le chiffre romain de fin partait seul à la ligne, et se perdait.

Relevé en observant vingt minutes de jeu réel : cinq échecs d'affilée sur
« [Mediah] Les marchands d'Altinova II ». Le nom déborde de la largeur du
bandeau, et son numéro passe seul sur la deuxième ligne, à gauche.

    Quete accomplie                     0.98   <- le titre
    [Mediah] Les marchands d'Altinova   0.96   <- le nom, amputé
    Ⅱ                                   0.515  <- le numéro, seul

Le fragment fait deux caractères et sort à **0,515**, sous le seuil des lignes
qui est à 0,75. Il est écarté avant même d'arriver au catalogue, et le nom
reconstruit devient « [Mediah] Les marchands d'Altinova », qui n'est le nom
complet d'aucune quête.

Ce n'est pas un défaut de normalisation : `fold` ramène très bien « Ⅱ »
(U+2161) à « ii », et le nom complet se résout parfaitement. C'est le fragment
qui n'arrive jamais.

Et `resolve_partial` n'y peut rien : elle cherche par la **fin** du nom, pour
le cas du panneau de choix où c'est le préfixe de région qui saute. Ici c'est
justement la fin qui manque. Les deux cas sont symétriques et demandent deux
traitements opposés.

Compté sur le catalogue réel du 5 août 2026 : **81 quêtes principales**
finissent par un chiffre romain, et **76** portent un nom que le seul début ne
distingue plus.
"""

from __future__ import annotations

import pytest

from rubin.reading import MIN_LINE_SCORE, BannerKind, parse_banner
from rubin.reference import Catalog, QuestId

#: Les quêtes réellement en jeu ici, avec leurs vrais identifiants et leurs
#: vrais noms dans les deux langues. Relevées dans le référentiel complet, qui
#: ne peut pas être embarqué dans le dépôt : ce sont des données appartenant à
#: Pearl Abyss, téléchargées chez le joueur au premier lancement.
#:
#: Les trois quêtes de la chaîne 21402 sont le cas dangereux : elles ne
#: diffèrent que par leur numéro. Les deux de la 21137 sont le cas facile : le
#: marqueur de carrefour, présent sur la première seulement, suffit à les
#: distinguer même sans leur numéro.
QUÊTES: dict[str, tuple[str, str]] = {
    "21402/3": (
        "[Mediah] Les marchands d'Altinova I",
        "[Mediah] The Merchants of Altinova I",
    ),
    "21402/4": (
        "[Mediah] Les marchands d'Altinova II",
        "[Mediah] The Merchants of Altinova II",
    ),
    "21402/5": (
        "[Mediah] Les marchands d'Altinova III",
        "[Mediah] The Merchants of Altinova III",
    ),
    "21137/1": (
        "[Calpheon][Carrefour] Extermination des harpies I",
        "[Calpheon] [Crossroad] Harpy Subjugation I",
    ),
    "21137/2": (
        "[Calpheon] Extermination des harpies II",
        "[Calpheon] Harpy Subjugation II",
    ),
    # Un nom sans numéro, pour vérifier qu'on ne lui en ajoute jamais un.
    "21136/1": ("[Calpheon] Jeron, la tacticienne", "[Calpheon] Jeron the Tactician"),
    # Un nom long, pour vérifier qu'un début auquel il manque plusieurs mots
    # n'est pas complété non plus.
    "21139/29": (
        "[Calpheon] Ce qui s'est passé jusqu'à présent",
        "[Calpheon] What Happened So Far",
    ),
}

#: Les trois lignes telles que la reconnaissance les a rendues, textes et
#: scores compris. Le « Ⅱ » est le caractère romain d'Unicode, U+2161, celui
#: que le jeu affiche, et non deux « I » à la suite.
BANDEAU_LU: list[tuple[str, float]] = [
    ("Quete accomplie", 0.98),
    ("[Mediah] Les marchands d'Altinova", 0.96),
    ("Ⅱ", 0.515),
]

#: Le nom tel qu'il ressort du bandeau une fois le numéro écarté.
NOM_AMPUTÉ = "[Mediah] Les marchands d'Altinova"

#: La quête réellement accomplie, et donc la seule bonne réponse.
ATTENDUE = QuestId(21402, 4)


@pytest.fixture(scope="module")
def catalogue() -> Catalog:
    payloads = {
        language: {
            "aaData": [
                [
                    {"display": identifiant},
                    "",
                    f"<b>{noms[index]}</b>",
                    1,
                    {"display": "Tous"},
                    {"display": "0"},
                    {"display": "0"},
                    "0",
                    "",
                    "[26]",
                    1,
                ]
                for identifiant, noms in QUÊTES.items()
            ]
        }
        for index, language in enumerate(("fr", "en"))
    }
    return Catalog.from_payloads(payloads)


def test_le_numero_isole_tombe_sous_le_seuil_des_lignes() -> None:
    """Le point de départ : la ligne existe, elle est simplement jetée.

    Un fragment de deux caractères a un score structurellement plus bas qu'une
    ligne de trente. Le seuil ne fait pas la différence entre les deux, et le
    numéro disparaît avec les artefacts qu'il est censé filtrer.
    """
    assert BANDEAU_LU[2][1] < MIN_LINE_SCORE

    lecture = parse_banner(BANDEAU_LU)

    assert lecture is not None
    assert lecture.kind is BannerKind.COMPLETED
    # Le nom sort amputé de son numéro, sans que rien ne le signale.
    assert lecture.quest_name == NOM_AMPUTÉ


def test_le_nom_ampute_se_retrouve_par_la_position_suivante(catalogue: Catalog) -> None:
    """Le cas réel, de bout en bout : ce que le bandeau donne doit rendre 21402/4.

    Le nom amputé ne se résout ni exactement, ni par la fin. Il est en revanche
    le **début** exact d'un nom du catalogue, et le contexte de la session dit
    lequel : le joueur venait de finir la 21402/3, donc la quête qui s'achève
    est la 21402/4.

    C'est le même recours, et la même étroitesse, que pour les homonymes d'une
    même chaîne : la position exactement suivante, jamais une position plus
    loin.
    """
    lecture = parse_banner(BANDEAU_LU)
    assert lecture is not None
    lignes = lecture.name_lines or (lecture.quest_name,)

    assert catalogue.resolve(lecture.quest_name) is None
    assert catalogue.resolve_partial(lecture.quest_name) is None
    assert catalogue.resolve_lines(lignes) is None

    assert catalogue.resolve_lines(lignes, "fr", chain=21402, after_position=3) == ATTENDUE


def test_le_numero_lu_donne_la_meme_reponse_sans_aucun_contexte(catalogue: Catalog) -> None:
    """L'autre bout du même problème, et il appartient au chemin de lecture.

    Si le « Ⅱ » était retenu, le nom serait complet et se résoudrait tout seul,
    sans contexte ni hypothèse. C'est la piste d'un seuil plus bas pour une
    ligne très courte, qui vit dans `reading/` et n'est pas traitée ici.

    ⚠️ Un seul seuil n'y suffirait d'ailleurs pas, et ce test le montre : la
    confiance du bandeau est le **minimum** des scores retenus, donc garder une
    ligne à 0,515 ferait tomber le bandeau entier sous `MIN_READING_SCORE`, qui
    est à 0,80. Il faudrait soit sortir les fragments très courts du calcul de
    confiance, soit baisser les deux seuils, ce qui n'est pas la même décision.

    Ce test vérifie surtout que les deux chemins tombent sur la **même** quête.
    Si les seuils bougent un jour, la résolution par début de nom ne contredira
    pas ce que la lecture aura retrouvé.
    """
    # Le seuil des lignes seul ne suffit pas : le bandeau est encore refusé.
    assert parse_banner(BANDEAU_LU, min_line_score=0.50) is None

    complet = parse_banner(BANDEAU_LU, min_line_score=0.50, min_reading_score=0.50)

    assert complet is not None
    assert complet.quest_name == "[Mediah] Les marchands d'Altinova Ⅱ"
    assert catalogue.resolve(complet.quest_name) == ATTENDUE


def test_le_debut_seul_ne_tranche_jamais_entre_les_trois_numeros(
    catalogue: Catalog,
) -> None:
    """Le garde-fou, et c'est lui qui rend la méthode acceptable.

    « [Mediah] Les marchands d'Altinova » est le début exact du I, du II et du
    III, toutes trois dans la chaîne 21402. Sans la position, rien ne les
    départage, et prendre la première venue attribuerait la mesure à une quête
    que le joueur n'a peut-être pas faite.

    Une quête non identifiée coûte une mesure ; une quête mal identifiée pollue
    une médiane pour toujours.
    """
    for candidate in (QuestId(21402, 3), ATTENDUE, QuestId(21402, 5)):
        quête = catalogue.get(candidate)
        assert quête is not None and quête.name.startswith(NOM_AMPUTÉ)

    assert catalogue.resolve_truncated(NOM_AMPUTÉ) is None
    # Même la chaîne ne suffit pas : les trois y sont.
    assert catalogue.resolve_truncated(NOM_AMPUTÉ, "fr", chain=21402) is None
    assert catalogue.resolve_lines((NOM_AMPUTÉ,), "fr", chain=21402) is None


class TestResolveTruncated:
    """La résolution par début de nom, prise isolément."""

    def test_complete_un_nom_qu_un_seul_numero_prolonge(self, catalogue: Catalog) -> None:
        """Un seul candidat : on complète, sans avoir besoin d'aucun contexte.

        « [Calpheon][Carrefour] Extermination des harpies » n'est le début que
        du I, puisque le II a perdu son marqueur de carrefour et porte donc un
        autre préfixe. Les deux se retrouvent ainsi chacune de son côté.
        """
        assert catalogue.resolve("[Calpheon][Carrefour] Extermination des harpies") is None
        assert catalogue.resolve_truncated(
            "[Calpheon][Carrefour] Extermination des harpies"
        ) == QuestId(21137, 1)
        assert catalogue.resolve_truncated("[Calpheon] Extermination des harpies") == QuestId(
            21137, 2
        )

    def test_la_position_suivante_departage_les_numeros_d_une_meme_chaine(
        self, catalogue: Catalog
    ) -> None:
        assert catalogue.resolve_truncated(
            NOM_AMPUTÉ, "fr", chain=21402, after_position=3
        ) == ATTENDUE
        assert catalogue.resolve_truncated(
            NOM_AMPUTÉ, "fr", chain=21402, after_position=4
        ) == QuestId(21402, 5)

    def test_ne_devine_pas_une_position_plus_loin(self, catalogue: Catalog) -> None:
        # Deviner un saut reviendrait à attribuer une mesure à une quête que le
        # joueur n'a peut-être pas faite. Même étroitesse que `resolve_in_chain`.
        assert catalogue.resolve_truncated(NOM_AMPUTÉ, "fr", chain=21402, after_position=9) is (
            None
        )

    def test_ignore_une_chaine_ou_aucun_candidat_ne_se_trouve(
        self, catalogue: Catalog
    ) -> None:
        # Le joueur était ailleurs : le contexte ne peut alors rien départager,
        # et n'autorise surtout pas à prendre un candidat d'une autre chaîne.
        assert catalogue.resolve_truncated(
            NOM_AMPUTÉ, "fr", chain=21137, after_position=1
        ) is None

    def test_ne_complete_pas_un_nom_qui_est_deja_celui_d_une_quete(
        self, catalogue: Catalog
    ) -> None:
        # Un nom complet est pris pour ce qu'il est : la résolution exacte
        # l'emporte, et aucun numéro ne lui est ajouté.
        assert catalogue.resolve_truncated("[Calpheon] Jeron, la tacticienne") == QuestId(
            21136, 1
        )

    def test_refuse_un_debut_trop_court(self, catalogue: Catalog) -> None:
        # Un fragment de quelques lettres ressemble à trop de choses. Même
        # garde que la résolution partielle, et pour la même raison.
        assert catalogue.resolve_truncated("Les") is None
        assert catalogue.resolve_truncated("") is None

    def test_refuse_quand_le_reste_manquant_n_est_pas_un_numero(
        self, catalogue: Catalog
    ) -> None:
        """Un nom auquel il manque plusieurs mots est un autre problème.

        « [Calpheon] Ce qui s'est » est bien le début de la 21139/29, mais ce
        qui manque n'est pas un numéro passé à la ligne : c'est la moitié du
        nom. Ce cas n'a pas les mêmes garanties, et n'est pas traité ici.
        """
        assert catalogue.resolve_truncated("[Calpheon] Ce qui s'est") is None
        assert catalogue.resolve_truncated(
            "[Calpheon] Ce qui s'est", "fr", chain=21139, after_position=28
        ) is None

    def test_complete_aussi_sur_le_client_anglais(self, catalogue: Catalog) -> None:
        # Les deux langues partagent les identifiants : le classement reste
        # commun, quelle que soit celle où le numéro a sauté.
        assert catalogue.resolve_truncated(
            "[Mediah] The Merchants of Altinova", "en", chain=21402, after_position=3
        ) == ATTENDUE
