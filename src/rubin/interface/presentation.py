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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from ..capture import Rect
from ..reference import Catalog, Quest, QuestId, fold
from ..references import (
    MIN_SAMPLES_PER_QUEST,
    RANKING_LIMIT,
    Coverage,
    QuestReference,
    RankedQuest,
    ServerHealth,
)
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


#: Le cadenas qui marque une commande verrouillée pendant la mesure.
#:
#: Un caractère et non une image : il doit rester lisible sur le libellé du
#: bouton lui-même, à côté du texte, sans dépendre d'un fichier à empaqueter.
LOCK_MARK: Final = "🔒"


def zone_lock_reason() -> str:
    """Pourquoi les commandes de zone sont verrouillées pendant la mesure.

    **La raison principale n'est pas la prudence, c'est que ça ne marcherait
    pas.** La zone d'une session est calculée **une seule fois**, au démarrage,
    et `ScreenCapture` retient ensuite un rectangle fixe : voir
    `MeasuringSession._run`. Retracer une zone pendant la mesure enregistre bien
    le nouveau rectangle dans les réglages, mais la session en cours continue
    sur l'ancien, sans que rien ne le dise.

    C'est le pire des cas de ce projet, et le même que la zone sans taille de
    fenêtre : le joueur croit avoir corrigé, il a corrigé quelque chose, et
    l'effet n'arrive pas. Il attribuera ensuite au réglage un silence qui vient
    d'ailleurs, et cherchera là où il n'y a rien.

    La seconde raison est mesurée à moitié seulement, et elle est écrite ici
    comme une prudence, pas comme un fait : « Lire maintenant » et « Choix
    automatique » lancent une reconnaissance **dans le processus qui mesure**.
    Le 5 août 2026, une session a vu passer un bandeau sur une seule image là où
    un témoin extérieur en voyait vingt et une, et la concurrence entre deux
    reconnaissances dans le même processus est l'une des rares différences que
    les essais n'ont pas reproduites. Ce n'est pas prouvé ; c'est une raison de
    plus de ne pas les laisser se marcher dessus pendant qu'on cherche.
    """
    return (
        "Verrouillé pendant la mesure. La zone d'une session est calculée à son "
        "démarrage : la retracer maintenant n'aurait aucun effet sur la session "
        "en cours, et vous croiriez avoir corrigé quelque chose. Arrêtez la "
        "session pour y toucher."
    )


#: Les commandes de l'onglet Zones verrouillées pendant une session.
#:
#: Toutes celles qui écrivent une zone ou qui lancent une reconnaissance. Une
#: seule table, pour que le libellé, le cadenas et l'état suivent ensemble : deux
#: listes parallèles finiraient par diverger, et un bouton oublié resterait
#: cliquable sans que rien ne le signale.
LOCKED_WHILE_MEASURING: Final = (
    "read_now",
    "reset",
    "auto",
    "adopt",
    "pick_banner",
    "pick_tracker",
    "pick_choice",
)


def lock_label(label: str, locked: bool) -> str:
    """Le libellé d'un bouton, avec son cadenas quand il est verrouillé.

    Le cadenas est **dans le libellé**, pas à côté : un bouton grisé se
    remarque à peine, et l'utilisateur qui clique sans effet en conclut que le
    logiciel ne répond plus. Le cadenas dit que le refus est voulu.
    """
    return f"{LOCK_MARK} {label}" if locked else label


#: Au-delà de ce silence, la ligne de surveillance devient un avertissement.
#:
#: Quarante-cinq secondes, parce que c'est le temps qu'il faut pour douter sans
#: que ce soit encore anormal : une quête courante dure une à deux minutes, donc
#: aucun bandeau pendant quarante-cinq secondes arrive tous les jours. Le seuil
#: ne sert pas à accuser, il sert à ce que le joueur qui SE DEMANDE si ça marche
#: trouve la réponse à l'écran au lieu de la chercher une heure plus tard dans
#: un lot vide.
SILENCE_WARNING: Final = 45.0

#: Part de captures répétées au-delà de laquelle la ligne devient un avertissement.
#:
#: Un quart, et pas moins : le jeu s'immobilise réellement de temps en temps,
#: un menu ouvert, un chargement, et quelques répétitions isolées sont
#: normales. C'est un TAUX SOUTENU qui trahit une capture qui ne renouvelle
#: plus rien, pas une répétition de temps en temps.
REPEAT_WARNING: Final = 0.25


