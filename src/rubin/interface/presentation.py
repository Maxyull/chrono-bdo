"""Ce que l'interface affiche, sans savoir comment l'afficher.

Tout ici est du calcul pur : des états entrent, des chaînes de caractères
sortent. Aucune dépendance à Tk, donc tout est vérifiable sans écran, donc en
intégration continue.

C'est la même séparation qu'ailleurs dans le projet : `region.py` calcule des
rectangles quand `screen.py` capture, et c'est le calcul qui porte les erreurs
intéressantes. Une fenêtre mal dessinée se voit ; un temps mal formaté ou un
compte de mesures oublié se croit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..capture import Rect
from ..upcoming import UpcomingQuest

#: En dessous de ce nombre de mesures, un temps est annoncé comme fragile.
#:
#: Cinq n'est pas un seuil statistique, c'est un seuil d'honnêteté : la base ne
#: contient aujourd'hui que onze mesures d'un seul joueur, donc presque tout
#: sera marqué, et c'est exactement ce qu'il faut montrer. Un chiffre affiché
#: sans son assise se croit plus solide qu'il n'est.
FRAGILE_BELOW: Final = 5


def format_duration(seconds: float) -> str:
    """Une durée lisible, de la seconde à l'heure."""
    minutes, reste = divmod(int(seconds), 60)
    if minutes >= 60:
        heures, minutes = divmod(minutes, 60)
        return f"{heures} h {minutes:02d} min"
    return f"{minutes} min {reste:02d} s" if minutes else f"{reste} s"


def format_reference(item: UpcomingQuest) -> str:
    """Le temps connu d'une quête à venir, et sur quoi il repose.

    Une quête que personne n'a mesurée le dit en toutes lettres. Laisser la
    colonne vide ou afficher un zéro se lirait comme « instantané », c'est-à-dire
    l'inverse de « inconnu ».
    """
    reference = item.reference
    if reference is None:
        return "jamais mesurée"
    mesures = "mesure" if reference.samples == 1 else "mesures"
    texte = f"{format_duration(reference.median_seconds)}  ({reference.samples} {mesures})"
    if reference.samples < FRAGILE_BELOW:
        # Le nombre seul ne suffit pas : il faut dire ce qu'il vaut.
        texte += "  peu sûr"
    return texte


def format_upcoming_line(item: UpcomingQuest) -> str:
    """Une ligne de la liste des quêtes à venir."""
    marque = "   (branche d'un choix)" if item.is_crossroad else ""
    return f"{item.quest.id.position}. {item.quest.name}{marque}"


def format_gap(item: UpcomingQuest) -> str | None:
    """L'avertissement de trou, ou `None` s'il n'y en a pas.

    Enjamber un trou sans rien dire laisserait croire que cette quête suit
    immédiatement la précédente. 82 chaînes sur 349 en portent, et le
    référentiel connaît 18 999 quêtes quand le jeu en compte 19 235 : une quête
    peut donc exister à l'écran sans figurer dans la liste.
    """
    if not item.gap_before:
        return None
    quoi = "position inconnue" if item.gap_before == 1 else "positions inconnues"
    return f"... {item.gap_before} {quoi} du référentiel"


@dataclass(frozen=True)
class ZoneState:
    """Ce qu'on sait d'une zone de lecture, pour le dire à l'écran."""

    name: str
    rect: Rect
    #: `True` quand le joueur l'a choisie lui-même, `False` quand elle est
    #: calculée depuis la fenêtre du jeu.
    chosen: bool
    #: Lignes que la reconnaissance en tire à l'instant. Vide est un résultat,
    #: pas une absence de résultat : c'est même le symptôme d'une zone mal
    #: placée, et c'est précisément ce qu'on veut voir.
    lines: tuple[str, ...] = ()


def describe_zone(state: ZoneState) -> str:
    """Résume une zone en une ligne : d'où elle vient, et où elle est."""
    origine = "choisie" if state.chosen else "calculée"
    return (
        f"{state.name} : {state.rect.width}x{state.rect.height} "
        f"en ({state.rect.left}, {state.rect.top}), {origine}"
    )


def describe_reading(state: ZoneState) -> str:
    """Ce que la reconnaissance lit dans cette zone, maintenant.

    C'est l'apport réel de l'onglet des zones. Sans cet aperçu, régler un
    rectangle revient à le déplacer à l'aveugle puis à jouer une session entière
    pour découvrir qu'il était à côté. Trois des défauts de ce projet ont coûté
    une séance chacun faute de pouvoir répondre à « qu'est-ce que tu lis, là,
    tout de suite ».
    """
    if not state.lines:
        return "rien lu ici. La zone est probablement à côté, ou le jeu ne montre rien."
    return "\n".join(state.lines)


def describe_conflict(blinded: list[Rect], zones: dict[str, Rect]) -> str | None:
    """L'avertissement à afficher quand la fenêtre couvre une zone lue.

    Nomme la zone en cause plutôt que de dire « une zone » : le bandeau et le
    panneau de suivi n'ont ni les mêmes conséquences ni le même remède.
    """
    if not blinded:
        return None
    noms = [nom for nom, rect in zones.items() if rect in blinded]
    liste = " et ".join(noms) if noms else "une zone de lecture"
    return (
        f"Cette fenêtre couvre {liste}. Rubin lit une capture d'écran, "
        "donc il vous lira vous au lieu du jeu, et ne mesurera rien. "
        "La transparence n'y change rien : c'est le mélange des deux qui est capturé."
    )
