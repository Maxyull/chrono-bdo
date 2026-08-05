"""Le catalogue : les quêtes indexées, dans toutes les langues chargées.

C'est ici que le bilingue se joue. Les deux langues partagent les mêmes
identifiants, donc une quête lue à l'écran en français et la même quête lue en
anglais aboutissent au même `QuestId`. Le classement est commun aux deux
clients sans qu'aucune traduction n'ait à être écrite à la main.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from .models import KIND_MAIN, Chain, Quest, QuestId
from .parsing import parse_payload

#: Longueur minimale d'un nom tronqué pour qu'on accepte de le compléter. En
#: dessous, un fragment ressemble à trop de choses pour désigner quoi que ce
#: soit. Même seuil que `resolve_partial`, et pour la même raison.
MIN_TRUNCATED_KEY: Final = 8

#: Un chiffre romain, tel qu'il ressort de `fold` : minuscules, sans espace.
#: `fold` normalise en NFKD, donc les caractères romains dédiés d'Unicode
#: (« Ⅱ », U+2161) arrivent ici déjà décomposés en « ii ».
_ROMAN = re.compile(
    r"(?=[ivxlcdm]{1,7}$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$"
)


def is_roman_numeral(folded: str) -> bool:
    """Vrai si ce fragment déjà replié est un chiffre romain, et rien d'autre."""
    return bool(folded) and _ROMAN.fullmatch(folded) is not None


