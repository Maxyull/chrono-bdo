"""Les notes personnelles du joueur sur une quête.

Demandé par Maxime le 05/08/2026 au soir : de quoi noter, à côté d'une quête,
le monstre à tuer, l'instance à faire, le choix pris à un carrefour, ou un mot
ou un nombre à relever dans le chat du jeu. Ce genre de détail se perd d'une
fois sur l'autre, en particulier sur un personnage refait plus tard.

Ce n'est **pas une mesure**, et le principe qui gouverne le reste du projet
(« rater une mesure donne un chiffre incomplet, en inventer une donne un
chiffre faux ») ne s'y applique donc pas de la même façon : une note est écrite
par le joueur, pour lui-même, et son exactitude ne regarde que lui. Rien
n'empêche une note fausse ou périmée, comme rien n'empêche un mot mal noté
dans un vrai bloc-notes.

**Purement local, comme le record personnel (`history.py`).** Une note peut
nommer un monstre, un lieu ou un choix : ce n'est pas une donnée que ce projet
a vocation à collecter, encore moins à partager entre joueurs sans qu'ils l'aient
demandé. Aucune requête réseau ici, jamais.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from .reference import QuestId

__all__ = ["load_notes", "save_note"]

FILE_NAME: Final = "notes.json"


def load_notes(home: Path) -> dict[QuestId, str]:
    """Relit les notes existantes, ou un dictionnaire vide.

    Traité comme hostile, à l'image de `settings.load` : un fichier absent est
    le cas normal du premier lancement, un fichier illisible ou modifié à la
    main ne doit pas être plus grave. Une clé qui ne se lit pas comme
    `chaîne/position`, ou une valeur qui n'est pas du texte, est écartée seule,
    jamais au prix des autres notes.
    """
    chemin = home / FILE_NAME
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(brut, dict):
        return {}
    notes: dict[QuestId, str] = {}
    for clé, valeur in brut.items():
        if not isinstance(clé, str) or not isinstance(valeur, str) or not valeur.strip():
            continue
        try:
            identifiant = QuestId.parse(clé)
        except ValueError:
            continue
        notes[identifiant] = valeur
    return notes


def save_note(home: Path, quest_id: QuestId, text: str) -> dict[QuestId, str]:
    """Enregistre la note d'une quête, ou l'efface si `text` est vide.

    Relit puis réécrit le fichier entier plutôt que de tenir une copie en
    mémoire à jour : le nombre de notes qu'un joueur écrit reste minuscule à
    côté du nombre de mesures, le même raisonnement qui justifie le balayage
    complet de `history.personal_best`.

    Rend la table complète après écriture, pour que l'appelant n'ait pas à la
    relire.
    """
    notes = load_notes(home)
    texte = text.strip()
    if texte:
        notes[quest_id] = texte
    else:
        notes.pop(quest_id, None)
    home.mkdir(parents=True, exist_ok=True)
    chemin = home / FILE_NAME
    chemin.write_text(
        json.dumps(
            {str(qid): t for qid, t in sorted(notes.items())},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return notes
