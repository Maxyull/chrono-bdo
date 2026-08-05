"""Le record personnel du joueur, lu dans les sessions déjà écrites sur ce poste.

Demandé par Maxime une fois le meilleur temps connu affiché en jeu (#72) : voir
non seulement ce que les autres ont mesuré, mais aussi **son propre** record sur
la quête en cours. Le serveur ne peut pas répondre à cette question : il ne
garde jamais rien lié à un joueur, par conception (voir `references.py`). La
seule source possible est donc locale, les fichiers que ce même logiciel a
écrits pendant les sessions précédentes.

## Pourquoi un balayage complet à chaque demande, et pas un index tenu à jour

La base de ce soir tient dans quelques dizaines de fichiers. Relire chaque
mesure de chaque session à chaque quête acceptée coûte quelques millisecondes,
et c'est strictement plus simple, et donc plus sûr, qu'un index construit
incrémentalement : pas de fichier de cache à invalider, pas d'état à tenir en
mémoire qui pourrait désynchroniser de ce qui est réellement sur le disque, pas
de migration le jour où le format change.

⚠️ **Ce n'est pas la bonne réponse pour toujours.** Après des mois de jeu, des
milliers de fichiers de session rendraient un balayage complet perceptible à
chaque quête acceptée. Le jour où ça se voit, la bonne réponse est un index
tenu à jour au fil de l'eau, pas un raccourcissement du balayage : deviner un
seuil de lenteur sans le mesurer serait exactement l'erreur que ce projet
refuse ailleurs, régler un seuil sans le vérifier en jeu.

## Ce qui est lu, et pourquoi

Deux formes de fichiers vivent dans `sessions/` :

- les lots `.json`, écrits en un bloc à la fermeture normale d'une session
  (`upload.save_session`) ;
- les journaux `.jsonl`, écrits mesure par mesure pendant qu'on joue
  (`upload.SessionJournal`), et qui restent seuls sur le disque si la session
  n'a jamais été fermée proprement (processus tué, redémarrage, plantage).

**Les deux comptent.** Ignorer les journaux ferait perdre le record d'une
session interrompue avant sa clôture, ce qui reviendrait à inventer une
réponse : le joueur verrait « jamais mesurée » pour une quête qu'il a pourtant
faite, plus vite qu'à son record affiché. Un chiffre manquant à cause d'un
fichier illisible reste honnête ; un chiffre qui ignore une mesure réelle sans
le dire ne l'est pas.

Un fichier illisible, tronqué ou d'un format inattendu est écarté seul, jamais
au prix des autres : la même tolérance que `upload.read_journal`, pour la même
raison, un processus tué en pleine écriture ne doit pas priver le joueur de
tout le reste de son historique.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from .protocol import MeasurePayload, SessionPayload
from .reference import QuestId
from .upload import JOURNAL_SUFFIX, read_journal

__all__ = ["personal_best"]


def _local_measures(home: Path) -> Iterator[MeasurePayload]:
    """Toutes les mesures plausibles connues sur ce poste, tous fichiers confondus."""
    dossier = home / "sessions"
    if not dossier.is_dir():
        return

    for chemin in sorted(dossier.glob("*.json")):
        try:
            brut = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue  # un fichier illisible ne prive pas des autres
        if not isinstance(brut, dict):
            continue
        try:
            payload = SessionPayload.from_dict(brut)
        except (TypeError, ValueError, KeyError):
            continue
        yield from _plausible(payload)

    for chemin in sorted(dossier.glob(f"*{JOURNAL_SUFFIX}")):
        contenu = read_journal(chemin)
        if contenu is not None:
            yield from _plausible(contenu.payload)


def _plausible(payload: SessionPayload) -> Iterator[MeasurePayload]:
    """Écarte ce qui n'aurait jamais dû être envoyé.

    En pratique tout ce qui vient de `save_session` ou de `SessionJournal.record`
    a déjà passé ce filtre à l'écriture (voir `session.py`). Le refaire ici est
    une redondance volontaire, pas un oubli comblé : un fichier de session peut
    être modifié à la main entre deux lancements, et une borne implausible qui
    se glisserait dans le record personnel serait un chiffre faux, exactement ce
    que le principe du projet interdit.
    """
    for mesure in payload.measures:
        if mesure.is_plausible:
            yield mesure


def personal_best(home: Path, quest_id: QuestId) -> float | None:
    """Le record personnel du joueur sur cette quête, ou `None` si jamais mesurée.

    `None` se distingue d'un zéro ou d'une colonne vide, qui se liraient comme
    « instantané » : voir `format_personal_best`, qui porte cette même règle
    jusqu'à l'affichage.

    Purement local : aucune requête réseau, aucune donnée envoyée ni reçue.
    Cette fonction ne lit que des fichiers déjà sur ce poste.
    """
    cible = str(quest_id)
    meilleur: float | None = None
    for mesure in _local_measures(home):
        if mesure.quest != cible:
            continue
        if meilleur is None or mesure.seconds < meilleur:
            meilleur = mesure.seconds
    return meilleur