@dataclass(frozen=True)
class Watching:
    """Ce que la surveillance a fait depuis le début de la session.

    Les quatre premiers nombres viennent de `BannerWatcher.stats` et de
    `DeferredWatcher`, qui les comptaient déjà. Ils ne sont pas nouveaux, ils
    étaient seulement invisibles.

    `since_banner` vaut `None` tant qu'aucun bandeau n'a jamais été vu, ce qui
    ne se confond pas avec zéro seconde : `elapsed` porte alors la durée de la
    session, seul chiffre qui permette de juger si ce silence est normal.
    """

    frames: int = 0
    banners_seen: int = 0
    reads: int = 0
    failed: int = 0
    overflowed: int = 0
    #: Captures identiques à la précédente. Voir `BannerWatcher.stats.repeats`,
    #: qui porte la mesure de fond et le cas qui l'a motivée.
    repeated: int = 0
    #: Durée de la session, en secondes.
    elapsed: float = 0.0
    #: Secondes depuis le dernier bandeau vu, ou `None` s'il n'y en a jamais eu.
    since_banner: float | None = None


def format_watching(watching: Watching | None) -> str:
    """Ce que la surveillance a vu, en une ligne, pour rendre son silence lisible.

    **C'est la ligne qui manquait le 5 août 2026**, et son absence a coûté une
    séance entière. La fenêtre affichait « mesure en cours, zone 349x115 »
    pendant quinze minutes sans mesurer une seule quête, et rien, nulle part,
    ne permettait de distinguer les quatre causes possibles : la capture ne
    tourne plus, elle tourne sur une zone qui ne contient pas le bandeau, elle
    voit le bandeau mais refuse de le lire, ou elle le lit sans rien en tirer.
    Il a fallu écrire cinq programmes de diagnostic hors du logiciel pour
    trancher, alors que `BannerWatcher.stats` comptait déjà exactement ces
    quatre nombres et les jetait.

    L'ordre des nombres suit la chaîne, et c'est ce qui rend la ligne
    diagnostique : le premier qui reste à zéro désigne l'étage en panne.

    Le temps depuis le dernier bandeau est là pour la même raison que le
    chronomètre en direct : « 0 bandeau » sur une session de dix secondes est
    normal, sur une session de dix minutes c'est la panne elle-même.
    """
    if watching is None:
        return ""
    morceaux = [
        f"{_grouped(watching.frames)} images",
        f"{_grouped(watching.banners_seen)} bandeaux vus",
        f"{_grouped(watching.reads)} lectures",
    ]
    if watching.failed:
        morceaux.append(f"{_grouped(watching.failed)} sans résultat")
    if watching.overflowed:
        # Jamais normal : la lecture ne suit plus la capture. Le dire plutôt que
        # de laisser croire à des bandeaux jamais apparus.
        morceaux.append(f"⚠ {_grouped(watching.overflowed)} images perdues")
    if watching.frames and watching.repeated / watching.frames >= REPEAT_WARNING:
        # Le jeu redessine en permanence, même un personnage immobile a de
        # l'herbe qui bouge : un taux élevé d'images identiques signale une
        # capture qui répète au lieu de produire du neuf, pas un joueur AFK.
        morceaux.append(
            f"⚠ {_grouped(watching.repeated)} images répétées sur {_grouped(watching.frames)}"
        )
    ligne = ", ".join(morceaux)
    if watching.banners_seen == 0 and watching.elapsed >= SILENCE_WARNING:
        # Le seul cas où la ligne devient un avertissement. Voir la constante.
        return f"{ligne} — aucun bandeau depuis {format_duration(watching.elapsed)}"
    if watching.since_banner is not None and watching.since_banner >= SILENCE_WARNING:
        return f"{ligne} — dernier bandeau il y a {format_duration(watching.since_banner)}"
    return ligne


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


