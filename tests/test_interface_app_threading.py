"""`RubinApp._add_measure` ne doit jamais bloquer le fil de Tk.

`_add_measure` est appelée depuis `_handle`, elle-même appelée depuis `_drain`,
planifiée par `self.root.after(...)` : elle tourne donc sur le fil principal de
Tk, celui qui redessine la fenêtre. `ReferenceClient.quest` fait un GET HTTP
synchrone quand la quête n'est pas déjà en cache, et un appel peut durer
jusqu'à cinq secondes quand le serveur ne répond pas, voir `_ask_server`. Un
appel direct depuis `_add_measure` gèlerait donc la fenêtre entière à la
première quête inconnue mesurée dans une session.

Ces tests n'ont besoin d'aucune fenêtre Tk : `_add_measure`, une fois corrigée,
ne touche plus à aucun composant, elle ne fait que lancer un fil et déposer un
message dans la file, exactement comme `_ask_server` et `_query_reference`. Un
petit porteur, avec seulement les deux attributs que la méthode emploie
(`_references` et `publish`), suffit donc à l'éprouver sans écran.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from rubin.interface.app import RubinApp
from rubin.reference import QuestId
from rubin.references import QuestReference
from rubin.timing import Measure, Quality

#: Le temps qu'on laisse à `_add_measure` pour rendre la main. Très généreux
#: comparé à ce qu'elle a vraiment à faire (lancer un fil), pour ne jamais
#: faire échouer le test sur une machine chargée.
BUDGET_RETOUR = 0.2


class _Porteur:
    """Le strict nécessaire que `_add_measure` lit et écrit sur `self`."""

    def __init__(self, references: Any) -> None:
        self._references = references
        self._messages: queue.Queue[tuple[str, Any]] = queue.Queue()

    def publish(self, genre: str, charge: Any) -> None:
        self._messages.put((genre, charge))


class _ReferentielBloquant:
    """Un `ReferenceClient` dont `quest` ne répond qu'une fois débloqué.

    Reproduit le GET synchrone réel : tant que personne n'appelle `débloquer`,
    l'appel ne rend jamais la main, exactement comme un serveur qui ne répond
    pas pendant les cinq secondes du vrai `_get`.
    """

    def __init__(self, reference: QuestReference | None) -> None:
        self._reference = reference
        self._prêt = threading.Event()
        self.appels = 0

    def débloquer(self) -> None:
        self._prêt.set()

    def quest(self, quest_id: QuestId) -> QuestReference | None:
        self.appels += 1
        self._prêt.wait()
        return self._reference

    def compare(self, seconds: float) -> str:  # pragma: pas de couverture
        return ""


def _mesure() -> Measure:
    return Measure(
        quest_id=QuestId(21136, 2),
        seconds=42.0,
        quality=Quality.EXACT,
        started_at=0.0,
        ended_at=42.0,
        confidence=1.0,
    )


class TestAjoutDeMesureNeBloquePasLeFilDeTk:
    def test_rend_la_main_avant_que_le_referentiel_ait_repondu(self) -> None:
        référence = QuestReference(median_seconds=40.0, samples=3, fastest_seconds=35.0)
        referentiel = _ReferentielBloquant(référence)
        porteur = _Porteur(referentiel)

        début = time.monotonic()
        RubinApp._add_measure(porteur, _mesure(), "fr")
        écoulé = time.monotonic() - début

        assert écoulé < BUDGET_RETOUR
        # Le référentiel n'a peut-être même pas encore été interrogé : le seul
        # fait garanti est que l'appelant, lui, n'a pas attendu.
        assert porteur._messages.empty()

        referentiel.débloquer()
        genre, charge = porteur._messages.get(timeout=BUDGET_RETOUR)

        assert genre == "mesure_reference"
        mesure, langue, reference_reçue = charge
        assert mesure.quest_id == QuestId(21136, 2)
        assert langue == "fr"
        assert reference_reçue is référence
        assert referentiel.appels == 1

    def test_regression_la_fenetre_gelait_a_la_premiere_quete_inconnue_mesuree(
        self,
    ) -> None:
        """Régression : `ReferenceClient.quest` bloquait le fil de Tk.

        Avant correctif, `_add_measure` appelait `self._references.quest(...)`
        directement, sur le fil qui vide `_drain`. La première fois qu'une
        quête était mesurée dans une session (donc absente du cache de
        `ReferenceClient`), l'appel partait en GET synchrone et pouvait durer
        jusqu'à cinq secondes si le serveur ne répondait pas, gelant toute la
        fenêtre pendant ce temps : plus aucun bouton, plus aucun rafraîchissement
        du chronomètre.

        Ce test simule ce cas précis, un délai représentatif du défaut réel, et
        vérifie que l'appelant n'attend plus du tout : c'est la fenêtre qui
        aurait continué à répondre pendant que le fil séparé attendait, elle.
        """
        DÉLAI_SERVEUR_LENT = 0.3  # représentatif du « jusqu'à cinq secondes »
        referentiel = _ReferentielBloquant(None)
        porteur = _Porteur(referentiel)

        def débloquer_après_un_moment() -> None:
            time.sleep(DÉLAI_SERVEUR_LENT)
            referentiel.débloquer()

        threading.Thread(target=débloquer_après_un_moment, daemon=True).start()

        début = time.monotonic()
        RubinApp._add_measure(porteur, _mesure(), "fr")
        écoulé_pour_l_appelant = time.monotonic() - début

        # C'est la fenêtre entière qui aurait été gelée pendant DÉLAI_SERVEUR_LENT :
        # l'appelant doit en être revenu bien avant, pas seulement un peu avant.
        assert écoulé_pour_l_appelant < DÉLAI_SERVEUR_LENT / 3

        genre, _charge = porteur._messages.get(timeout=DÉLAI_SERVEUR_LENT + BUDGET_RETOUR)
        assert genre == "mesure_reference"
