"""L'interface graphique de Rubin.

Quatre onglets, et chacun répond à une question qu'on se pose vraiment.

**Session** : où j'en suis, qu'est-ce qui vient, combien de temps ça prend.

**Classement** : quelles quêtes sont les plus rapides, et combien de temps prend
celle que je cherche. C'est de la consultation pure, sur les temps que les autres
ont mesurés. ⚠️ Le classement se fait **par quête** et sur la **médiane** : une
chaîne moyenne ses quêtes rapides et ses quêtes lentes, or on choisit quête par
quête, et un record se falsifie en un seul envoi quand une médiane ne se déplace
pas. Les lignes ne s'affichent qu'à partir de trois mesures, faute de quoi la
première place reviendrait toujours à la quête qu'une personne a mesurée une fois
en ayant eu de la chance.

**Zones** : est-ce que le logiciel regarde au bon endroit, et **qu'est-ce qu'il
y lit en ce moment**. C'est l'onglet qui manquait le plus : trois des défauts du
projet ont coûté une séance chacun, faute de pouvoir répondre à « qu'est-ce que
tu lis, là, tout de suite ».

**Réglages** : les seuils, la cadence, la langue du client, l'opacité.

## Ce que cette interface n'est pas

Ce n'est **pas une surcouche**. Rien n'est injecté dans le jeu, aucune fonction
graphique n'est accrochée, aucun processus n'est ouvert. C'est une fenêtre
Windows ordinaire, que l'on peut poser au-dessus du jeu comme n'importe quelle
autre. La limite du projet vise l'injection, et elle tient.

## La règle qui commande la disposition

Rubin lit une capture d'écran, donc ce qui est **composé** à l'écran. Une
fenêtre posée sur une zone de lecture est lue à la place de cette zone, et la
transparence n'y change rien puisque c'est le mélange qui est capturé.

L'interface refuse donc de se poser sur ce qu'elle lit, et le dit quand le
joueur l'y déplace. Voir `placement.py`.

Le découpage suit celui du reste du projet : `presentation.py` calcule ce qu'il
faut afficher et ne dépend pas de Tk, `app.py` l'affiche. C'est le calcul qui
porte les erreurs qu'on ne voit pas.
"""

from .presentation import (
    COVERAGE_TAGS,
    DEMO_BANNER,
    DEMO_MARK,
    FRAGILE_BELOW,
    LINK_TAGS,
    RANKING_UNAVAILABLE,
    SEARCH_MIN_LENGTH,
    ZoneState,
    demo_active,
    demo_ranking,
    describe_conflict,
    describe_reading,
    describe_zone,
    format_coverage,
    format_duration,
    format_gap,
    format_link,
    format_other_quests,
    format_quest_times,
    format_ranked_quest,
    format_ranking,
    format_reference,
    format_running,
    format_search_result,
    format_upcoming_line,
    main_quest_total,
    other_quest_total,
    quest_display_name,
    ranking_message,
    running_seconds,
    search_quests,
)

__all__ = [
    "COVERAGE_TAGS",
    "DEMO_BANNER",
    "DEMO_MARK",
    "FRAGILE_BELOW",
    "LINK_TAGS",
    "RANKING_UNAVAILABLE",
    "SEARCH_MIN_LENGTH",
    "ZoneState",
    "demo_active",
    "demo_ranking",
    "describe_conflict",
    "describe_reading",
    "describe_zone",
    "format_coverage",
    "format_duration",
    "format_gap",
    "format_link",
    "format_other_quests",
    "format_quest_times",
    "format_ranked_quest",
    "format_ranking",
    "format_reference",
    "format_running",
    "format_search_result",
    "format_upcoming_line",
    "main_quest_total",
    "other_quest_total",
    "quest_display_name",
    "ranking_message",
    "running_seconds",
    "search_quests",
]
