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
from ..reference import Catalog
from ..references import Coverage
from ..upcoming import UpcomingQuest

#: Les trois tranches de couverture, dans l'ordre où elles s'affichent, et la
#: balise de couleur de chacune.
#:
#: Ce sont les mêmes noms que les balises de `app.py` et les mêmes que les trois
#: pastilles de la légende juste au-dessus du compteur. Une seule source pour
#: cet ordre : deux listes parallèles finiraient par diverger, et un compte
#: peint de la couleur du voisin ne lève aucune erreur et se croit sur parole.
COVERAGE_TAGS: Final = ("sur", "moyen", "absent")

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


def running_seconds(started_at: float | None, now: float) -> float | None:
    """Le temps écoulé sur la quête en cours, ou `None` si aucune n'est ouverte.

    ⚠️ **Les deux instants sont en temps monotone**, celui que le journal
    d'événements emploie, et jamais une heure du jour. Y mêler un `time.time()`
    donnerait un écart de plusieurs milliards de secondes, que rien ne
    signalerait : l'affichage montrerait un nombre, simplement absurde.

    ⚠️ **C'est le temps de la quête en cours, jamais un total de session.** Un
    total serait le débit au rythme médian, qui ment du simple au double : 77
    quêtes à l'heure annoncées contre 36 réellement produites sur une vraie
    session.

    Le plancher à zéro couvre le seul cas où la soustraction pourrait être
    négative, un départ enregistré par le fil de mesure entre la lecture de
    l'instant courant et celle du journal.
    """
    if started_at is None:
        return None
    return max(0.0, now - started_at)


def format_running(seconds: float | None) -> str:
    """Le chronomètre de la quête en cours, ou son absence, en toutes lettres.

    **L'absence dit autant que le temps, et c'est ce qui rend ce compteur
    prioritaire.** Aujourd'hui, un bandeau de DÉPART ignoré est parfaitement
    silencieux : le joueur ne découvre les quêtes manquées qu'une heure plus
    tard, en comptant. Un chronomètre qui reste arrêté alors qu'il vient
    d'accepter une quête le lui dit sur-le-champ, et transforme « ça va trop
    vite et certaines quêtes ne sont pas comptées » en fait observable.

    D'où une phrase, et non une colonne vide ou un « 0 s ». Les deux se
    liraient comme « ça vient de démarrer », c'est-à-dire l'inverse de « rien
    n'est chronométré ». C'est le même écueil que la quête jamais mesurée dont
    la colonne vide se lisait « instantané ».
    """
    if seconds is None:
        return "aucune quête chronométrée"
    return f"chronomètre : {format_duration(seconds)}"


def _grouped(number: int) -> str:
    """Un nombre avec son séparateur de milliers, « 3 913 » et pas « 3913 ».

    L'espace est insécable : le nombre s'affiche à côté de deux autres, et une
    coupure entre le 3 et le 913 en ferait lire quatre. C'est U+00A0, posée
    telle quelle dans le code : indiscernable d'une espace ordinaire à la
    lecture, donc les tests la comparent en `\\u00a0` pour que la différence se
    voie là où elle compte.
    """
    return f"{number:,}".replace(",", " ")


def main_quest_total(catalog: Catalog, language: str = "fr") -> int:
    """Combien de quêtes principales le catalogue connaît, 3 924 aujourd'hui.

    Le total de **ce** client, et pas celui du serveur, qui n'a jamais vu de
    catalogue. C'est aussi ce qui rend la soustraction possible : le serveur ne
    peut compter que ce qu'on lui a envoyé, ce poste sait ce qui existe.

    Les quêtes principales seulement, comme partout ailleurs : ce sont les
    seules que le chronomètre mesure, donc les seules dont une couverture veut
    dire quelque chose.
    """
    return sum(len(chain.quests) for chain in catalog.chains(language).values())


def format_coverage(coverage: Coverage | None, main_quests: int) -> tuple[str, str, str] | None:
    """Les trois tranches de la couverture : vertes, oranges, jamais mesurées.

    ⚠️ **Le serveur ne rend pas les grises, et c'est délibéré.** Il ne connaît
    que les quêtes ayant reçu au moins une mesure ; les 3 924 quêtes
    principales sont un fait du catalogue, que le client porte. La soustraction
    se fait donc ici, et ne se demande pas au serveur.

    Rend `None` quand le serveur n'a rien dit, ou quand le catalogue manque.
    Trois zéros à la place se liraient comme « personne n'a jamais rien
    mesuré », qui est une affirmation, et une fausse : la bonne réponse est
    « je ne sais pas ».

    Aucun pourcentage, aucun arrondi flatteur. « 0 verte, 11 orange, 3 913
    jamais mesurées » est le vrai chiffre du jour, et c'est celui qui donne
    l'échelle de ce qui reste.
    """
    if coverage is None or main_quests <= 0:
        return None
    # Le plancher à zéro couvre le catalogue plus court que ce que le serveur a
    # reçu : un client d'une version antérieure, ou une langue dont le
    # référentiel a pris du retard. Un nombre négatif de quêtes grises se
    # verrait, mais après avoir été affiché.
    never = max(0, main_quests - coverage.well_measured - coverage.lightly_measured)
    return (
        f"{_grouped(coverage.well_measured)} vert{'es' if coverage.well_measured > 1 else 'e'}",
        f"{_grouped(coverage.lightly_measured)} orange",
        f"{_grouped(never)} jamais mesurée{'s' if never > 1 else ''}",
    )


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
