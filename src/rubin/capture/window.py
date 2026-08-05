"""Localisation de la fenêtre du jeu.

Le bandeau est repéré par rapport à la fenêtre du jeu, pas à l'écran : sur
plusieurs écrans, ou en mode fenêtré, les deux ne coïncident pas.

Windows uniquement, par l'interface système, sans dépendance supplémentaire.
Sur les autres systèmes, la recherche renvoie `None` plutôt que d'échouer, ce
qui permet aux tests et à l'intégration continue de tourner sur Linux.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Final

from .region import Rect

#: Fragments cherchés dans le titre de la fenêtre, en minuscules. Le client
#: français et le client anglais portent le même titre, mais il a changé au fil
#: des versions du jeu, d'où plusieurs candidats.
#:
#: ⚠️ Le titre **ne suffit pas** à reconnaître le jeu, et c'est le sens du
#: module. Voir `GAME_EXECUTABLES`.
TITLE_FRAGMENTS: Final = ("black desert",)

#: Noms d'exécutables du client, en minuscules.
#:
#: C'est le critère principal, et il a remplacé le titre après un incident
#: reproduit sur ce poste : Chrome affichait une vidéo intitulée « RETOUR SUR
#: BLACK DESERT ! ... - YouTube », donc son titre contenait le fragment cherché,
#: donc la recherche a rendu **la fenêtre du navigateur**. Le jeu tournait
#: pourtant en même temps, dans une autre fenêtre.
#:
#: La conséquence était la pire possible : `rubin verifier` répondait « fenêtre
#: du jeu trouvée, tout est en ordre » en pointant un navigateur, et la session
#: qui suivait ne mesurait rien sans jamais dire pourquoi. Un joueur de Black
#: Desert qui regarde une vidéo de Black Desert n'est pas un cas tordu, c'est le
#: cas courant.
GAME_EXECUTABLES: Final = (
    "blackdesert64.exe",
    "blackdesert32.exe",
    "blackdesert.exe",
)


# La condition est écrite au niveau du module, et sous cette forme exacte,
# parce que c'est celle que le vérificateur de types reconnaît : il n'analyse
# alors que la branche correspondant à la plateforme visée. Un test à
# l'intérieur de la fonction ne suffirait pas, `ctypes.WinDLL` n'existant pas
# hors Windows ; et une annotation d'exception serait signalée comme inutile
# quand la vérification tourne, elle, sur Windows.
@dataclass(frozen=True)
class Candidate:
    """Une fenêtre visible dont le titre évoque le jeu.

    `executable` est le nom du programme qui la possède, en minuscules, ou
    `None` quand il n'a pas pu être lu. Ce cas n'est pas théorique : le client
    tourne parfois avec des privilèges plus élevés que Rubin, à cause de son
    anti-triche, et l'interrogation du processus échoue alors. Une fenêtre dont
    on ne sait rien reste donc un candidat, mais un candidat de dernier recours.
    """

    rect: Rect
    title: str
    executable: str | None

    @property
    def is_game(self) -> bool:
        return self.executable in GAME_EXECUTABLES

    @property
    def is_other_program(self) -> bool:
        """Vrai quand on a **su lire** le programme et que ce n'est pas le jeu.

        C'est cette certitude qui écarte le navigateur, et elle vaut mieux
        qu'une liste de programmes interdits : demain ce sera un lecteur vidéo,
        un client Discord affichant un statut, ou une fenêtre de streaming.
        """
        return self.executable is not None and not self.is_game


if sys.platform == "win32":

    def _executable_of(handle: int) -> str | None:
        """Nom du programme propriétaire d'une fenêtre, en minuscules."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if not pid.value:
            return None
        # Le droit le plus faible qui permette de lire le chemin. Demander
        # davantage échouerait sur les processus protégés sans rien apporter.
        _QUERY_LIMITED_INFORMATION = 0x1000
        process = kernel32.OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not process:
            return None
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(
                process, 0, buffer, ctypes.byref(size)
            ):
                return None
            return PurePath(buffer.value).name.lower()
        finally:
            kernel32.CloseHandle(process)

    def _candidates(fragment: str) -> list[Candidate]:
        """Toutes les fenêtres visibles dont le titre contient `fragment`.

        Toutes, et non la première : c'est précisément le fait de s'arrêter à la
        première qui faisait rendre le navigateur. L'ordre d'énumération suit
        l'ordre d'affichage, donc la fenêtre au premier plan gagnait, quelle
        qu'elle soit.
        """
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        found: list[Candidate] = []

        def visit(handle: int, _param: int) -> bool:
            if not user32.IsWindowVisible(handle):
                return True
            length = user32.GetWindowTextLengthW(handle)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, buffer, length + 1)
            title = buffer.value
            if fragment not in title.lower():
                return True
            rect = wintypes.RECT()
            if not user32.GetClientRect(handle, ctypes.byref(rect)):
                return True
            origin = wintypes.POINT(0, 0)
            user32.ClientToScreen(handle, ctypes.byref(origin))
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if width > 0 and height > 0:
                found.append(
                    Candidate(
                        rect=Rect(origin.x, origin.y, width, height),
                        title=title,
                        executable=_executable_of(handle),
                    )
                )
            return True  # on continue : la première n'est pas forcément la bonne

        callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(visit)
        user32.EnumWindows(callback, 0)
        return found