def other_quest_total(catalog: Catalog, language: str = "fr") -> int:
    """Les quêtes du catalogue que Rubin ne mesure pas, 15 075 aujourd'hui.

    Le catalogue en connaît 18 999, dont 3 924 principales réparties en 349
    chaînes. Le reste, ce sont les quotidiennes, les répétables, les quêtes de
    métier, celles de l'Esprit noir.

    ⚠️ **Ce nombre ne rejoint JAMAIS le total de la couverture, et c'est tout
    l'intérêt de le calculer à part.** Rubin ne mesure que les principales, et
    c'est délibéré : chronométrer une quête répétable n'a aucun sens puisqu'on la
    refait indéfiniment. Voir `Quest.is_main`. Les mêler donnerait un chiffre
    décourageant **et** faux, puisqu'on n'a jamais eu l'intention de les mesurer :
    le dénominateur de la couverture reste 3 924.

    Le plancher à zéro couvre le catalogue où tout serait principal, qui
    n'existe pas mais ne coûte rien à prévoir.
    """
    tout = sum(len(chain.quests) for chain in catalog.chains(language, kind=None).values())
    return max(0, tout - main_quest_total(catalog, language))


def format_other_quests(others: int) -> str | None:
    """Le rappel des quêtes hors périmètre, ou `None` s'il n'y en a pas.

    Dit **pourquoi** elles n'y sont pas, et pas seulement combien. « 15 075
    autres » posé sans explication à côté de « 3 913 jamais mesurées » se
    lirait comme un arriéré de travail, alors que c'est exactement l'inverse :
    ce sont les quêtes que Rubin ne mesurera jamais, par conception.
    """
    if others <= 0:
        return None
    return f"+ {_grouped(others)} quêtes non principales, que Rubin ne mesure pas"


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


# --------------------------------------------------------------- témoin de serveur

#: Les trois états du lien au serveur, et la balise de couleur de chacun.
#:
#: Les balises sont celles de `theme.COLORS`, jamais de nouvelles couleurs : la
#: légende des pastilles emploie déjà les mêmes, et un quatrième vert voisin du
#: premier ne se distinguerait de rien.
#:
#: ⚠️ **Chaque état porte un mot**, et la couleur ne fait que le doubler. C'est
#: déjà la règle de la légende : rien ne doit reposer sur la couleur seule.
LINK_TAGS: Final = {"absent": "faible", "injoignable": "alerte", "connecte": "sur"}


def format_link(base_url: str | None, health: ServerHealth | None) -> tuple[str, str]:
    """Le témoin de connexion : ce qu'il faut lire, et de quelle couleur.

    **Trois états, et ils appellent trois gestes différents**, d'où trois
    messages qui ne se ressemblent pas :

    - **aucun serveur configuré** : la fenêtre a été lancée sans `--envoyer`.
      Ce n'est pas une panne, c'est un choix, et le dire ainsi évite de chercher
      un problème qui n'existe pas ;
    - **configuré mais injoignable** : réseau coupé, machine éteinte, adresse
      fausse. Là, il y a quelque chose à réparer ;
    - **connecté**, avec l'adresse et ce que le serveur a déjà reçu.

    ⚠️ **Un point d'entrée manquant n'est pas une panne de connexion.** Cas réel
    du 05/08/2026 : `rubin.maxyull.fr` répondait parfaitement, mais rendait 404
    sur `/v1/couverture` parce qu'il tournait sur une version antérieure.
    Annoncer « serveur injoignable » aurait envoyé chercher l'erreur du mauvais
    côté. Ce témoin ne regarde donc que `/sante`, qui existe depuis le premier
    jour ; c'est à chaque compteur de dire séparément que **lui** n'a pas eu sa
    réponse.
    """
    if base_url is None:
        return (
            "aucun serveur : lancé sans --envoyer, rien ne partira",
            LINK_TAGS["absent"],
        )
    if health is None:
        return (f"serveur injoignable : {base_url}", LINK_TAGS["injoignable"])
    mesures = "mesure" if health.measures == 1 else "mesures"
    return (
        f"connecté à {base_url}   ({health.measures} {mesures} reçues)",
        LINK_TAGS["connecte"],
    )


# ------------------------------------------------------------- classement par quête

#: Ce qui s'affiche à la place du classement quand le serveur n'a rien dit.
RANKING_UNAVAILABLE: Final = "classement indisponible : le serveur ne l'a pas donné"


def quest_display_name(
    catalog: Catalog | None, quest_id: QuestId, language: str = "fr"
) -> str:
    """Le nom d'une quête, ou son identifiant à défaut.

    ⚠️ **Le nom vient du catalogue, jamais du serveur.** Le serveur ne connaît
    que `chaine/position` et ne doit pas prétendre connaître des noms : rien ne
    lui garantit que tous les clients lisent le même référentiel, ni la même
    langue. La résolution appartient donc à ce côté-ci, qui porte le catalogue.

    À défaut, l'identifiant brut plutôt qu'un blanc : « 21403/1 » est laid mais
    vrai, et il se cherche dans le référentiel. Un blanc ne se cherche pas.
    """
    quest = catalog.get(quest_id, language) if catalog else None
    return quest.name if quest else str(quest_id)


