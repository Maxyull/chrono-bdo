"""Transformer des lignes de texte reconnues en un bandeau typé.

Séparé de la reconnaissance elle-même, qui est lente, dépend d'un moteur et
demande un écran. Ici tout est pur : des lignes de texte entrent, un bandeau
sort. C'est donc la partie vérifiable sans rien installer, et c'est là que se
logent les cas tordus.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Final

from ..reference import fold
from .models import BannerKind, BannerReading
from .ocr import TextLine, neutral_lines

#: Titres reconnus, par type de bandeau, sous leur forme normalisée.
#:
#: Ce sont des **préfixes** : « Objectif de quête partiellement accompli »
#: s'affiche tronqué en « Objectif de quête partielle... », et la troncature
#: dépend de la largeur disponible, donc du texte lui-même.
#:
#: L'ordre compte. « objectif de quete accompli » et « quete accomplie » se
#: ressemblent assez pour qu'un préfixe trop court attrape l'autre : les titres
#: sont donc essayés du plus long au plus court, et le premier qui convient
#: l'emporte.
TITLES: Final[dict[BannerKind, tuple[str, ...]]] = {
    BannerKind.PARTIAL: ("objectif de quete partielle",),
    BannerKind.OBJECTIVE_DONE: ("objectif de quete accompli",),
    BannerKind.ACCEPTED: ("nouvelle quete",),
    BannerKind.COMPLETED: ("quete accomplie",),
}

#: En dessous, une ligne est ignorée. Relevé sur les captures : les lignes
#: utiles sortent entre 0,91 et 1,00, tandis qu'un artefact isolé, un « F »
#: né d'un bord d'icône, sortait à 0,59.
MIN_LINE_SCORE: Final = 0.75

#: En dessous, le bandeau entier est refusé. Plus exigeant que pour une ligne :
#: une mesure attribuée à la mauvaise quête coûte plus cher qu'une mesure
#: perdue.
MIN_READING_SCORE: Final = 0.80


def _in_banner_column(title: TextLine, below: Sequence[TextLine]) -> list[TextLine]:
    """Ne garde, sous le titre, que les lignes qui sont dans sa colonne.

    C'est la correction du défaut qui empêchait Rubin de mesurer quoi que ce
    soit. La zone du bandeau recouvre le haut du chat du jeu, et la
    reconnaissance rend les lignes des deux **mélangées**, dans un ordre qui
    alterne. Relevé sur les neuf échecs du 5 août 2026 :

        Queteaccomplie                      <- le titre
        Guer                                <- du chat, APRÈS le titre
        [Hebdo] Echange d'arme du Voile     <- le nom
        finp                                <- du chat
        noir                                <- la SUITE du nom

    Le nom recollé devenait « Guer [Hebdo] Echange d'arme du Voile finp noir »,
    qui ne se résout en rien, alors que chaque ligne était lue entre 0,94 et
    0,97. Rien ne manquait à la reconnaissance : il manquait de savoir **où**
    chaque ligne avait été lue.

    Aucune abscisse n'est écrite ici, et c'est délibéré : un seuil fixe calé sur
    des captures est le deuxième piège du projet. Le critère est **relatif**, et
    tient à une propriété du bandeau qui ne dépend d'aucune résolution : il
    centre son texte, toujours sur le même axe. Les neuf relevés le confirment,
    milieu du titre entre 215,5 et 218,25 sur une zone large de 349. Le chat, à
    l'inverse, est calé à gauche.

    Une ligne appartient donc au bandeau si son **milieu** tombe dans la colonne
    ouverte par le titre, colonne qu'elle élargit ensuite : un nom plus long que
    le titre déborde des deux côtés, et les lignes de suite sont alignées à
    gauche sur lui, donc plus à gauche que le titre.

    Ce qui a été mesuré sur les neuf images, boîtes ramenées à l'échelle de la
    vignette de 349 pixels :

    - les lignes de chat qui suivent le titre sont **hachées par la barre
      opaque du bandeau** et ne dépassent jamais x = 33,5 ;
    - la colonne du bandeau commence au plus tôt à x = 103,5.

    Soit soixante-dix pixels de marge, sans qu'aucun nombre n'ait à être écrit.
    En cas de doute la ligne est **abandonnée**, jamais attribuée au bandeau :
    un nom amputé ne se résout en rien et coûte une mesure, un nom pollué
    pourrait en résoudre une autre.
    """
    left, right = title.left, title.right
    retained: list[TextLine] = []
    for line in below:
        # Au-dessus du titre, ce n'est pas la suite du bandeau. L'ordre rendu
        # par le moteur suit les rangées de haut en bas mais s'inverse parfois
        # entre deux lignes de la même rangée, et une ligne de chat pleine
        # largeur traverserait la colonne.
        if line.top < title.top:
            continue
        if not left <= line.middle <= right:
            continue
        left = min(left, line.left)
        right = max(right, line.right)
        retained.append(line)
    return retained


def is_foreign_noise(text: str) -> bool:
    """Cette ligne est-elle d'un alphabet que le jeu n'affiche pas ici ?

    Le moteur de reconnaissance est livré avec le modèle **chinois**, seul
    modèle empaqueté par `rapidocr_onnxruntime`. Il lit très bien le français,
    mesuré à 0,96 / 0,99 sur les bandeaux réels, mais son alphabet contient
    aussi les idéogrammes, et il en produit sur du décor ou du bruit.

    Or un client français ou anglais de Black Desert n'affiche **jamais** un
    idéogramme. Une ligne qui n'a pas une seule lettre latine ne peut donc être
    ni un titre de bandeau, ni un nom de quête : c'est du bruit, et le seul
    endroit où elle peut encore nuire est le recollage des noms longs, où elle
    se glisserait au milieu et rendrait le nom irrésoluble.

    ⚠️ **Il faut les deux conditions**, un caractère d'un autre alphabet ET
    aucune lettre latine, et c'est le point délicat.

    Refuser toute ligne sans lettre latine serait plus simple et serait faux :
    une ligne purement numérique serait jetée avec, or un nom de quête dont la
    fin passe à la ligne peut très bien s'y réduire. C'est le cas que la PR #62
    vient de traiter pour les chiffres romains, qui ne s'en sortaient que parce
    que `I`, `V` et `X` sont des lettres latines. Le chiffre arabe, lui,
    n'aurait rien pour se défendre.

    Refuser sur le seul idéogramme serait faux dans l'autre sens : une ligne
    mixte, où la reconnaissance a glissé un idéogramme au milieu du vrai nom,
    se verrait jetée alors qu'elle porte l'essentiel.

    Mesuré sur les 51 bandeaux réels du 5 août 2026, 173 lignes et 2 560
    caractères : **2 caractères hors français**, deux fois le même idéogramme
    seul sur sa ligne, et **aucun dans un nom de quête**. Le gain d'aujourd'hui
    est donc nul, et c'est écrit ici pour que personne ne croie avoir corrigé
    une panne. Ce garde-fou empêche un cas qui ne s'est pas encore produit.

    C'est aussi la mesure qui a fait renoncer au modèle latin : dix mégaoctets
    de plus dans le dépôt et dans l'exécutable, pour deux caractères sur deux
    mille cinq cent soixante, dont aucun ne coûtait une mesure. Les accents, eux,
    ne changeraient rien non plus : les noms sont comparés sans accents des deux
    côtés, c'est le troisième piège de l'ETAT.
    """
    latine = any("a" <= caractere <= "z" for caractere in fold(text))
    if latine:
        return False
    return any(unicodedata.category(caractere) == "Lo" for caractere in text)


def _match_title(text: str) -> BannerKind | None:
    # Les titres sont écrits lisiblement et normalisés ici, plutôt que stockés
    # sous leur forme normalisée : celle-ci n'a ni espaces ni accents, donc
    # « objectifdequetepartielle », et une table écrite ainsi serait pénible à
    # relire et fragile au moindre changement de normalisation.
    normalized = fold(text)
    candidates = sorted(
        ((kind, fold(title)) for kind, titles in TITLES.items() for title in titles),
        key=lambda pair: len(pair[1]),
        reverse=True,
    )
    for kind, title in candidates:
        if normalized.startswith(title):
            return kind
    return None


def parse_banner(
    lines: Iterable[tuple[str, float]],
    min_line_score: float = MIN_LINE_SCORE,
    min_reading_score: float = MIN_READING_SCORE,
) -> BannerReading | None:
    """Assemble des lignes sans géométrie, quand on n'a que du texte.

    Point d'entrée historique, gardé pour tout ce qui fabrique des lignes à la
    main : les tests, la vérification `rubin verifier`, un enregistrement rejoué.
    Sans boîte, aucune séparation d'avec le chat n'est possible ; ce chemin ne
    doit donc pas être celui d'une vraie session, qui passe par
    `parse_banner_lines`.
    """
    return parse_banner_lines(neutral_lines(lines), min_line_score, min_reading_score)


def parse_banner_lines(
    lines: Iterable[TextLine],
    min_line_score: float = MIN_LINE_SCORE,
    min_reading_score: float = MIN_READING_SCORE,
) -> BannerReading | None:
    """Assemble les lignes reconnues en un bandeau, ou renvoie `None`.

    `lines` arrive dans l'ordre de lecture, de haut en bas : le titre d'abord,
    puis le nom de la quête, qui passe sur deux lignes dès qu'il est trop long.
    Les lignes du nom sont recollées par un espace.

    Renvoie `None` dans tous les cas douteux, et ils sont nombreux : la zone
    peut ne contenir aucun bandeau mais du chat de guilde, le bandeau peut être
    capturé pendant son apparition en fondu, une ligne peut être un artefact.
    Un `None` ne coûte qu'une mesure ; un bandeau inventé fausse un classement.
    """
    kept = [
        replace(line, text=line.text.strip())
        for line in lines
        if line.score >= min_line_score
        and line.text.strip()
        # Une ligne d'un alphabet que le client n'affiche pas est du bruit, et
        # elle nuit précisément là où elle se glisse : au milieu d'un nom long
        # recollé. Voir `is_foreign_noise`, qui dit aussi ce que cela ne corrige
        # pas.
        and not is_foreign_noise(line.text)
    ]
    if len(kept) < 2:  # il faut au moins un titre et un nom
        return None

    # Le titre est CHERCHÉ parmi les lignes, il n'est pas supposé être la
    # première.
    #
    # Il l'était, et c'était le défaut le plus coûteux du projet. La zone du
    # bandeau recouvre le haut du chat du jeu : quand une annonce de guilde
    # déborde, elle occupe les premières lignes, le titre glisse en deuxième ou
    # troisième position, et le bandeau entier était jeté. Le titre et le nom
    # étaient pourtant lus parfaitement, à 0,97.
    #
    # Mesuré sur vingt minutes de jeu réel : **onze bandeaux sur soixante-treize
    # perdus pour cette seule raison**, tous avec leur nom parfaitement lisible.
    # C'est aussi ce qui a fait afficher « Les fanatiques » sans jamais la
    # mesurer.
    #
    # Chercher plutôt que supposer n'ouvre pas la porte aux inventions : les
    # libellés cherchés sont précis, et si du chat en contenait un par accident,
    # le nom retenu serait la ligne suivante, qui ne se résoudrait en aucune
    # quête. Le pire cas reste une mesure manquante.
    found = next(
        (
            (i, genre)
            for i, line in enumerate(kept)
            if (genre := _match_title(line.text)) is not None
        ),
        None,
    )
    if found is None:
        return None
    index, kind = found
    title = kept[index]

    retained = _in_banner_column(title, kept[index + 1 :])
    name_lines = tuple(line.text for line in retained)
    name = " ".join(name_lines)
    if not name:
        return None

    # La confiance ne porte que sur le titre et le nom. Y mêler les lignes de
    # chat ferait varier la confiance d'une mesure selon ce que racontait la
    # guilde à cet instant.
    confidence = min([title.score, *(line.score for line in retained)])
    if confidence < min_reading_score:
        return None
    return BannerReading(
        kind=kind, quest_name=name, name_lines=name_lines, confidence=confidence
    )


def is_known_title(text: str) -> bool:
    """Vrai si ce texte est l'un des titres de bandeau connus.

    Sert à savoir si la zone montre bien un bandeau plutôt qu'autre chose,
    quand on n'a qu'une ligne sous la main.
    """
    return _match_title(text) is not None


def known_titles() -> Sequence[str]:
    """Tous les titres reconnus, normalisés. Pour diagnostic."""
    return [title for titles in TITLES.values() for title in titles]
