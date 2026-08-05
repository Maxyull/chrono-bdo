"""Régression : le chat du jeu arrivait ENTRELACÉ avec le bandeau.

Neuf échecs sur neuf du journal de Maxime, le 5 août 2026, après le correctif
qui cherchait le titre au lieu de le supposer en première ligne. Ce correctif
était nécessaire et **pas suffisant** : le titre était bien retrouvé, mais les
lignes du chat qui le suivaient entraient dans le nom de la quête.

    Queteaccomplie                      <- le titre
    Guer                                <- du chat, APRÈS le titre
    [Hebdo] Echange d'arme du Voile     <- le nom
    finp                                <- du chat
    noir                                <- la SUITE du nom

Le nom recollé devenait « Guer [Hebdo] Echange d'arme du Voile finp noir ».
Aucune des neuf lectures ne se résolvait, alors que chaque ligne sortait entre
0,94 et 0,97 : rien ne manquait à la reconnaissance.

Les lignes ci-dessous sont les **vraies** sorties du moteur sur les neuf
vignettes gardées dans le dossier des échecs, textes, scores et boîtes compris,
relevés en rejouant la reconnaissance sur les images elles-mêmes. Les
coordonnées sont celles de la vignette de 349 x 115 pixels.
"""

from __future__ import annotations

import pytest

from rubin.reading import BannerKind, TextLine, parse_banner_lines
from rubin.reference import Catalog, QuestId


def ligne(
    text: str, score: float, left: float, right: float, top: float, bottom: float
) -> TextLine:
    return TextLine(text=text, score=score, left=left, right=right, top=top, bottom=bottom)


