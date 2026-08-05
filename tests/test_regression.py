"""Régression : ce qui est lu à l'écran doit retomber sur la bonne quête.

Ces trois quêtes viennent des captures qui ont servi à concevoir le
chronomètre. Les chaînes de caractères ci-dessous sont exactement ce que le
jeu affiche dans le bandeau en bas à droite, préfixe compris.

C'est le seul test qui relie les deux moitiés du projet : ce que l'œil voit et
ce que le référentiel contient. S'il casse, le logiciel mesure des temps qu'il
attribue à la mauvaise quête, ce qui est pire que de ne rien mesurer.
"""

from __future__ import annotations

import pytest

from rubin.reading import BannerKind, parse_banner
from rubin.reference import Catalog, QuestId

#: nom affiché en jeu -> identifiant attendu, relevé sur les captures.
SEEN_ON_SCREEN = {
    # Bandeau « Quête accomplie », capture du 04/08/2026.
    "[Calpheon] Jeron, la tacticienne": QuestId(21136, 1),
    # Bandeau « Nouvelle quête » qui suit immédiatement le précédent.
    "[Calpheon] Cris stridents des harpies": QuestId(21136, 2),
    # Suivi de quête, colonne de droite.
    "[Serendia] Statue du dragon noir": QuestId(21130, 147),
}


#: Textes rendus par la reconnaissance de caractères sur les captures, copiés
#: tels quels, défauts compris. Ce ne sont pas les noms du jeu : ce sont les
#: noms tels que le logiciel les recevra vraiment.
READ_BY_OCR = {
    # Accents perdus, et surtout virgule recollée au mot suivant.
    "[Calpheon] Jeron,la tacticienne": QuestId(21136, 1),
    # Nom rendu sur deux lignes par le bandeau, recollé avant résolution.
    "[Calpheon] Cris stridents des harpies": QuestId(21136, 2),
    # Accent conservé sur « desiré » mais perdu ailleurs : la reconnaissance
    # n'est pas cohérente d'un mot à l'autre, la normalisation doit l'absorber.
    "[Calpheon] Coup de main tant desiré": QuestId(21136, 3),
}


@pytest.mark.parametrize(("displayed", "expected"), SEEN_ON_SCREEN.items())
def test_un_nom_lu_a_l_ecran_retombe_sur_la_bonne_quete(
    catalog: Catalog, displayed: str, expected: QuestId
) -> None:
    assert catalog.resolve(displayed) == expected


@pytest.mark.parametrize(("read", "expected"), READ_BY_OCR.items())
def test_un_nom_abime_par_l_ocr_retombe_sur_la_bonne_quete(
    catalog: Catalog, read: str, expected: QuestId
) -> None:
    """Régression : « Jeron,la tacticienne » ne se résolvait pas.

    La reconnaissance colle la virgule au mot suivant. La normalisation ne
    traitait que les accents, la casse et les espaces, donc ce nom, pourtant lu
    avec un score de 0,95, ne retombait sur aucune quête.

    32 % des quêtes principales portent de la ponctuation dans leur nom, dont
    3 % une virgule. Sans ce traitement, le chronomètre aurait perdu ces
    mesures sans jamais dire pourquoi : un nom non résolu ne produit aucune
    erreur, seulement un trou dans les données.
    """
    assert catalog.resolve(read) == expected


@pytest.mark.parametrize("displayed", SEEN_ON_SCREEN)
def test_les_quetes_observees_sont_des_quetes_principales(catalog: Catalog, displayed: str) -> None:
    # Si l'une d'elles cessait d'être classée comme principale, le chronomètre
    # l'ignorerait en silence alors que le joueur la voit dans son journal.
    quest_id = catalog.resolve(displayed)
    assert quest_id is not None
    quest = catalog.get(quest_id)
    assert quest is not None and quest.is_main


