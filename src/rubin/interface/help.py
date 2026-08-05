"""Montrer à quoi doit ressembler une zone bien placée.

Tracer un rectangle suppose de savoir quoi viser. Décrire la cible avec des
mots ne suffit pas : « le bandeau en bas à droite » désigne une zone que le
joueur croit connaître, jusqu'à ce qu'il tombe à côté et que rien ne soit
mesuré pendant une session entière.

Chaque zone a donc son bouton **?**, qui affiche une **vraie capture** de ce que
Rubin doit y trouver, à côté des lignes qu'il en tire. Le joueur voit la cible
et la preuve qu'elle se lit.

## Les images sont de vraies captures, pas des dessins

`exemple-bandeau.png` est le bandeau « Nouvelle quête » d'où sont tirées les
lignes qui servent aux tests de tout le projet. `exemple-suivi.png` est un
panneau de suivi relevé en jeu, avec ses défauts : un nom tronqué par le jeu,
des espaces avalés par la reconnaissance, un caractère parasite né d'une icône.

Un dessin propre montrerait une cible qui n'existe pas, et donnerait au joueur
l'impression que sa capture à lui est ratée alors qu'elle est normale.

## Et donc : une entrée peut n'avoir aucune image

C'est le cas du panneau de choix. Aucune capture n'en existe, ni ici ni dans
les échantillons de calibration. La même règle qui interdit un dessin à la
place d'une vraie capture interdit d'en fabriquer un pour combler ce trou :
une image inventée passerait pour une mesure, et le joueur réglerait sa zone
sur une cible qui n'existe pas.

L'entrée est donc rendue **sans image**, avec le texte seul, qui dit pourquoi.
De la même façon, elle ne montre aucun exemple de ce que la reconnaissance en
tire : personne n'a jamais lu ce panneau, donc il n'y a rien d'honnête à
afficher là.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Final

from .picker import png_data
from .theme import COLORS, FAMILY, MONO_FAMILY

#: Où vivent les captures de référence, embarquées avec le paquet.
DATA: Final = Path(__file__).parent / "data"

#: Ce que chaque zone doit contenir, et ce qu'on en tire quand elle est bonne.
#:
#: Le fichier vaut `None` quand aucune vraie capture n'existe, et les lignes
#: sont vides quand personne n'a encore lu cette zone. Les deux se disent dans
#: le texte plutôt que de se combler par une invention.
EXAMPLES: Final[dict[str, tuple[str, str | None, str, tuple[str, ...]]]] = {
    "banner": (
        "Bandeau de quête",
        "exemple-bandeau.png",
        "Voilà ce que Rubin doit voir : le titre « Nouvelle quête » ou\n"
        "« Quête accomplie », puis le nom, qui passe à la ligne s'il est long.\n"
        "\n"
        "Cadrez la barre entière, avec son icône à gauche. Elle est ancrée en\n"
        "bas à droite et s'allonge vers la gauche selon le nom : prenez large\n"
        "plutôt que juste.",
        ("Nouvelle quete", "[Calpheon] Cris stridents des", "harpies"),
    ),
    "tracker": (
        "Panneau de suivi",
        "exemple-suivi.png",
        "Voilà ce que Rubin doit voir : la liste des quêtes suivies, sous la\n"
        "minimap, avec leurs objectifs.\n"
        "\n"
        "Les défauts visibles ici sont NORMAUX. Le jeu tronque les noms trop\n"
        "longs, la reconnaissance avale des espaces et ajoute parfois un\n"
        "caractère né d'une icône. Rubin s'en accommode : il ne retient que\n"
        "les lignes qui se résolvent en quête principale connue.",
        (
            "Objectifactuel:Alamemoire des soldats",
            "letenued'Elle",
            "O[Joum.][Recolte]Decouverte",
        ),
    ),
    "choice": (
        "Panneau de choix",
        # Pas d'image, et c'est délibéré : voir l'en-tête du module.
        None,
        "AUCUNE CAPTURE DE CE PANNEAU N'EXISTE ENCORE, donc rien n'est montré\n"
        "ici. Un dessin propre vous ferait viser une cible inventée, et la\n"
        "zone calculée par défaut est elle aussi une estimation : la moitié\n"
        "centrale de l'écran, à vérifier en jeu.\n"
        "\n"
        "Ce qu'il faut cadrer : le panneau qui s'ouvre au CENTRE quand une\n"
        "quête vous fait choisir entre deux suites. Le jeu y coupe le préfixe\n"
        "de région, « [Carrefour] Du côté de Valks » au lieu de\n"
        "« [Calpheon][Carrefour] Du côté de Valks » : Rubin sait le rattraper.\n"
        "\n"
        "Prenez large. Si la zone tombe à côté, rien n'est identifié, mais\n"
        "rien n'est identifié à tort non plus.",
        # Vide : personne n'a jamais lu ce panneau, donc il n'y a rien à
        # montrer. Y mettre des lignes plausibles serait inventer une mesure.
        (),
    ),
}


class HelpWindow:
    """Une fenêtre qui montre la cible, et la preuve qu'elle se lit."""

    def __init__(self, parent: tk.Tk, which: str) -> None:
        titre, fichier, explication, lignes = EXAMPLES[which]

        self.top = tk.Toplevel(parent)
        self.top.title(f"{titre} — ce que Rubin doit y trouver")
        self.top.configure(background=COLORS["fond"])
        self.top.transient(parent)

        tk.Label(
            self.top,
            text=explication,
            background=COLORS["fond"],
            foreground=COLORS["texte"],
            font=(FAMILY, 10),
            justify="left",
            anchor="w",
            padx=16,
            pady=12,
            wraplength=460,
        ).pack(fill="x")

        chemin = DATA / fichier if fichier is not None else None
        if chemin is not None and chemin.is_file():
            from PIL import Image

            with Image.open(chemin) as image:
                # Gardée sur l'instance : Tk ne retient pas ses images, et une
                # image ramassée par le collecteur laisse un cadre vide sans la
                # moindre erreur.
                self._photo = tk.PhotoImage(data=png_data(image.convert("RGB")))
            tk.Label(self.top, image=self._photo, background=COLORS["carte"]).pack(
                padx=16, pady=(0, 8)
            )

        if not lignes:
            # Rien à montrer, et le dire plutôt que d'afficher un cadre vide :
            # un cadre vide se lirait comme « la reconnaissance ne tire rien de
            # cette zone », ce qui est un tout autre problème que « personne ne
            # l'a encore lue ».
            return

        tk.Label(
            self.top,
            text="Ce que la reconnaissance en tire :",
            background=COLORS["fond"],
            foreground=COLORS["accent"],
            font=(FAMILY, 9, "bold"),
            anchor="w",
            padx=16,
        ).pack(fill="x")
        tk.Label(
            self.top,
            text="\n".join(lignes),
            background=COLORS["carte"],
            foreground=COLORS["texte"],
            font=(MONO_FAMILY, 9),
            justify="left",
            anchor="w",
            padx=10,
            pady=8,
        ).pack(fill="x", padx=16, pady=(4, 14))