#: empreinte de la vignette -> lignes lues, type attendu, nom attendu.
ENTRELACES: list[tuple[str, list[TextLine], BannerKind, str]] = [
    (
        # Le cas cité en exemple : deux lignes de chat entre le nom et sa suite.
        "cfbbb896250632c0",
        [
            ligne("de guilde", 0.963, 2.5, 56.5, 1.0, 13.0),
            ligne("termineesavantla", 0.961, 54.0, 156.5, 3.0, 10.5),
            ligne("aintenance", 0.914, 167.0, 227.0, 3.0, 10.5),
            ligne("ontpasdoRei", 0.867, 1.5, 77.0, 17.0, 29.5),
            ligne("Queteaccomplie", 0.959, 148.5, 288.0, 31.5, 50.5),
            ligne("Guer", 0.981, 1.0, 27.5, 39.0, 51.0),
            ligne("[Hebdo] Echange d’arme du Voile", 0.943, 103.5, 330.0, 48.5, 68.5),
            ligne("finp", 0.969, 1.5, 27.0, 54.5, 69.5),
            ligne("ajour", 0.959, 1.5, 33.5, 72.0, 86.5),
            ligne("noir", 0.997, 103.5, 133.0, 68.5, 83.0),
        ],
        BannerKind.COMPLETED,
        "[Hebdo] Echange d’arme du Voile noir",
    ),
    (
        # Une ligne de chat s'intercale entre le nom et son dernier mot.
        "1e34506386049e03",
        [
            ligne("de", 0.927, 4.0, 20.5, 2.0, 11.0),
            ligne("termineesavantlamaintenance", 0.994, 51.5, 229.5, 1.0, 12.0),
            ligne("ontpas-do", 0.923, 1.5, 60.5, 18.5, 29.5),
            ligne("1244", 0.703, 185.0, 222.0, 18.0, 25.0),
            ligne("Nouvellequete", 0.968, 152.5, 279.0, 31.0, 51.0),
            ligne("Guer", 0.99, 1.0, 27.5, 39.0, 51.0),
            ligne("[Mediah] Abun,le village des", 0.95, 119.5, 312.5, 49.5, 67.0),
            ligne("ajour", 0.99, 2.0, 33.0, 72.5, 86.5),
            ligne("ouvriers", 0.996, 120.5, 177.0, 69.5, 82.5),
        ],
        BannerKind.ACCEPTED,
        "[Mediah] Abun,le village des ouvriers",
    ),
    (
        # Trois lignes de chat mêlées à un nom qui tient sur deux lignes.
        "54eb955628c5afe7",
        [
            ligne("deguildei", 0.954, 2.5, 56.5, 1.0, 13.0),
            ligne("termineesavantl", 0.957, 54.5, 147.5, 3.0, 10.5),
            ligne("nce:", 0.73, 205.5, 229.5, 3.0, 11.5),
            ligne("ontpasdhRenor", 0.86, 1.0, 94.0, 17.0, 30.0),
            ligne("Objectif dequete accompli", 0.953, 108.0, 328.5, 31.0, 51.0),
            ligne("Guer", 0.983, 0.5, 27.5, 38.5, 51.0),
            ligne("finp", 0.977, 1.0, 27.5, 55.0, 70.0),
            ligne("[Mediah][Boss]Lesouverain", 0.984, 115.0, 307.0, 51.0, 65.5),
            ligne("ajour", 0.943, 1.5, 33.5, 72.0, 86.5),
            ligne("supreme dela Grotte delave", 0.962, 114.0, 307.5, 66.5, 85.0),
        ],
        BannerKind.OBJECTIVE_DONE,
        "[Mediah][Boss]Lesouverain supreme dela Grotte delave",
    ),
    (
        "c6ca4445d1bbf183",
        [
            ligne("de guilde terminees avant la maintenance,", 0.981, 2.5, 230.5, 0.5, 14.0),
            ligne("ontpas de Renomr", 0.905, 1.5, 102.5, 17.5, 29.5),
            ligne("[12:44]", 0.94, 183.5, 222.5, 17.5, 25.5),
            ligne("Objectif de quete partielle...", 0.93, 103.5, 331.5, 30.5, 52.0),
            ligne("Guer", 0.991, 1.5, 27.5, 39.5, 50.5),
            ligne("[Mediah] Chaleur incontrolable", 0.959, 113.5, 322.5, 59.0, 74.5),
            ligne("ajour", 0.917, 2.0, 32.5, 73.0, 86.0),
        ],
        BannerKind.PARTIAL,
        "[Mediah] Chaleur incontrolable",
    ),
    (
        # « Les fanatiques » : le nom que la fenêtre affichait sans jamais le
        # mesurer, cité tel quel dans l'état du projet.
        "fc16310ec912f5ff",
        [
            ligne("de guilde terminees avant la maintenance,", 0.989, 2.5, 230.0, 0.5, 14.0),
            ligne("ontpasdeRenomm", 0.937, 1.0, 106.0, 17.5, 29.5),
            ligne("[12:44]", 0.944, 183.5, 222.0, 17.5, 25.5),
            ligne("Objectif de quete accompli", 0.939, 108.0, 328.5, 30.5, 52.0),
            ligne("Guer", 0.99, 1.0, 27.5, 39.0, 51.0),
            ligne("Les fanatiques", 0.973, 168.0, 266.5, 58.5, 75.5),
            ligne("ajour", 0.988, 2.0, 33.0, 73.0, 86.0),
        ],
        BannerKind.OBJECTIVE_DONE,
        "Les fanatiques",
    ),
    (
        "2d07fe4b1c8b18b1",
        [
            ligne("de", 0.997, 3.5, 22.5, 1.5, 11.5),
            ligne("guilde terminees avant la maintenance,", 0.974, 16.0, 230.5, 0.5, 13.0),
            ligne("ontpasdoRenommee", 0.948, 1.5, 123.5, 17.0, 30.0),
            ligne("[12:44]", 0.845, 184.5, 222.0, 18.0, 25.0),
            ligne("Nouvelle quete", 0.965, 152.5, 278.5, 31.0, 51.5),
            ligne("Guer", 0.989, 1.0, 27.5, 39.0, 51.0),
            ligne("[Mediah] Larevoltedesbarbares", 0.973, 109.0, 328.5, 59.5, 74.0),
            ligne("ajour", 0.894, 2.0, 32.5, 73.0, 86.0),
        ],
        BannerKind.ACCEPTED,
        "[Mediah] Larevoltedesbarbares",
    ),
    (
        "56c019db144811a8",
        [
            ligne("de guilde terminees avant la1", 0.971, 2.5, 159.0, 1.0, 13.0),
            ligne("maintenance", 0.993, 156.0, 229.0, 2.5, 11.0),
            ligne("ontpasdeRenommee", 0.931, 1.5, 123.0, 16.5, 30.0),
            ligne("[12:44", 0.852, 184.5, 222.0, 18.0, 25.0),
            ligne("Objectif de quete accompli", 0.946, 108.0, 328.5, 30.5, 52.0),
            ligne("Guer", 0.994, 2.0, 27.0, 39.5, 50.5),
            ligne("Un sacrifice pour un survivant", 0.951, 115.0, 321.5, 58.0, 77.0),
            ligne("ajour", 0.988, 1.5, 33.0, 73.0, 86.5),
        ],
        BannerKind.OBJECTIVE_DONE,
        "Un sacrifice pour un survivant",
    ),
    (
        "ee9ac3cbb05b2177",
        [
            ligne("de guilde terminees avant la maintenance,", 0.991, 2.5, 231.0, 1.0, 13.0),
            ligne("ontpasdoR", 0.916, 1.5, 71.0, 17.5, 30.0),
            ligne("ommoo", 0.752, 80.0, 122.0, 19.0, 26.5),
            ligne("deauilda", 0.771, 122.0, 175.0, 18.5, 26.0),
            ligne("[12:441", 0.834, 184.5, 222.0, 18.0, 25.0),
            ligne("Quete.accomplie", 0.947, 148.5, 287.5, 31.5, 50.5),
            ligne("Guer", 0.993, 1.5, 27.5, 39.0, 51.0),
            ligne("[Mediah] La pierrenoire et les", 0.956, 115.5, 316.5, 49.5, 67.0),
            ligne("ajour", 0.993, 2.0, 33.0, 73.0, 86.5),
            ligne("barbares", 0.997, 116.0, 176.5, 68.5, 82.5),
        ],
        BannerKind.COMPLETED,
        "[Mediah] La pierrenoire et les barbares",
    ),
    (
        "d56df2c00fc34772",
        [
            ligne("de guilde terminees avant la maintenance,", 0.954, 2.5, 231.0, 0.0, 13.5),
            ligne("ontpasdeRenommee", 0.954, 1.0, 124.0, 16.5, 30.0),
            ligne("[12:44]", 0.91, 183.0, 222.5, 17.5, 25.5),
            ligne("Nouvelle quete", 0.968, 152.5, 278.5, 31.0, 51.5),
            ligne("Guer", 0.987, 1.0, 27.5, 39.0, 51.0),
            ligne("finp", 0.975, 3.0, 25.0, 56.5, 68.5),
            ligne("[Mediah] Ala prochaine", 0.954, 137.5, 300.0, 57.5, 76.0),
            ligne("ajour", 0.982, 2.0, 33.0, 73.0, 86.0),
        ],
        BannerKind.ACCEPTED,
        "[Mediah] Ala prochaine",
    ),
]