def format_measure_line(
    duration_text: str, name: str, marque: str, score: int
) -> tuple[str, int, int]:
    """La ligne « temps · nom · score » d'une quête faite, et les bornes du nom.

    Demandé par Maxime le 05/08/2026 : un visuel plus lisible que les deux
    lignes précédentes, temps et nom d'un côté, score et détail de l'autre,
    et le nom cliquable pour rejoindre sa fiche.

    Les bornes sont en index de **caractères** dans la ligne rendue, pour que
    l'appelant les recopie tel quel dans un index Tk `"1.{début}"` sans refaire
    le calcul de largeur : un second calcul, ailleurs, finirait par diverger du
    premier le jour où l'un des deux formats change, et la zone cliquable
    tomberait à côté du texte qu'elle est censée couvrir.
    """
    préfixe = f"{duration_text}  ·  "
    nom_affiché = f"{name}{marque}"
    ligne = f"{préfixe}{nom_affiché}  ·  {score}/100"
    return ligne, len(préfixe), len(préfixe) + len(nom_affiché)


def format_ranked_quest(rank: int, item: RankedQuest, name: str) -> str:
    """Une ligne du classement : son rang, son temps, son nom, son assise.

    Le nombre de mesures est **sur la ligne**, comme partout ailleurs dans ce
    projet, et ici il compte plus qu'ailleurs : un classement de quêtes sur peu
    de mesures est faux et convaincant.
    """
    mesures = "mesure" if item.samples == 1 else "mesures"
    return (
        f"{rank:>2}. {format_duration(item.median_seconds):>12}   "
        f"{name}   ({item.samples} {mesures})"
    )


def format_ranking(
    quests: Sequence[RankedQuest] | None,
    catalog: Catalog | None,
    language: str = "fr",
) -> tuple[str, ...]:
    """Les lignes du classement, dans l'ordre où elles s'affichent.

    Vide quand il n'y a rien à montrer, quelle qu'en soit la raison :
    `ranking_message` dit laquelle, et les deux vont toujours ensemble.
    """
    if not quests:
        return ()
    return tuple(
        format_ranked_quest(rang, item, quest_display_name(catalog, item.quest_id, language))
        for rang, item in enumerate(quests, start=1)
    )


def ranking_message(
    quests: Sequence[RankedQuest] | None, min_samples: int = MIN_SAMPLES_PER_QUEST
) -> str | None:
    """Ce qu'il faut dire quand le classement ne montre rien, sinon `None`.

    ⚠️ **Une liste vide et une absence de réponse ne disent pas la même chose**,
    et c'est tout l'objet de cette fonction. Un tableau vide et muet se lit comme
    « aucune quête n'est rapide », ce qui ne veut rien dire. Les deux vraies
    réponses sont :

    - « aucune quête n'a encore assez de mesures pour être classée », qui est
      l'état du jour : la base contient vingt-et-une mesures, presque toutes
      uniques par quête, donc rien n'atteint le seuil de trois ;
    - « le serveur ne l'a pas donné », qui couvre aussi bien la panne que le
      serveur d'une version antérieure, sans encore ce point d'entrée.

    C'est la même règle que le compteur de couverture : quand on ne sait pas, on
    le dit, on n'affiche pas un zéro qui se lirait comme une affirmation.
    """
    if quests is None:
        return RANKING_UNAVAILABLE
    if not quests:
        mesures = "mesure" if min_samples == 1 else "mesures"
        return (
            "aucune quête n'a encore assez de mesures pour être classée "
            f"({min_samples} {mesures} au minimum)"
        )
    return None


# ------------------------------------------------------------- mode démonstration

#: La marque posée sur chaque ligne fabriquée. En toutes lettres, et pas
#: seulement une couleur : une capture d'écran se transmet en noir et blanc, se
#: recadre, et une couleur seule ne survit ni à l'une ni à l'autre.
DEMO_MARK: Final = "TEST"

