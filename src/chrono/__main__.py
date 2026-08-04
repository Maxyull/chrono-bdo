"""Point d'entrée en ligne de commande.

Pour l'instant, une seule chose : construire le référentiel et dire ce qu'il
contient. C'est peu, mais ça vérifie de bout en bout que la source répond, que
le format n'a pas changé et que les chaînes se reconstituent, ce qui est
exactement ce qu'on veut pouvoir contrôler avant chaque session de mesure.
"""

from __future__ import annotations

import argparse
import sys

from .reference import Catalog
from .reference.source import load


def main() -> int:
    parser = argparse.ArgumentParser(prog="chrono", description="Chronomètre de quêtes BDO")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="retélécharge le référentiel même si le cache est récent",
    )
    args = parser.parse_args()

    languages = ("fr", "en")
    try:
        payloads = {lang: load(lang, refresh=args.refresh) for lang in languages}
    except Exception as error:  # message lisible plutôt qu'une trace
        print(f"référentiel indisponible : {error}", file=sys.stderr)
        return 1

    catalog = Catalog.from_payloads(payloads)
    chains = catalog.chains("fr")
    quests = sum(len(chain) for chain in chains.values())
    complete = sum(1 for chain in chains.values() if chain.is_contiguous)

    print(f"{len(catalog)} quêtes au catalogue, en {', '.join(catalog.languages)}")
    print(f"{quests} quêtes principales réparties en {len(chains)} chaînes")
    print(f"{complete} chaînes sans trou de numérotation, {len(chains) - complete} à compléter")

    # L'ambiguïté ne compte que sur le périmètre réellement mesuré. Le chiffre
    # sur l'ensemble du catalogue serait plus impressionnant et moins utile.
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


if __name__ == "__main__":
    raise SystemExit(main())