#: Les mots du chat qui traînaient dans les noms. Aucun ne doit y rester.
MOTS_DU_CHAT = ("Guer", "finp", "ajour", "[12:44]", "deauilda", "ommoo")


@pytest.mark.parametrize(("empreinte", "lignes", "genre", "nom"), ENTRELACES)
def test_le_chat_ne_se_mele_plus_au_nom_de_la_quete(
    empreinte: str, lignes: list[TextLine], genre: BannerKind, nom: str
) -> None:
    """Régression : les neuf échecs du 5 août 2026, un par un.

    Chacun de ces neuf relevés produisait un nom mêlé de chat, qui ne se
    résolvait en aucune quête. Neuf mesures perdues sur neuf, sur une session
    où le joueur enchaînait des quêtes principales de Mediah.
    """
    lu = parse_banner_lines(lignes)

    assert lu is not None, empreinte
    assert lu.kind is genre
    assert lu.quest_name == nom
    assert not any(mot in lu.quest_name for mot in MOTS_DU_CHAT)


#: Confiance attendue pour chaque relevé : le plus faible score parmi le titre
#: et les lignes du nom, et rien d'autre. Une ligne de chat écartée ne doit plus
#: peser sur la certitude d'une mesure.
CONFIANCES: dict[str, float] = {
    "cfbbb896250632c0": 0.943,
    "1e34506386049e03": 0.950,
    "54eb955628c5afe7": 0.953,
    "c6ca4445d1bbf183": 0.930,
    "fc16310ec912f5ff": 0.939,
    "2d07fe4b1c8b18b1": 0.965,
    "56c019db144811a8": 0.946,
    "ee9ac3cbb05b2177": 0.947,
    "d56df2c00fc34772": 0.954,
}


