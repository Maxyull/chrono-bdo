"""L'interface graphique de Rubin.

Trois onglets, et chacun répond à une question qu'on se pose vraiment.

**Session** : où j'en suis, qu'est-ce qui vient, combien de temps ça prend.

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
    FRAGILE_BELOW,
    ZoneState,
    describe_conflict,
    describe_reading,
    describe_zone,
    format_duration,
    format_gap,
    format_reference,
    format_upcoming_line,
)

__all__ = [
    "FRAGILE_BELOW",
    "ZoneState",
    "describe_conflict",
    "describe_reading",
    "describe_zone",
    "format_duration",
    "format_gap",
    "format_reference",
    "format_upcoming_line",
]
