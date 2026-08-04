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

from .capture import ScreenCapture, banner_region, find_game_window
from .deferred import DeferredWatcher
from .reading import RapidOcrReader
from .reference import Catalog
from .reference.source import load
from .timing import Measure, Quality, Timeline
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


def _print_measure(measure: Measure, catalog: Catalog, language: str) -> None:
    quest = catalog.get(measure.quest_id, language)
    name = quest.name if quest else str(measure.quest_id)
    mark = "" if measure.quality is Quality.EXACT else "  (déduite)"
    print(f"  {_format_duration(measure.seconds):>12}   {name}{mark}")


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
                            _print_measure(measure, catalog, args.language)
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
    return 0


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
        "--echelle",
        dest="ui_scale",
        type=float,
        default=1.0,
        help="échelle de l'interface du jeu, si elle a été modifiée",
    )
    watch.set_defaults(handler=command_watch)
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
