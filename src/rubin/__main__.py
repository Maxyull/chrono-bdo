"""Ligne de commande.

Quatre commandes. `referentiel` construit le catalogue et dit ce qu'il contient,
ce qui vérifie que la source répond et que son format n'a pas changé. `suivre`
est le chronomètre lui-même. `echecs` montre les bandeaux qui n'ont pas pu être
lus et en fabrique une archive à envoyer à la main. `verifier` contrôle que
l'installation est complète.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from platformdirs import user_data_dir

from .capture import Rect, ScreenCapture, banner_region, find_game_window, tracker_region
from .capture.window import TITLE_FRAGMENTS, _candidates
from .deferred import DeferredWatcher
from .failures import DESTINATIONS, FailureStore, find_destination, larger_than
from .protocol import PlayerIdentity, build_session
from .reading import RapidOcrReader
from .reference import Catalog
from .reference.source import catalog_date, load
from .references import ReferenceClient
from .timing import Measure, Quality, Timeline
from .tracking import TrackedQuests, read_tracker
from .upcoming import DEFAULT_COUNT, UpcomingQuest, crossroads_ahead, upcoming
from .updates import check_for_update
from .upload import save_session, send_session
from .watching import BannerWatcher

#: Cadence de la boucle. Huit fois par seconde suffisent : le bandeau reste
#: affiché plusieurs secondes, et une capture ne coûte que 4 millisecondes.
POLL_INTERVAL = 0.125


def _setup_console() -> None:
    """Sort en UTF-8, quelle que soit la console.

    Sans cela, la console Windows par défaut refuse les accents et le
    programme s'arrête sur un nom de quête, ce qui serait un comble.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _home() -> Path:
    """Le dossier de données du logiciel, chez l'utilisateur courant."""
    return Path(user_data_dir("rubin-bdo", "maxyull"))


def _load_catalog(languages: Sequence[str], refresh: bool = False) -> Catalog:
    payloads = {lang: load(lang, refresh=refresh) for lang in languages}
    return Catalog.from_payloads(payloads)