else:

    def _executable_of(handle: int) -> str | None:
        return None

    def _candidates(fragment: str) -> list[Candidate]:
        return []


def choose_window(candidates: Sequence[Candidate]) -> Rect | None:
    """Départage les fenêtres candidates, et rend celle du jeu.

    Trois règles, dans cet ordre.

    **Une fenêtre dont on a lu le programme et qui n'est pas le jeu est
    écartée**, quel que soit son titre. C'est ce qui élimine le navigateur qui
    affiche une vidéo de Black Desert.

    **Une fenêtre du jeu l'emporte toujours** sur une fenêtre inconnue.

    **À égalité, la plus grande gagne.** Le client ouvre parfois une fenêtre
    secondaire, écran de lancement ou boîte de dialogue ; c'est la surface de
    jeu qui nous intéresse, et c'est la plus grande.

    Rend `None` quand il ne reste rien : mieux vaut dire que le jeu est
    introuvable que désigner une fenêtre au hasard. Une zone capturée au mauvais
    endroit ne produit pas d'erreur, elle produit une session qui ne mesure rien
    et n'explique pas pourquoi.
    """
    retenus = [c for c in candidates if not c.is_other_program]
    if not retenus:
        return None
    surs = [c for c in retenus if c.is_game]
    parmi = surs or retenus
    return max(parmi, key=lambda c: c.rect.width * c.rect.height).rect


def find_game_window(fragments: tuple[str, ...] = TITLE_FRAGMENTS) -> Rect | None:
    """Rectangle de la zone client du jeu, ou `None` s'il n'est pas trouvé.

    La **zone client** est renvoyée, pas la fenêtre entière : elle exclut la
    bordure et la barre de titre en mode fenêtré. C'est elle qui correspond à
    l'image du jeu, donc aux coordonnées du bandeau. En plein écran sans
    bordure, les deux coïncident.

    Le titre ne sert qu'à **présélectionner** : c'est le programme propriétaire
    de la fenêtre qui tranche. Se fier au titre seul faisait rendre la fenêtre
    d'un navigateur affichant une vidéo du jeu, et `rubin verifier` annonçait
    alors « tout est en ordre » en pointant Chrome.
    """
    # Pas de test de plateforme ici : `_candidates` rend déjà une liste vide
    # hors Windows. En ajouter un rendrait tout ce qui suit inatteignable aux
    # yeux du vérificateur de types quand il vise Linux, et il le signale.
    for fragment in fragments:
        rect = choose_window(_candidates(fragment.lower()))
        if rect is not None:
            return rect
    return None
