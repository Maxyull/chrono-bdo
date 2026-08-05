"""Ligne de commande.

Deux commandes. `referentiel` construit le catalogue et dit ce qu'il contient,
ce qui vérifie que la source répond et que son format n'a pas changé. `suivre`
est le chronomètre lui-même.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from platformdirs import user_data_dir

from .capture import ScreenCapture, banner_region, find_game_window
from .deferred import DeferredWatcher
from .protocol import PlayerIdentity, build_session
from .reading import RapidOcrReader
from .reference import Catalog
from .reference.source import catalog_date, load
from .references import ReferenceClient
from .timing import Measure, Quality, Timeline
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
    # Les références sont lues sur le serveur d'envoi, sans qu'envoyer soit
    # nécessaire pour les consulter : la lecture est publique.
    references = ReferenceClient(args.server or args.references)
    try:
        with ScreenCapture(region) as capture:
            watcher = BannerWatcher(capture, reader)
            # La capture et la lecture vivent dans deux fils séparés : sinon,
            # l'écran cesserait d'être surveillé pendant chaque reconnaissance,
            # soit jusqu'à une seconde, et un bandeau qui apparaît puis
            # disparaît dans cet intervalle serait perdu en silence.
            with DeferredWatcher(watcher, reader, interval=POLL_INTERVAL) as deferred:
                while True:
                    for reading, at in deferred.readings(timeout=1.0):
                        # L'instant retenu est celui de la capture, pas celui
                        # de la lecture : sans quoi chaque mesure serait
                        # allongée de la durée de sa propre reconnaissance.
                        measure = timeline.record(reading, at=at)
                        if measure is not None:
                            _print_measure(measure, catalog, args.language, references)
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
    _finish_session(timeline, args)
    return 0


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
    home = Path(user_data_dir("chrono-bdo", "maxyull"))
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

    print()
    print("tout est en ordre" if ok else "installation incomplète")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chrono", description="Chronomètre de quêtes BDO")
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
    watch.set_defaults(handler=command_watch)

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