def _format_duration(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min {rest:02d} s" if minutes else f"{rest} s"


def _print_measure(
    measure: Measure,
    catalog: Catalog,
    language: str,
    references: ReferenceClient | None = None,
) -> None:
    quest = catalog.get(measure.quest_id, language)
    name = quest.name if quest else str(measure.quest_id)
    mark = "" if measure.quality is Quality.EXACT else "  (déduite)"

    # La référence est la seule information vraiment utile sur le moment : une
    # durée seule ne dit rien tant qu'on ne sait pas à quoi la comparer.
    suffix = ""
    if references is not None and references.enabled:
        known = references.quest(measure.quest_id)
        if known is not None:
            echantillons = "mesure" if known.samples == 1 else "mesures"
            suffix = (
                f"   [référence {_format_duration(known.median_seconds)}"
                f" sur {known.samples} {echantillons}, {known.compare(measure.seconds)}]"
            )
        else:
            # Le dire plutôt que de laisser un blanc : une quête que personne
            # n'a mesurée est une information en soi, et c'est celle que la
            # session du joueur vient justement de combler.
            suffix = "   [aucune référence, vous êtes le premier]"
    print(f"  {_format_duration(measure.seconds):>12}   {name}{mark}{suffix}")


def command_reference(args: argparse.Namespace) -> int:
    try:
        catalog = _load_catalog(("fr", "en"), refresh=args.refresh)
    except Exception as error:  # message lisible plutôt qu'une trace
        print(f"référentiel indisponible : {error}", file=sys.stderr)
        return 1

    chains = catalog.chains("fr")
    quests = sum(len(chain) for chain in chains.values())
    complete = sum(1 for chain in chains.values() if chain.is_contiguous)

    print(f"{len(catalog)} quêtes au catalogue, en {', '.join(catalog.languages)}")
    print(f"{quests} quêtes principales réparties en {len(chains)} chaînes")
    print(f"{complete} chaînes sans trou de numérotation, {len(chains) - complete} à compléter")

    main_ids = {quest.id for chain in chains.values() for quest in chain.quests}
    ambiguous = [
        ids for ids in catalog.ambiguous_names("fr").values() if any(i in main_ids for i in ids)
    ]
    affected = sum(1 for ids in ambiguous for i in ids if i in main_ids)
    if affected:
        share = 100 * affected / quests
        print(
            f"{affected} quêtes principales ({share:.0f}%) partagent leur nom avec une autre "
            f"et exigent la chaîne en cours pour être identifiées"
        )
    return 0


def command_watch(args: argparse.Namespace) -> int:
    window = find_game_window()
    if window is None:
        print(
            "fenêtre du jeu introuvable. Lancez Black Desert, puis relancez.",
            file=sys.stderr,
        )
        return 1

    region = banner_region(window, ui_scale=args.ui_scale)
    print(f"fenêtre {window.width}x{window.height}, zone surveillée {region.width}x{region.height}")

    try:
        catalog = _load_catalog((args.language,))
    except Exception as error:  # message lisible plutôt qu'une trace
        print(f"référentiel indisponible : {error}", file=sys.stderr)
        return 1
    print(f"{len(catalog)} quêtes chargées. Jouez normalement, Ctrl+C pour arrêter.\n")

    timeline = Timeline(catalog=catalog, language=args.language)
    started = time.monotonic()
    reader = RapidOcrReader()
    # Les lectures ratées sont gardées sur le disque, et n'en sortent que si le
    # joueur fabrique une archive et l'envoie lui-même. La purge a lieu avant la
    # session plutôt qu'après : une session s'arrête souvent par un Ctrl+C, et un
    # ménage placé à la fin ne serait jamais fait.
    failures = FailureStore(_home() / "echecs")
    failures.purge()
    deferred = None
    # Dernière position pour laquelle la liste a été montrée. Sert à ne pas la
    # réafficher à l'identique sur les bandeaux d'objectif, qui racontent ce qui
    # se passe pendant une quête sans faire avancer d'un cran.
    last_seen: tuple[int | None, int | None] = (None, None)
    # Les références sont lues sur le serveur d'envoi, sans qu'envoyer soit
    # nécessaire pour les consulter : la lecture est publique.
    references = ReferenceClient(args.server or args.references)

    # Où en est le joueur, tout de suite, sans attendre le premier bandeau.
    # Le panneau sous la minimap est affiché en permanence, contrairement au
    # bandeau qui n'apparaît qu'aux transitions.
    tracked = _locate_from_tracker(window, args.ui_scale, reader, catalog, args.language)
    if tracked is not None and tracked.chain is not None:
        active = tracked.active
        print(f"panneau de suivi : {len(tracked)} quêtes suivies, chaîne {tracked.chain}")
        if active is not None:
            en_cours = catalog.get(active, args.language)
            print(f"en cours : {en_cours.name if en_cours else active}")
            _print_upcoming_from(
                active.chain,
                active.position,
                catalog,
                references,
                args.language,
                args.upcoming,
            )
            # Mémorisée pour que le premier bandeau ne réaffiche pas la même
            # liste juste après.
            last_seen = (active.chain, active.position)
        print()

    try:
        with ScreenCapture(region) as capture:
            watcher = BannerWatcher(capture, reader)
            # La capture et la lecture vivent dans deux fils séparés : sinon,
            # l'écran cesserait d'être surveillé pendant chaque reconnaissance,
            # soit jusqu'à une seconde, et un bandeau qui apparaît puis
            # disparaît dans cet intervalle serait perdu en silence.
            with DeferredWatcher(
                watcher, reader, interval=POLL_INTERVAL, failures=failures
            ) as deferred:
                while True:
                    for reading, at in deferred.readings(timeout=1.0):
                        # L'instant retenu est celui de la capture, pas celui
                        # de la lecture : sans quoi chaque mesure serait
                        # allongée de la durée de sa propre reconnaissance.
                        measure = timeline.record(reading, at=at)
                        if measure is not None:
                            _print_measure(measure, catalog, args.language, references)
                        # La liste suit la POSITION, pas la mesure. La première
                        # quête d'une session n'en clôt aucune, faute de quête
                        # précédente : l'écran restait vide alors qu'on savait
                        # déjà où était le joueur. Suivre la position affiche
                        # aussi la liste sans attendre, quand on démarre le
                        # logiciel au milieu d'une chaîne déjà commencée.
                        here = (timeline.current_chain, timeline.current_position)
                        if here != last_seen and here[0] is not None:
                            _print_upcoming(
                                timeline, catalog, references, args.language, args.upcoming
                            )
                            last_seen = here
    except KeyboardInterrupt:
        pass

    elapsed = time.monotonic() - started
    print()
    if not timeline.measures:
        print(f"aucune quête mesurée en {_format_duration(elapsed)}")
        if watcher.stats.banners_seen == 0:
            # Le cas le plus probable d'un premier essai qui ne donne rien.
            print(
                "aucun bandeau n'a été vu : vérifiez que le jeu est bien au premier plan, "
                "et que l'échelle de l'interface n'a pas été modifiée (--echelle)"
            )
        _print_failures(deferred, failures)
        return 0

    measured = sum(m.seconds for m in timeline.measures)
    exact = sum(1 for m in timeline.measures if m.quality is Quality.EXACT)
    rate = 3600 * len(timeline.measures) / measured if measured else 0
    print(
        f"{len(timeline.measures)} quêtes mesurées en {_format_duration(measured)}, "
        f"soit {rate:.0f} quêtes par heure"
    )
    print(f"{exact} mesures exactes, {len(timeline.measures) - exact} déduites")
    if timeline.dropped:
        # Dit ce qui a été perdu plutôt que de le taire : un chiffre incomplet
        # qui s'annonce reste utilisable.
        print(f"{timeline.dropped} quêtes vues mais non mesurables")

    _print_chain_summary(timeline, references, catalog, args.language)
    _print_failures(deferred, failures)
    _finish_session(timeline, args)
    return 0


def _print_failures(deferred: DeferredWatcher | None, failures: FailureStore) -> None:
    """Dit combien de bandeaux ont été vus sans pouvoir être lus.

    Ce chiffre manquait, et son absence coûtait cher : une session qui ne
    mesurait rien ne disait pas si le jeu n'avait rien montré, ou si le logiciel
    n'avait rien su lire. Ce sont deux pannes opposées, avec deux remèdes
    opposés.
    """
    if deferred is None or not deferred.failed:
        return
    print()
    print(f"{deferred.failed} bandeaux vus mais illisibles, gardés dans {failures.directory}")
    if failures.unwritable:
        # Un dossier vide ne doit pas se lire comme « aucun échec ».
        print(f"({failures.unwritable} n'ont pas pu être écrits sur le disque)")
    print("« rubin echecs --archiver » en fait une archive, si vous voulez aider à corriger")


def _print_window_candidates() -> None:
    """Dit quel programme a été retenu, et lesquels ont été écartés.

    Sans cette ligne, la vérification annonçait « fenêtre du jeu... 2560x1392 »
    puis « tout est en ordre » en pointant un navigateur, et rien à l'écran ne
    permettait de s'en apercevoir. Une vérification qui ne dit pas **sur quoi**
    elle a porté ne vérifie rien.
    """
    for fragment in TITLE_FRAGMENTS:
        for candidate in _candidates(fragment.lower()):
            programme = candidate.executable or "programme inconnu"
            if candidate.is_other_program:
                verdict = "écarté, ce n'est pas le jeu"
            elif candidate.is_game:
                verdict = "retenu"
            else:
                verdict = "retenu faute de mieux"
            print(
                f"  {programme:<22} {candidate.rect.width}x{candidate.rect.height}  {verdict}"
            )


def _locate_from_tracker(
    window: Rect,
    ui_scale: float,
    reader: RapidOcrReader,
    catalog: Catalog,
    language: str,
) -> TrackedQuests | None:
    """Lit le panneau de suivi pour savoir où en est le joueur, sans attendre.

    Le bandeau ne dit où l'on est qu'au moment d'une transition. Le panneau
    sous la minimap, lui, est affiché **en permanence** : il répond dès le
    lancement, y compris quand on démarre le logiciel au milieu d'une chaîne
    déjà entamée, qui est le cas le plus courant.

    Lu **une seule fois**, au démarrage. La zone est six fois plus grande que
    celle du bandeau, donc la reconnaissance y coûte 1,9 seconde contre 0,3 :
    la relire en boucle mangerait le fil de lecture pour une information qui ne
    change qu'entre deux quêtes, et que le bandeau annonce déjà.

    Ce que la lecture apprend ne sert qu'à **afficher** la liste des quêtes à
    venir. Elle n'entre ni dans le journal d'événements, ni dans les mesures :
    le panneau tronque les noms trop longs, donc une ligne mal reconnue y est
    normale. Une position lue de travers qui servirait à identifier une quête
    lui attribuerait un temps qui n'est pas le sien, et ce chiffre faux entrerait
    dans les médianes. Un affichage faux se remarque et ne coûte rien.

    Rend `None` sur la moindre difficulté : cette lecture est un confort, elle
    ne doit jamais empêcher une session de démarrer.
    """
    try:
        with ScreenCapture(tracker_region(window, ui_scale=ui_scale)) as capture:
            lines = reader.read(capture.grab_gray())
    except Exception:  # pragma: pas de couverture
        return None
    tracked = read_tracker(lines, catalog, language)
    return tracked if tracked.quests else None


def _print_upcoming(
    timeline: Timeline,
    catalog: Catalog,
    references: ReferenceClient,
    language: str,
    count: int,
) -> None:
    """Montre ce qui vient après la quête qu'on vient de finir.

    C'est la question qu'on se pose en jouant, et à laquelle le bilan de fin de
    session répond trop tard pour qu'elle serve à décider quoi que ce soit.

    Rien n'est affiché quand on ne sait pas où l'on est : une liste tirée d'une
    position inconnue serait une liste au hasard, ce qui est pire que pas de
    liste du tout.
    """
    chain = timeline.current_chain
    position = timeline.current_position
    if chain is None or position is None:
        return
    _print_upcoming_from(chain, position, catalog, references, language, count)


def _print_upcoming_from(
    chain: int,
    position: int,
    catalog: Catalog,
    references: ReferenceClient,
    language: str,
    count: int,
) -> None:
    """Le cœur de l'affichage, depuis une position connue d'où qu'elle vienne.

    Séparé pour que le panneau de suivi, lu au démarrage, et le journal
    d'événements, alimenté par les bandeaux, produisent exactement le même
    affichage. Deux rendus qui divergeraient finiraient par se contredire à
    l'écran, sur les trous ou sur les branches.
    """
    if count <= 0:
        return
    suivantes = upcoming(
        catalog, chain, position, language=language, count=count, references=references
    )
    if not suivantes:
        # Fin de chaîne connue, ou chaîne absente du référentiel. Les deux se
        # produisent normalement et ne méritent pas d'alarme.
        return

    print(f"  à suivre dans la chaîne {chain} :")
    for item in suivantes:
        _print_upcoming_line(item)

    embranchements = crossroads_ahead(suivantes)
    if embranchements:
        # Le référentiel dit lesquelles sont des branches, pas lesquelles
        # s'excluent entre elles. On ne prétend donc pas dire laquelle prendre.
        print(
            f"    {embranchements} de ces quêtes sont des branches d'un choix : "
            "vous n'en ferez pas la totalité"
        )


def _print_upcoming_line(item: UpcomingQuest) -> None:
    """Une ligne de la liste : position, nom, et ce qu'on sait du temps.

    Aucun symbole hors de l'ASCII n'est employé, et ce n'est pas de la
    coquetterie. Un glyphe comme « ⑂ » n'existe pas dans la page de codes
    cp1252 de la console Windows, et son affichage **interrompt la session** par
    une erreur d'encodage si la sortie n'a pas pu être basculée en UTF-8. Même
    quand elle l'a été, la plupart des polices de console le rendent en carré
    vide. Un marqueur illisible qui peut faire tomber le programme ne vaut pas
    les trois caractères qu'il économise.
    """
    if item.gap_before:
        # Enjamber un trou sans rien dire laisserait croire que cette quête
        # suit immédiatement la précédente.
        manquantes = "position inconnue" if item.gap_before == 1 else "positions inconnues"
        print(f"    ... {item.gap_before} {manquantes} du référentiel")

    # Le marqueur va en fin de ligne et non après le nom : accolé au nom, il
    # décale la colonne des temps d'une ligne à l'autre et l'œil ne peut plus
    # les comparer d'un coup, ce qui est pourtant le seul usage de cette liste.
    marque = "   (branche d'un choix)" if item.is_crossroad else ""
    nom = f"{item.quest.id.position}. {item.quest.name}"
    reference = item.reference
    if reference is None:
        # « jamais mesurée » et non une colonne vide ou un zéro : un blanc se
        # lit comme « instantané », l'inverse de ce qu'on veut dire.
        print(f"    {nom:<52} jamais mesurée{marque}")
        return
    mesures = "mesure" if reference.samples == 1 else "mesures"
    temps = (
        f"{_format_duration(reference.median_seconds)} ({reference.samples} {mesures})"
    )
    print(f"    {nom:<52} {temps}{marque}")


def _print_chain_summary(
    timeline: Timeline, references: ReferenceClient, catalog: Catalog, language: str
) -> None:
    """Situe la session dans les chaînes parcourues.

    C'est la question qui compte quand il reste des milliers de quêtes à
    faire : où j'en suis, et ce qu'il reste dans celle-ci.
    """
    if not timeline.measures or not references.enabled:
        return
    toutes = catalog.chains(language, kind=None)
    for number in sorted({m.quest_id.chain for m in timeline.measures}):
        chain = toutes.get(number)
        total = len(chain) if chain else 0
        faites = {m.quest_id.position for m in timeline.measures if m.quest_id.chain == number}
        print()
        accord = "mesurée" if len(faites) <= 1 else "mesurées"
        titre = f"chaîne {number} : {len(faites)} {accord} cette session"
        if total:
            titre += f", {total} quêtes au total"
        print(titre)
        # Un embranchement fait que la chaîne ne sera jamais faite en entier :
        # le total de ses quêtes surestime donc ce qu'il reste à faire.
        embranchements = len(chain.crossroads) if chain else 0
        if embranchements:
            print(
                f"  {embranchements} de ces quêtes sont des embranchements : "
                "vous n'en ferez qu'une partie"
            )

        known = references.chain(number)
        if known is None:
            continue
        print(
            f"  référence : {known.measured_quests} quêtes connues, "
            f"{known.quests_per_hour:.0f} quêtes/heure au rythme médian"
        )
        if total and known.measured_quests < total:
            # Le total connu est un plancher tant que tout n'est pas mesuré,
            # et le présenter autrement serait mentir.
            manquantes = total - known.measured_quests
            print(f"  {manquantes} quêtes de cette chaîne n'ont jamais été chronométrées")
    if references.failures:
        # Dire que les références manquaient, plutôt que de laisser croire que
        # ces quêtes n'avaient jamais été mesurées par personne.
        print()
        print(f"({references.failures} références n'ont pas pu être lues)")


def _finish_session(timeline: Timeline, args: argparse.Namespace) -> None:
    """Écrit le lot sur le disque, et l'envoie si un serveur a été demandé.

    L'écriture a toujours lieu, l'envoi jamais tout seul. Transmettre les
    données de quelqu'un sans qu'il l'ait demandé serait une décision prise à
    sa place, et le fait qu'elles soient anonymes n'y change rien.
    """
    home = _home()
    identity = PlayerIdentity.load_or_create(home / "identite")
    payload = build_session(
        timeline,
        player=identity.value,
        catalog_date=catalog_date(args.language),
        language=args.language,
    )
    written = save_session(payload, home / "sessions" / f"session-{int(time.time())}.json")
    print(f"lot écrit dans {written}")

    if not args.server:
        print("aucun serveur indiqué : rien n'a été envoyé (--envoyer pour contribuer)")
        return
    result = send_session(payload, args.server)
    if result.ok:
        print(f"envoyé : {result.stored} mesures enregistrées, {result.refused} refusées")
    else:
        # Le lot reste sur le disque : une session mesurée ne doit pas
        # disparaître parce que le réseau a hoqueté.
        print(f"envoi impossible, le lot est conservé — {result.detail}", file=sys.stderr)


def command_failures(args: argparse.Namespace) -> int:
    """Montre les lectures ratées, et en fabrique une archive sur demande.

    L'archive ne part nulle part. Elle est écrite sur le disque, et son chemin
    s'affiche : c'est le joueur qui l'envoie, s'il le veut, où il veut. Un envoi
    automatique déciderait à sa place de partager ses images, et le fait qu'elles
    ne montrent qu'un bandeau de quête n'y changerait rien.
    """
    failures = FailureStore(_home() / "echecs")
    removed = failures.purge()
    stats = failures.stats()

    if not stats.images and not stats.entries:
        print(f"aucune lecture ratée retenue ({failures.directory})")
        return 0

    print(
        f"{stats.images} images retenues pour {stats.entries} échecs, "
        f"{stats.kilobytes} Ko dans {failures.directory}"
    )
    if removed:
        print(f"{removed} effacées, trop anciennes ou au-delà du plafond")
    if not args.archive:
        print()
        print("« rubin echecs --archiver » pour en faire une archive à envoyer.")
        _print_destinations()
        return 0

    cible = find_destination(args.destination)
    chemin = _home() / "echecs" / f"rubin-echecs-{int(time.time())}.zip"
    result = failures.package(chemin, max_bytes=cible.max_bytes)
    if result is None:  # pragma: pas de couverture
        print("rien à archiver")
        return 0

    print()
    print(f"archive écrite : {result.path}")
    print(
        f"{result.images} images, {result.kilobytes} Ko "
        f"sur les {cible.kilobytes} Ko que {cible.label} accepte"
    )
    if result.left_out:
        # Une troncature qui se tait se lirait comme un inventaire complet.
        # Texte simple et non un pictogramme : « ⚠ » n'existe pas en cp1252 et
        # interromprait la commande sur une console qui n'a pas pu basculer en
        # UTF-8, pour n'apporter aucune information de plus.
        print(f"ATTENTION : {result.left_out} images laissées dehors, l'archive était pleine")
        plus_grand = larger_than(result.needed)
        if plus_grand is not None and plus_grand.key != cible.key:
            print(
                f"  tout tiendrait dans {plus_grand.kilobytes} Ko : "
                f"« rubin echecs --archiver --vers {plus_grand.key} »"
            )
    print()
    print("elle ne contient que des vignettes de texte de quête en niveaux de gris,")
    print("et les lignes lues. Ni le nom du personnage, ni le chat, ni la carte.")
    print("vous pouvez l'ouvrir avant de l'envoyer.")
    print()
    print(f"à déposer sur {cible.label} : {cible.url}")
    print(f"  {cible.detail}")
    if cible.account:
        print("  (un compte est nécessaire)")
    return 0


def _print_destinations() -> None:
    """Les destinations et ce qu'elles acceptent, en kilo-octets.

    Le plafond est affiché parce qu'il décide du choix : une archive de mille
    échecs passe partout, une reconnaissance qui s'est effondrée pendant une nuit
    entière ne passe plus par la porte la plus étroite.
    """
    print("destinations possibles (--vers) :")
    for candidate in DESTINATIONS:
        compte = ", compte nécessaire" if candidate.account else ", sans compte"
        print(f"  {candidate.key:<12} {candidate.kilobytes:>10} Ko max   {candidate.url}{compte}")


def command_check(args: argparse.Namespace) -> int:
    """Vérifie que l'installation est complète et fonctionnelle.

    Écrite pour deux raisons. Dans une version empaquetée, un fichier manquant
    ne se voit qu'au moment où il sert, c'est-à-dire au milieu d'une session de
    jeu. Et chez quelqu'un d'autre, « ça ne marche pas » n'est pas un
    diagnostic : il faut pouvoir dire quelle étape précise a échoué.
    """
    ok = True

    print("moteur de reconnaissance... ", end="", flush=True)
    try:
        import numpy as np

        from .capture import icon_template
        from .reading import RapidOcrReader, parse_banner

        gabarit = icon_template()
        print(f"chargé (gabarit {gabarit.shape[0]}x{gabarit.shape[1]})")
    except Exception as error:  # message lisible plutôt qu'une trace
        print(f"ÉCHEC : {error}")
        return 1

    print("lecture d'une image témoin... ", end="", flush=True)
    try:
        # Une image fabriquée plutôt qu'une capture de plus à embarquer : ce
        # qu'on vérifie est que le moteur se charge et rend la main, pas ce
        # qu'il lit.
        temoin = np.full((60, 400), 20, dtype=np.uint8)
        temoin[20:40, 20:380] = 200
        lignes = RapidOcrReader().read(temoin)
        print(f"moteur opérationnel ({len(lignes)} zone(s) analysée(s))")
    except Exception as error:  # message lisible plutôt qu'une trace
        print(f"ÉCHEC : {error}")
        ok = False

    print("analyse d'un bandeau... ", end="", flush=True)
    lu = parse_banner([("Nouvelle quete", 0.99), ("[Calpheon] Une quete", 0.98)])
    if lu is None:
        print("ÉCHEC : le bandeau témoin n'a pas été compris")
        ok = False
    else:
        print(f"reconnu ({lu.kind.value})")

    print("référentiel des quêtes... ", end="", flush=True)
    try:
        catalog = _load_catalog((args.language,))
        print(f"{len(catalog)} quêtes")
    except Exception as error:  # message lisible plutôt qu'une trace
        print(f"ÉCHEC : {error}")
        ok = False

    if args.server:
        print("version... ", end="", flush=True)
        status = check_for_update(args.server)
        if status is None:
            print("serveur muet (sans gravité)")
        else:
            print(status.message() or f"{status.current}, à jour")

    print("fenêtre du jeu... ", end="", flush=True)
    window = find_game_window()
    # L'absence du jeu n'est pas une panne : on doit pouvoir vérifier son
    # installation sans avoir lancé Black Desert.
    print(f"{window.width}x{window.height}" if window else "non lancé (sans gravité)")
    if window is not None:
        _print_window_candidates()

    print()
    print("tout est en ordre" if ok else "installation incomplète")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rubin", description="Rubinmètre de quêtes BDO")
    subparsers = parser.add_subparsers(dest="command")

    reference = subparsers.add_parser("referentiel", help="construit le catalogue et le décrit")
    reference.add_argument(
        "--refresh", action="store_true", help="retélécharge même si le cache est récent"
    )
    reference.set_defaults(handler=command_reference)

    watch = subparsers.add_parser("suivre", help="chronomètre les quêtes pendant que vous jouez")
    watch.add_argument(
        "--langue", dest="language", default="fr", choices=("fr", "en"), help="langue du client"
    )
    watch.add_argument(
        "--envoyer",
        dest="server",
        default=None,
        metavar="URL",
        help="adresse du serveur où envoyer les mesures en fin de session",
    )
    watch.add_argument(
        "--references",
        dest="references",
        default=None,
        metavar="URL",
        help="serveur à consulter pour les temps de référence, sans y envoyer",
    )
    watch.add_argument(
        "--echelle",
        dest="ui_scale",
        type=float,
        default=1.0,
        help="échelle de l'interface du jeu, si elle a été modifiée",
    )
    watch.add_argument(
        "--suivantes",
        dest="upcoming",
        type=int,
        default=DEFAULT_COUNT,
        metavar="N",
        help="nombre de quêtes à venir affichées après chaque mesure, 0 pour aucune",
    )
    watch.set_defaults(handler=command_watch)

    failures = subparsers.add_parser("echecs", help="montre les lectures ratées et les archive")
    failures.add_argument(
        "--archiver",
        dest="archive",
        action="store_true",
        help="fabrique une archive à envoyer à la main, pour aider à corriger",
    )
    failures.add_argument(
        "--vers",
        dest="destination",
        default=DESTINATIONS[0].key,
        choices=[candidate.key for candidate in DESTINATIONS],
        help="où l'archive sera déposée, ce qui fixe sa taille maximale",
    )
    failures.set_defaults(handler=command_failures)

    check = subparsers.add_parser("verifier", help="vérifie que l'installation est complète")
    check.add_argument("--langue", dest="language", default="fr", choices=("fr", "en"))
    check.add_argument(
        "--serveur",
        dest="server",
        default=None,
        metavar="URL",
        help="vérifie aussi que cette version est encore acceptée",
    )
    check.set_defaults(handler=command_check)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _setup_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        # Sans sous-commande, l'état du référentiel est la réponse la plus
        # utile : elle dit si l'installation est en état de marche.
        args = parser.parse_args(["referentiel"])
        handler = args.handler
    result: int = handler(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