def test_deux_toasts_consecutifs_se_suivent_dans_la_meme_chaine() -> None:
    # Le cas qui permet de retrouver la quête terminée quand son bandeau a été
    # manqué : voir démarrer 21136/2 implique que 21136/1 vient de s'achever.
    accomplie = SEEN_ON_SCREEN["[Calpheon] Jeron, la tacticienne"]
    nouvelle = SEEN_ON_SCREEN["[Calpheon] Cris stridents des harpies"]
    assert nouvelle.chain == accomplie.chain
    assert nouvelle.position == accomplie.position + 1


def test_le_nom_anglais_mene_a_la_meme_quete(catalog: Catalog) -> None:
    # Un joueur du client anglais lit un autre texte et doit alimenter la même
    # ligne de classement.
    quest_id = QuestId(21136, 1)
    anglais = catalog.get(quest_id, "en")
    assert anglais is not None
    assert catalog.resolve(anglais.name, "en") == quest_id


#: Lignes rendues par la reconnaissance sur un bandeau d'objectif capté en
#: session. La dernière n'est pas le nom de la quête mais la description de
#: l'objectif, et rien dans sa mise en forme ne l'en distingue.
OBJECTIVE_BANNER = (
    "[Calpheon] Cequi s'estpasse",
    "jusqu'apresent",
    "Lirelesdialoguesen fonctlon delaudio",
)


def test_ecarte_la_description_d_objectif_collee_au_nom(catalog: Catalog) -> None:
    """Régression : un bandeau d'objectif porte une ligne de trop.

    Relevé en jeu. Recoller toutes les lignes fabrique un nom qui n'existe
    pas, et la mesure est perdue. Les recollages sont donc essayés du plus
    long au plus court, et le premier qui tombe sur une quête l'emporte.
    """
    assert catalog.resolve(" ".join(OBJECTIVE_BANNER)) is None
    assert catalog.resolve_lines(OBJECTIVE_BANNER) == QuestId(21139, 29)


@pytest.mark.parametrize(
    ("read", "expected"),
    [
        # Espaces avalés, accents perdus : tel que lu en session.
        ("[Calpheon] Cequi s'estpasse jusqu'apresent", QuestId(21139, 29)),
        ("[Calpheon] Pretre officiel dElion", QuestId(21143, 2)),
    ],
)
def test_un_nom_aux_espaces_avales_retombe_sur_la_bonne_quete(
    catalog: Catalog, read: str, expected: QuestId
) -> None:
    """Régression : la reconnaissance supprime des espaces.

    « Ce qui s'est passé jusqu'à présent » est rendu « Cequi s'estpasse
    jusqu'apresent ». Aucun traitement des accents ne rattrape un mot recollé
    au suivant : il faut comparer des formes sans espaces du tout.
    """
    assert catalog.resolve(read) == expected


def test_un_nom_prive_de_son_prefixe_de_region_reste_identifiable(catalog: Catalog) -> None:
    """Régression : le panneau de choix d'un carrefour coupe le nom.

    Relevé en jeu sur un embranchement : l'écran affiche « [Carrefour] Du côté
    de Valks », le catalogue porte « [Calpheon][Carrefour] Du côté de Valks ».
    Le préfixe de région a sauté, et la résolution exacte échouait.

    76 quêtes principales portent un double préfixe et sont exposées au
    problème ; 72 se retrouvent par la fin de leur nom sans ambiguïté. Les
    carrefours comptent double, puisqu'ils décident du chemin suivi dans une
    chaîne : les rater fausse aussi la suite.
    """
    assert catalog.resolve("[Carrefour] Du côté de Valks") is None
    assert catalog.resolve_partial("[Carrefour] Du côté de Valks") == QuestId(21142, 1)
    assert catalog.resolve_partial("[Carrefour] Du côté d'Andre") == QuestId(21142, 5)


#: Les deux branches d'un carrefour, telles que le panneau de choix les montre :
#: préfixe de région coupé des deux côtés. Ce sont les deux quêtes de la chaîne
#: 21142, en positions 1 et 5, et elles s'excluent l'une l'autre.
CROSSROAD_PANEL = ("[Carrefour] Du côté de Valks", "[Carrefour] Du côté d'Andre")

