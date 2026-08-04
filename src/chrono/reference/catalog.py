"""Le catalogue : les quêtes indexées, dans toutes les langues chargées.

C'est ici que le bilingue se joue. Les deux langues partagent les mêmes
identifiants, donc une quête lue à l'écran en français et la même quête lue en
anglais aboutissent au même `QuestId`. Le classement est commun aux deux
clients sans qu'aucune traduction n'ait à être écrite à la main.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .models import KIND_MAIN, Chain, Quest, QuestId
from .parsing import parse_payload


def fold(text: str) -> str:
    """Réduit un nom à une forme comparable : sans accents, sans casse.

    Provisoire, et volontairement minimal. La vraie normalisation vit dans le
    noyau partagé avec butin, qui traite en plus la ligature « œ » et le bruit
    propre à la reconnaissance de caractères. Ici, les noms viennent d'un
    fichier JSON, pas d'un écran : il n'y a pas de bruit à absorber, seulement
    des différences d'accent et de casse à ignorer.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(without_marks.casefold().split())


class Catalog:
    """Les quêtes d'une ou plusieurs langues, interrogeables par identifiant ou par nom."""

    def __init__(self, quests_by_language: Mapping[str, Iterable[Quest]]) -> None:
        self._by_id: dict[str, dict[QuestId, Quest]] = {
            language: {q.id: q for q in quests} for language, quests in quests_by_language.items()
        }
        # Un nom peut désigner plusieurs quêtes : le jeu réemploie des libellés
        # d'une région à l'autre. On garde donc toutes les correspondances, et
        # c'est `resolve` qui décide quoi en faire.
        self._by_name: dict[str, dict[str, list[QuestId]]] = {}
        for language, by_id in self._by_id.items():
            index: dict[str, list[QuestId]] = defaultdict(list)
            for quest in by_id.values():
                index[fold(quest.name)].append(quest.id)
            self._by_name[language] = dict(index)

    @classmethod
    def from_payloads(cls, payloads: Mapping[str, dict[str, Any]]) -> Catalog:
        """Construit le catalogue à partir des réponses brutes du référentiel."""
        return cls({language: parse_payload(payload) for language, payload in payloads.items()})

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(self._by_id)

    def __len__(self) -> int:
        first = next(iter(self._by_id.values()), {})
        return len(first)

    def get(self, quest_id: QuestId, language: str = "fr") -> Quest | None:
        return self._by_id.get(language, {}).get(quest_id)

    def resolve(self, name: str, language: str = "fr") -> QuestId | None:
        """Retrouve l'identifiant d'une quête d'après son nom exact.

        Renvoie `None` si le nom est inconnu **ou** s'il désigne plusieurs
        quêtes. C'est délibéré, et c'est le même principe que dans butin :
        rater une quête fausse un chiffre à la baisse, en inventer une fausse
        le classement de tout le monde. Les deux erreurs ne coûtent pas la
        même chose, donc on ne les traite pas symétriquement.

        La levée d'ambiguïté par le contexte, notamment par la chaîne en cours,
        appartient au chronomètre, qui sait ce que le joueur était en train de
        faire. Le catalogue, lui, ne devine pas.
        """
        matches = self._by_name.get(language, {}).get(fold(name), [])
        return matches[0] if len(matches) == 1 else None

    def ambiguous_names(self, language: str = "fr") -> dict[str, list[QuestId]]:
        """Les noms qui désignent plus d'une quête, pour diagnostic."""
        return {
            name: ids for name, ids in self._by_name.get(language, {}).items() if len(ids) > 1
        }

    def chains(self, language: str = "fr", kind: int | None = KIND_MAIN) -> dict[int, Chain]:
        """Regroupe les quêtes en chaînes, filtrées par type.

        Par défaut, seules les quêtes principales : ce sont les seules que le
        chronomètre mesure, et les seules dont un temps de référence veut dire
        quelque chose.
        """
        grouped: dict[int, list[Quest]] = defaultdict(list)
        for quest in self._by_id.get(language, {}).values():
            if kind is None or quest.kind == kind:
                grouped[quest.id.chain].append(quest)
        return {
            number: Chain(number, tuple(sorted(quests, key=lambda q: q.id.position)))
            for number, quests in sorted(grouped.items())
        }
