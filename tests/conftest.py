"""Données de test partagées.

Les échantillons sont de **vraies** lignes du référentiel, réduites à vingt-quatre
quêtes par langue. Des lignes inventées testeraient l'idée qu'on se fait du
format plutôt que le format lui-même, et c'est précisément là que se logent les
surprises : un identifiant qui est un objet et pas une chaîne, une apostrophe
encodée en entité HTML, une colonne qui change de type d'une ligne à l'autre.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rubin.reference import Catalog

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def payloads() -> dict[str, dict[str, Any]]:
    return {
        language: json.loads((DATA / f"quests_{language}.json").read_text(encoding="utf-8"))
        for language in ("fr", "en")
    }


@pytest.fixture(scope="session")
def catalog(payloads: dict[str, dict[str, Any]]) -> Catalog:
    return Catalog.from_payloads(payloads)