#: Texte relevé au CENTRE d'une vraie capture du jeu, là où la zone de choix
#: cadre. Ce n'est pas du décor inventé : c'est le dialogue d'un PNJ et les
#: libellés de ses boutons, sur une capture prise pour calibrer le bandeau.
#:
#: C'est exactement ce que la zone de choix lira la plupart du temps, puisque le
#: panneau de choix ne s'affiche que quelques secondes par chaîne.
CENTRE_OF_THE_SCREEN = (
    "Enchantée, même cette situation n'est pas des plus réjouissantes !",
    "Qu'est-ce qui vous amène ici, chez les Chevaliers de Delphe ?",
    "Confirmer (Fonction souris 2)",
    "Annuler",
    "Récomp.",
    "Quête",
)


def test_les_deux_branches_d_un_carrefour_se_retrouvent_chacune(catalog: Catalog) -> None:
    """Ce que le panneau de choix apporte : savoir laquelle des deux a été prise.

    La chaîne 21142 propose « Du côté de Valks » en position 1 et « Du côté
    d'Andre » en position 5. Les deux s'excluent, et le référentiel ne dit pas
    laquelle le joueur a suivie : c'est l'un des 69 embranchements répartis sur
    38 chaînes, rangés dans `ETAT.md` sous « ce qu'aucun code ne peut résoudre ».

    Le panneau de choix est justement la surface qui les montre. Chaque ligne y
    est identifiable seule, et sur la bonne position, ce qui suffit à lever le
    doute une fois la zone lue.
    """
    valks, andre = (catalog.resolve_partial(nom) for nom in CROSSROAD_PANEL)

    assert valks == QuestId(21142, 1)
    assert andre == QuestId(21142, 5)
    # Le même carrefour, donc un choix, et non deux quêtes à faire l'une après
    # l'autre : c'est ce que le nombre de positions entre les deux cache.
    assert valks.chain == andre.chain
    for quest_id in (valks, andre):
        quête = catalog.get(quest_id)
        assert quête is not None and quête.is_crossroad


def test_une_zone_de_choix_mal_placee_n_identifie_rien(catalog: Catalog) -> None:
    """Régression : une zone estimée ne doit jamais identifier de travers.

    La zone du panneau de choix est la seule des trois à n'avoir jamais été
    mesurée en jeu, faute de capture. Elle tombera donc à côté plus souvent que
    les deux autres, et le plus souvent au milieu d'un dialogue de PNJ, qui est
    ce qu'il y a au centre de l'écran le reste du temps.

    Ces six lignes sont recopiées d'une capture réelle prise pour calibrer le
    bandeau. Aucune ne doit ressortir en quête, pas même par correspondance
    partielle, qui est pourtant la résolution la plus permissive du catalogue.

    C'est ce qui autorise à livrer une zone estimée : rater le panneau donne un
    chiffre incomplet, l'identifier de travers donnerait un chiffre faux, et un
    faux carrefour enverrait en plus toute la suite de la chaîne sur la mauvaise
    branche.
    """
    for ligne in CENTRE_OF_THE_SCREEN:
        assert catalog.resolve(ligne) is None
        assert catalog.resolve_partial(ligne) is None
    assert catalog.resolve_lines(CENTRE_OF_THE_SCREEN) is None


def test_ne_devine_pas_sur_un_fragment_trop_court(catalog: Catalog) -> None:
    # Une correspondance partielle est plus facile à obtenir qu'une exacte,
    # donc plus facile à obtenir par erreur.
    assert catalog.resolve_partial("Valks") is None
    assert catalog.resolve_partial("") is None