@pytest.mark.parametrize(("empreinte", "lignes", "genre", "nom"), ENTRELACES)
def test_la_confiance_ne_depend_plus_de_ce_que_disait_la_guilde(
    empreinte: str, lignes: list[TextLine], genre: BannerKind, nom: str
) -> None:
    """La confiance ne retient que le titre et les lignes du nom.

    Sans quoi une mesure serait jugée d'après le score d'une annonce de guilde
    passée derrière le bandeau au même instant, ce qui n'a aucun rapport avec la
    certitude d'avoir bien lu la quête. Le relevé « ontpasdhRenor » à 0,86, par
    exemple, aurait fait tomber la lecture 54eb sous le seuil.
    """
    lu = parse_banner_lines(lignes)

    assert lu is not None
    assert lu.confidence == pytest.approx(CONFIANCES[empreinte])
    assert lu.confidence > min(ligne_lue.score for ligne_lue in lignes)


def _catalogue_des_quetes_ratees() -> Catalog:
    """Les quêtes réellement affichées ce jour-là, avec leurs vrais identifiants.

    Relevées dans le référentiel complet, qui ne peut pas être embarqué dans le
    dépôt : ce sont des données de jeu appartenant à Pearl Abyss, téléchargées
    chez le joueur au premier lancement.
    """
    quetes = {
        "4506/1": "[Hebdo] Échange d'arme du Voile noir",
        "21403/1": "[Mediah] Abun, le village des ouvriers",
        "209/1": "Les fanatiques",
    }
    rows = [
        [
            {"display": identifiant},
            "",
            f"<b>{nom}</b>",
            1,
            {"display": "Mediah"},
            {"display": "0"},
            {"display": "0"},
            "0",
            "",
            "[26]",
            1,
        ]
        for identifiant, nom in quetes.items()
    ]
    return Catalog.from_payloads({"fr": {"aaData": rows}})


def test_un_chat_mal_separe_ne_fabrique_aucun_nom_de_quete_plausible() -> None:
    """Le pire cas d'une séparation ratée reste une mesure perdue.

    C'est le principe qui tranche tout le projet : rater une mesure donne un
    chiffre incomplet, en inventer une donne un chiffre faux. Le filtre laisse
    donc tomber une ligne douteuse plutôt que de l'attribuer au bandeau.

    Ce test le vérifie dans les deux sens sur le relevé du 5 août 2026, à
    12:48:08. Le nom pollué, tel qu'il sortait avant la correction, ne se résout
    en rien, même en essayant les recollages de la ligne la plus longue à la
    plus courte comme le fait le chronomètre. Le nom séparé, lui, retombe sur
    4506/1.
    """
    catalogue = _catalogue_des_quetes_ratees()

    pollué = ["Guer", "[Hebdo] Echange d’arme du Voile", "finp", "ajour", "noir"]
    assert catalogue.resolve(" ".join(pollué)) is None
    assert catalogue.resolve_lines(pollué) is None
    assert catalogue.resolve_partial(" ".join(pollué)) is None

    séparé = ["[Hebdo] Echange d’arme du Voile", "noir"]
    assert catalogue.resolve_lines(séparé) == QuestId(4506, 1)


def test_les_noms_separes_retombent_sur_les_bonnes_quetes() -> None:
    """Régression : zéro nom résolu sur neuf avant, trois sur trois ici.

    Les trois quêtes ci-dessous sont celles des neuf échecs dont le nom, une
    fois séparé du chat, désigne une quête et une seule dans le référentiel
    complet. Les six autres relevés se séparent tout aussi bien, mais butent
    ensuite sur des difficultés qui n'ont rien à voir avec le chat : un nom que
    deux chaînes se partagent, ou une dernière ligne que la zone n'a pas
    couverte.
    """
    catalogue = _catalogue_des_quetes_ratees()
    attendus = {
        "[Hebdo] Echange d’arme du Voile noir": QuestId(4506, 1),
        "[Mediah] Abun,le village des ouvriers": QuestId(21403, 1),
        "Les fanatiques": QuestId(209, 1),
    }
    obtenus = {
        lu.quest_name: catalogue.resolve(lu.quest_name)
        for _, lignes, _, _ in ENTRELACES
        if (lu := parse_banner_lines(lignes)) is not None and lu.quest_name in attendus
    }
    assert obtenus == attendus
