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

from chrono.reference import Catalog, QuestId

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