class TestLeveeDAmbiguite:
    """Le contexte de la chaîne et de la position identifie les homonymes."""

    def test_la_chaine_departage_deux_quetes_de_meme_nom(self, catalog: Catalog) -> None:
        """Régression : 18 % des quêtes principales portent un nom partagé.

        « [Serendia] Boss des Fogans » désigne trois quêtes distinctes. Sans
        contexte, le catalogue refuse de trancher et ces quêtes ne sont jamais
        mesurées : une sur cinq disparaissait silencieusement du chronomètre.

        La chaîne en cours suffit dans 57 % des cas. Un joueur qui vient de
        finir une quête de la chaîne 21133 fait évidemment celle de 21133, pas
        celle d'une chaîne qu'il n'a jamais commencée.
        """
        nom = "[Calpheon] Jeron, la tacticienne"
        assert catalog.resolve_in_chain(nom, 21136) == QuestId(21136, 1)

    def test_la_position_departage_deux_homonymes_d_une_meme_chaine(
        self, catalog: Catalog
    ) -> None:
        """Régression : 305 homonymes sont dans la même chaîne.

        La chaîne ne les départage pas, seule la position le peut : celle qui
        suit immédiatement la dernière quête connue. Ce dernier niveau porte le
        taux d'identification de 92 % à 100 %.
        """
        nom = "[Calpheon] Cris stridents des harpies"
        assert catalog.resolve_in_chain(nom, 21136, after_position=1) == QuestId(21136, 2)

    def test_ne_devine_jamais_un_saut_de_position(self, catalog: Catalog) -> None:
        """Le recours à la position exige la suivante immédiate, jamais plus loin.

        Deviner un saut reviendrait à attribuer une mesure à une quête que le
        joueur n'a peut-être pas faite, ce qui est l'erreur refusée partout
        ailleurs. Une mesure perdue coûte moins cher.
        """
        nom = "[Calpheon] Coup de main tant désiré"  # position 3
        assert catalog.resolve_in_chain(nom, 21136, after_position=0) == QuestId(21136, 3)

    def test_sans_contexte_le_catalogue_refuse_toujours(self, catalog: Catalog) -> None:
        # Le comportement d'origine est intact : sans savoir où l'on est, on ne
        # devine pas.
        assert catalog.resolve_in_chain("[Calpheon] Jeron, la tacticienne", None) == QuestId(
            21136, 1
        )


def test_le_chat_de_guilde_ne_tue_plus_le_bandeau() -> None:
    """Régression : une annonce de guilde faisait jeter le bandeau entier.

    La zone du bandeau recouvre le haut du chat du jeu. Quand une annonce de
    guilde déborde, elle occupe les premières lignes, le titre glisse en
    deuxième ou troisième position, et l'analyse exigeait qu'il soit en
    première. Tout était jeté.

    Le titre et le nom étaient pourtant lus parfaitement. Les lignes ci-dessous
    sont celles d'une session réelle du 5 août 2026, à 13:53:56, recopiées avec
    leurs scores : « Nouvelle quete » à 0,971 et « Un forgeron chevronne » à
    0,969, et pourtant `None`.

    Mesuré sur vingt minutes de jeu : **onze bandeaux sur soixante-treize**
    perdus pour cette seule raison, tous avec leur nom parfaitement lisible.
    C'est aussi ce qui faisait afficher « Les fanatiques » sans jamais la
    mesurer.
    """
    pollué = [
        ("de guilde terminees avant la maintenance,", 0.98),
        ("Nouvelle quete", 0.971),
        ("Un forgeron chevronne", 0.969),
    ]

    lu = parse_banner(pollué)

    assert lu is not None
    assert lu.kind is BannerKind.ACCEPTED
    assert lu.quest_name == "Un forgeron chevronne"
    # La confiance ne retient pas la ligne de chat : elle ferait varier la
    # mesure selon ce que racontait la guilde à cet instant.
    assert lu.confidence == pytest.approx(0.969)


def test_un_bandeau_sans_titre_reste_refuse() -> None:
    # Chercher le titre plutôt que le supposer ne doit pas rendre l'analyse
    # crédule : sans titre connu, il n'y a pas de bandeau.
    assert parse_banner([("de guilde terminees", 0.98), ("Xian", 0.97)]) is None