#: Le bandeau posé au-dessus du tableau quand la démonstration est allumée.
DEMO_BANNER: Final = (
    "MODE DÉMONSTRATION : les lignes marquées TEST sont FABRIQUÉES. "
    "Elles ne sont ni mesurées, ni enregistrées, ni envoyées à personne."
)

#: Durées de démonstration, en secondes, dans l'ordre du classement.
#:
#: Une table figée plutôt qu'un tirage au sort : une démonstration qui change à
#: chaque ouverture donne l'illusion de données vivantes, ce qui est exactement
#: l'impression à ne pas donner. Les valeurs sont plausibles, croissantes, et
#: n'ont aucune vertu statistique.
DEMO_SECONDS: Final = (42.0, 55.0, 68.0, 90.0, 112.0, 135.0, 168.0, 210.0, 260.0, 320.0)


def demo_active(quests: Sequence[RankedQuest] | None, wanted: bool) -> bool:
    """Faut-il montrer la démonstration, sachant ce que le serveur a rendu.

    **Elle s'efface d'elle-même**, et c'est le seuil du classement qui en
    décide, pas un compteur séparé : dès que le serveur rend un classement
    complet, il n'y a plus rien à démontrer, et de fausses lignes à côté de
    vraies seraient le pire des deux mondes.
    """
    return wanted and len(quests or ()) < RANKING_LIMIT


def demo_ranking(
    catalog: Catalog | None, language: str = "fr", count: int = RANKING_LIMIT
) -> tuple[str, ...]:
    """Un classement FABRIQUÉ, pour voir le tableau rempli avant d'avoir mesuré.

    ⛔ **Ces lignes ne sont pas des mesures, et n'en deviendront jamais.** Le
    principe fondateur du projet est écrit partout : rater une mesure donne un
    chiffre incomplet, en inventer une donne un chiffre faux, et un chiffre faux
    entre dans les médianes sans jamais en ressortir.

    D'où la forme retenue, qui est la garantie elle-même : cette fonction rend
    des **chaînes de caractères déjà mises en forme**, jamais des `RankedQuest`,
    jamais un `MeasurePayload`. Il n'existe à aucun instant, nulle part dans le
    logiciel, un objet de mesure fabriqué qui pourrait se glisser dans un lot,
    dans un fichier de session, ou dans une requête. Le rendu est le même que
    celui des vraies lignes ; le chemin ne l'est pas, et ne peut pas l'être.

    ⚠️ « Ça disparaîtra quand il y aura assez de vraies mesures » n'aurait pas
    suffi comme garde-fou, et c'est ce qui a fait écarter la première idée :
    ce qui disparaît d'un affichage reste en base et continue de peser.

    Chaque ligne porte `TEST` en clair, et le bandeau `DEMO_BANNER` le répète
    au-dessus du tableau.
    """
    noms = _demo_names(catalog, language, count)
    return tuple(
        f"{rang:>2}. {DEMO_MARK}  {format_duration(secondes):>12}   {nom}   (fabriquée)"
        for rang, (secondes, nom) in enumerate(zip(DEMO_SECONDS, noms, strict=False), start=1)
    )


def _demo_names(catalog: Catalog | None, language: str, count: int) -> tuple[str, ...]:
    """Des noms de quêtes pour la démonstration, vrais si le catalogue est là.

    De vrais noms parce que c'est la longueur des noms réels qui met la mise en
    page à l'épreuve, et c'est bien ce qu'on vient regarder. Ce sont les seuls
    éléments véridiques de ces lignes ; les durées, elles, sont inventées et le
    disent.
    """
    if catalog is None:
        return tuple(f"quête de démonstration {index}" for index in range(1, count + 1))
    noms = [
        quest.name
        for chain in catalog.chains(language).values()
        for quest in chain.quests
    ]
    if not noms:
        return tuple(f"quête de démonstration {index}" for index in range(1, count + 1))
    return tuple(noms[index % len(noms)] for index in range(count))


# ------------------------------------------------------------------ recherche

#: Nombre de résultats proposés. Au-delà, ce n'est plus une recherche, c'est une
#: liste à faire défiler, et il vaut mieux taper deux lettres de plus.
SEARCH_LIMIT: Final = 12

#: En dessous de ce nombre de caractères, on ne cherche pas.
#:
#: Deux lettres rendraient des centaines de quêtes, donc une liste inutile, et
#: feraient replier le catalogue entier à chaque frappe.
SEARCH_MIN_LENGTH: Final = 3