def fold(text: str) -> str:
    """Réduit un nom à une forme comparable : lettres et chiffres, rien d'autre.

    Les noms du catalogue viennent d'un fichier JSON, mais ceux qu'on leur
    compare viennent d'un écran, lus par reconnaissance de caractères. Celle-ci
    abîme les noms de trois façons, toutes observées en jeu :

    - **les accents sautent** : « quête » se lit « quete » ;
    - **la ponctuation se recolle** : « Jeron, la tacticienne » se lit
      « Jeron,la tacticienne » ;
    - **les espaces disparaissent** : « Ce qui s'est passé » se lit
      « Cequi s'estpasse ».

    Ce dernier défaut est le plus destructeur, et c'est lui qui commande la
    méthode. Aucun traitement des accents ne rattrape un mot recollé au
    suivant, et le découpage réel est imprévisible d'une lecture à l'autre. La
    seule forme stable est donc celle où espaces et ponctuation ont tous
    disparu des deux côtés : « cequisestpasse » d'un côté comme de l'autre.

    Deux quêtes qui ne différeraient que par leurs espaces ou leur ponctuation
    deviennent indiscernables. C'est assumé, parce que `resolve` refuse les
    formes ambiguës : le pire cas est une mesure perdue, jamais une mesure
    attribuée à tort.

    Reste provisoire. La normalisation complète vit dans le noyau partagé avec
    butin, qui traite en plus la ligature « œ » et les confusions de caractères
    propres à la reconnaissance.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    kept = (c for c in without_marks if not unicodedata.category(c).startswith(("P", "Z")))
    return "".join(kept).casefold().replace(" ", "")


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

    def resolve_in_chain(
        self,
        name: str,
        chain: int | None,
        language: str = "fr",
        after_position: int | None = None,
    ) -> QuestId | None:
        """Retrouve une quête en sachant dans quelle chaîne le joueur se trouve.

        C'est la levée d'ambiguïté annoncée depuis le début. 705 quêtes
        principales sur 3 924, soit 18 %, partagent leur nom avec une autre :
        « [Serendia] Boss des Fogans » en désigne trois. Le catalogue seul
        refuse de trancher, et ces quêtes ne sont jamais mesurées.

        La chaîne en cours suffit presque toujours à décider. Un joueur qui
        vient de finir 21133/4 et voit apparaître un nom partagé fait
        évidemment celui de la chaîne 21133, pas celui d'une chaîne qu'il n'a
        jamais commencée.

        Reste le cas des homonymes d'une **même** chaîne, que la chaîne seule ne
        peut pas départager : 305 quêtes principales. `after_position` les
        traite, en retenant celle qui suit immédiatement la dernière quête
        connue.

        Ce dernier recours est volontairement étroit. Il exige la position
        exactement suivante, jamais une position plus loin : deviner un saut
        reviendrait à attribuer une mesure à une quête que le joueur n'a
        peut-être pas faite, ce qui est l'erreur qu'on refuse partout ailleurs.

        Si rien ne départage, on refuse comme avant : mieux vaut une mesure
        perdue qu'une mesure attribuée à la mauvaise quête.
        """
        exact = self.resolve(name, language)
        if exact is not None or chain is None:
            return exact
        candidates = self._by_name.get(language, {}).get(fold(name), [])
        in_chain = [quest_id for quest_id in candidates if quest_id.chain == chain]
        if len(in_chain) == 1:
            return in_chain[0]
        if after_position is None:
            return None
        expected = [q for q in in_chain if q.position == after_position + 1]
        return expected[0] if len(expected) == 1 else None

    def resolve_partial(self, name: str, language: str = "fr") -> QuestId | None:
        """Retrouve une quête dont le nom affiché a perdu son début.

        Le jeu n'affiche pas toujours le nom complet. Le panneau de choix d'un
        carrefour montre « [Carrefour] Du côté de Valks » là où le catalogue
        porte « [Calpheon][Carrefour] Du côté de Valks » : le préfixe de région
        a sauté.

        Le nom lu est donc cherché comme **fin** d'un nom connu. 76 quêtes
        principales portent un double préfixe et sont exposées au problème ;
        72 se retrouvent ainsi sans la moindre ambiguïté.

        Comme partout, plusieurs candidats valent `None` : une correspondance
        partielle est plus facile à obtenir qu'une exacte, donc plus facile à
        obtenir par erreur, et il n'est pas question d'attribuer une mesure à
        une quête plutôt qu'à une autre sur cette base.
        """
        exact = self.resolve(name, language)
        if exact is not None:
            return exact
        key = fold(name)
        if len(key) < 8:  # trop court pour distinguer quoi que ce soit
            return None
        found = {
            quest_id
            for indexed, ids in self._by_name.get(language, {}).items()
            if indexed.endswith(key)
            for quest_id in ids
        }
        return next(iter(found)) if len(found) == 1 else None

    def resolve_truncated(
        self,
        name: str,
        language: str = "fr",
        chain: int | None = None,
        after_position: int | None = None,
    ) -> QuestId | None:
        """Retrouve une quête dont le nom affiché a perdu son numéro de fin.

        Le cas symétrique de `resolve_partial`, et il demande le traitement
        inverse. Là-bas c'est le **début** du nom qui saute, ici c'est la
        **fin**, et chercher par la fin ne rattrape donc rien de ce cas.

        Observé en jouant, cinq échecs d'affilée sur la même quête. Le nom
        « [Mediah] Les marchands d'Altinova II » déborde de la largeur du
        bandeau, et son chiffre romain part seul sur la deuxième ligne. Lu
        « Ⅱ » à 0,515, ce fragment de deux caractères tombe sous le seuil des
        lignes et se trouve écarté avant d'arriver ici. Le nom reconstruit
        devient « Les marchands d'Altinova », qui n'est le nom complet
        d'aucune quête.

        81 quêtes principales finissent par un chiffre romain, et 76 d'entre
        elles portent un nom que le seul début ne distingue plus : « Les
        marchands d'Altinova » est le début exact du I, du II et du III.

        D'où la règle, qui est celle de tout le projet : **on ne complète que
        s'il ne reste qu'un candidat.** Une quête non identifiée coûte une
        mesure ; une quête mal identifiée entre dans une médiane et n'en
        ressort jamais. Le contexte peut lever l'ambiguïté, exactement comme
        dans `resolve_in_chain` et avec la même étroitesse : d'abord la chaîne
        en cours, puis, en dernier recours, la position immédiatement
        suivante. Jamais une position plus loin, jamais un tirage au sort.

        Le reste manquant doit par ailleurs se réduire à un chiffre romain.
        Un nom dont il manquerait plusieurs mots est un autre problème, qui
        n'a pas les mêmes garanties, et qu'on ne traite pas ici.
        """
        exact = self.resolve(name, language)
        if exact is not None:
            return exact
        key = fold(name)
        if len(key) < MIN_TRUNCATED_KEY:
            return None
        indexed_names = self._by_name.get(language, {})
        if key in indexed_names:
            # Une quête porte exactement ce nom. Si `resolve` n'a rien rendu,
            # c'est qu'elles sont plusieurs, et compléter par un numéro
            # ajouterait une hypothèse à une ambiguïté déjà non tranchée.
            return None
        candidates = [
            quest_id
            for name_key, ids in indexed_names.items()
            if name_key.startswith(key) and is_roman_numeral(name_key[len(key) :])
            for quest_id in ids
        ]
        if len(candidates) == 1:
            return candidates[0]
        if chain is None:
            return None
        in_chain = [quest_id for quest_id in candidates if quest_id.chain == chain]
        if len(in_chain) == 1:
            return in_chain[0]
        if after_position is None:
            return None
        expected = [q for q in in_chain if q.position == after_position + 1]
        return expected[0] if len(expected) == 1 else None

    def resolve_lines(
        self,
        lines: Sequence[str],
        language: str = "fr",
        chain: int | None = None,
        after_position: int | None = None,
    ) -> QuestId | None:
        """Retrouve une quête à partir de lignes dont on ignore où le nom s'arrête.

        Le bandeau n'affiche pas toujours que le nom. Sur un bandeau d'objectif,
        une ligne de description le suit, du genre « Lire les dialogues en
        fonction de l'audio », et rien dans sa mise en forme ne la distingue
        d'une suite de nom : les noms longs passent eux aussi à la ligne.

        On essaie donc les recollages, **du plus long au plus court**, et le
        premier qui tombe sur une quête l'emporte. Dans cet ordre, un nom
        complet est toujours préféré à l'un de ses débuts, ce qui évite qu'un
        préfixe se trouvant coïncider avec une autre quête ne l'emporte sur la
        bonne réponse.

        Les trois recours sont essayés dans cet ordre, du plus sûr au moins
        sûr, et l'ordre est ce qui les rend acceptables : un nom complet
        l'emporte toujours sur un nom auquel il faut ajouter ou retirer
        quelque chose.
        """
        for count in range(len(lines), 0, -1):
            found = self.resolve_in_chain(
                " ".join(lines[:count]), chain, language, after_position
            )
            if found is not None:
                return found
        # Rien d'exact : le nom affiché a peut-être perdu son préfixe de région,
        # ce que fait le panneau de choix d'un carrefour.
        for count in range(len(lines), 0, -1):
            partial = self.resolve_partial(" ".join(lines[:count]), language)
            if partial is not None:
                return partial
        # Toujours rien : c'est peut-être la fin qui manque, un chiffre romain
        # passé à la ligne et lu trop bas pour être retenu.
        for count in range(len(lines), 0, -1):
            truncated = self.resolve_truncated(
                " ".join(lines[:count]), language, chain, after_position
            )
            if truncated is not None:
                return truncated
        return None

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