def search_quests(
    catalog: Catalog | None,
    text: str,
    language: str = "fr",
    limit: int = SEARCH_LIMIT,
) -> tuple[Quest, ...]:
    """Les quêtes dont le nom contient ce qui est tapé.

    ⚠️ **La comparaison passe par `fold`, des deux côtés**, sinon on ne trouve
    rien. Le catalogue porte « [Calpheon] Ce qui s'est passé jusqu'à présent » ;
    on tape « ce qui sest passe », sans crochets, sans accents, sans apostrophe.
    `fold` réduit les deux à la même forme, celle qui a déjà été retenue pour la
    reconnaissance, qui avale les espaces et la ponctuation.

    ⚠️ **Les quêtes principales seulement.** Ce sont les seules que Rubin
    mesure : proposer les 15 075 autres ferait cliquer sur des quêtes qui
    n'auront jamais de temps, et une recherche qui rend des impasses est pire
    qu'une recherche qui rend peu.

    Le tri suit la chaîne puis la position, c'est-à-dire l'ordre du jeu : deux
    quêtes voisines d'une même chaîne se retrouvent côte à côte, ce qu'un tri
    alphabétique casserait.
    """
    besoin = fold(text)
    if catalog is None or len(besoin) < SEARCH_MIN_LENGTH:
        return ()
    trouvées = [
        quest
        for chain in catalog.chains(language).values()
        for quest in chain.quests
        if besoin in fold(quest.name)
    ]
    trouvées.sort(key=lambda q: (q.id.chain, q.id.position))
    return tuple(trouvées[:limit])


def format_search_result(quest: Quest) -> str:
    """Une ligne de résultat : le nom, et où il se trouve dans le jeu."""
    return f"{quest.name}   [{quest.id.chain}/{quest.id.position}]"


def format_quest_times(quest: Quest, reference: QuestReference | None) -> str:
    """Ce que le serveur sait des temps d'une quête, en toutes lettres.

    ⚠️ **Une quête jamais mesurée le dit**, jamais une colonne vide : un blanc
    se lit « instantané », c'est-à-dire l'inverse de « inconnu ». C'est la même
    règle que `format_reference`, et le même écueil.

    Le record est rendu **à côté** de la médiane, jamais à sa place : le
    classement se fait sur la médiane, un record se falsifie en un seul envoi.
    Le montrer ici renseigne sans rien classer.
    """
    entête = f"{quest.name}   [{quest.id.chain}/{quest.id.position}]"
    if reference is None or reference.samples <= 0:
        return f"{entête}\njamais mesurée, personne n'a encore envoyé de temps"
    mesures = "mesure" if reference.samples == 1 else "mesures"
    lignes = [
        entête,
        f"médiane : {format_duration(reference.median_seconds)}   "
        f"({reference.samples} {mesures})",
        f"meilleur temps connu : {format_duration(reference.fastest_seconds)}",
    ]
    if reference.samples < FRAGILE_BELOW:
        lignes.append("peu sûr : trop peu de mesures pour que ce temps fasse référence")
    return "\n".join(lignes)


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
    #: Vrai quand un tracé existe pour cette zone, mais pour une taille de
    #: fenêtre INCONNUE : un fichier écrit avant la table `zones` de #58, ou une
    #: résolution jamais revue depuis. `Settings.zone_for` ne l'applique à
    #: aucune taille, exprès, donc la zone montrée ici est la **calculée**, pas
    #: le tracé perdu.
    #:
    #: Sans cette ligne, un joueur dont l'ancien tracé a cessé de s'appliquer ne
    #: le saurait jamais : c'est exactement ce qui a coûté une matinée de
    #: mesures le 5 août 2026, une zone à y=1224 restée active sans que rien ne
    #: le montre, alors que `zone_for` disait déjà « non » depuis #58.
    stray: bool = False


def describe_zone(state: ZoneState) -> str:
    """Résume une zone en une ligne : d'où elle vient, et où elle est."""
    origine = "choisie" if state.chosen else "calculée"
    base = (
        f"{state.name} : {state.rect.width}x{state.rect.height} "
        f"en ({state.rect.left}, {state.rect.top}), {origine}"
    )
    if state.stray:
        base += " — ancien tracé disponible, bouton « Reprendre l'ancien tracé »"
    return base


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
