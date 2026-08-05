"""L'habillage de la fenêtre : couleurs, polices, styles.

Séparé de `app.py` parce que ce sont deux choses différentes : ce fichier décide
de quoi ça a l'air, l'autre de ce que ça fait. Et parce que le premier jet a dû
être refait entièrement une fois la fenêtre vue à l'écran.

## Ce que le premier jet a raté

La fenêtre était livrée à quatre-vingt-douze pour cent d'opacité, et habillée du
thème par défaut de Tk : du gris sur du gris. Posée sur Black Desert, cela
donnait du texte gris translucide sur un décor clair, mouvant et texturé.
Illisible, au sens propre : on ne distinguait pas les lettres.

Trois corrections en découlent, et aucune n'est décorative.

**Opaque par défaut.** La transparence est un confort, la lisibilité est la
fonction. On ne sacrifie pas la seconde à la première.

**Sombre à fort contraste.** Le jeu est sombre, l'œil y est habitué, et une
fenêtre claire posée à côté éblouit la nuit. Le rapport de contraste entre le
texte et le fond dépasse douze pour un, très au-delà des sept exigés pour du
petit texte.

**Des tailles qui hiérarchisent.** Tout était à la même taille, donc rien ne
ressortait. Le nom de la quête en cours est ce qu'on lit d'un coup d'œil sans
quitter le jeu ; le reste peut être plus petit.

## Le rouge

Rubin est un rubis, et c'est le nom d'un héraut de Calpheon. L'accent est donc
un rouge de pierre, pas un rouge d'alerte : les avertissements, eux, ont leur
propre couleur, plus orangée, pour qu'on ne confonde pas la marque du logiciel
avec un problème.
"""

from __future__ import annotations

from tkinter import font as tkfont
from tkinter import ttk
from typing import Final

#: Les couleurs, une seule fois. Changer l'habillage se fait ici.
COLORS: Final = {
    "fond": "#16161a",
    "carte": "#1f1f26",
    "bordure": "#33333d",
    "texte": "#ececf1",
    "faible": "#9b9bab",
    "accent": "#d4453c",
    "sur": "#4cb782",
    "moyen": "#e0a63a",
    "absent": "#7a7a88",
    "alerte": "#ff8a5b",
}

#: Police du texte, et police à chasse fixe pour ce que la reconnaissance rend.
#:
#: Les lignes lues sont affichées en chasse fixe **exprès** : on y cherche des
#: caractères précis, des espaces avalés, un « l » là où il devrait y avoir un
#: crochet. Une police proportionnelle masque exactement ce qu'on veut voir.
FAMILY: Final = "Segoe UI"
MONO_FAMILY: Final = "Consolas"


def apply(root: ttk.Widget | object) -> ttk.Style:
    """Habille toute la fenêtre, et rend le style pour les cas particuliers."""
    style = ttk.Style()
    # « clam » est le seul thème livré partout qui accepte qu'on lui impose ses
    # couleurs. Les thèmes natifs de Windows ignorent la moitié des réglages,
    # et on se retrouve avec des morceaux gris clair au milieu du sombre.
    style.theme_use("clam")

    base = tkfont.nametofont("TkDefaultFont")
    base.configure(family=FAMILY, size=10)

    fond, carte, texte, faible = (
        COLORS["fond"],
        COLORS["carte"],
        COLORS["texte"],
        COLORS["faible"],
    )

    # `clam` dessine ses reliefs avec trois couleurs distinctes du fond, et les
    # laisser par défaut cerne chaque cadre d'un liseré blanc, très visible sur
    # un thème sombre. Les aligner sur le fond fait disparaître les bordures que
    # personne n'a demandées, sans toucher à celles qu'on dessine exprès.
    style.configure(
        ".",
        background=fond,
        foreground=texte,
        fieldbackground=carte,
        bordercolor=fond,
        lightcolor=fond,
        darkcolor=fond,
        focuscolor=COLORS["accent"],
    )
    style.configure("TFrame", background=fond)
    style.configure("Carte.TFrame", background=carte)
    style.configure("TLabel", background=fond, foreground=texte, font=(FAMILY, 10))
    style.configure("Faible.TLabel", foreground=faible, font=(FAMILY, 9))
    style.configure("Titre.TLabel", foreground=texte, font=(FAMILY, 15, "bold"))
    style.configure("Section.TLabel", foreground=COLORS["accent"], font=(FAMILY, 9, "bold"))
    style.configure("Valeur.TLabel", foreground=COLORS["accent"], font=(FAMILY, 10, "bold"))
    style.configure("Alerte.TLabel", foreground=COLORS["alerte"], font=(FAMILY, 9))

    style.configure(
        "TNotebook",
        background=fond,
        borderwidth=0,
        bordercolor=fond,
        lightcolor=fond,
        darkcolor=fond,
        tabmargins=(0, 4, 0, 0),
    )
    # Le contenu de l'onglet retenu se distingue par sa couleur, pas par un
    # cadre : un liseré autour de chaque panneau hache la fenêtre en boîtes et
    # rend la hiérarchie moins lisible, pas plus.
    style.configure("TNotebook.Client", background=carte, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=fond,
        foreground=faible,
        padding=(16, 7),
        font=(FAMILY, 10),
        borderwidth=0,
        bordercolor=fond,
        lightcolor=fond,
        darkcolor=fond,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", carte)],
        foreground=[("selected", texte)],
        expand=[("selected", (0, 0, 0, 0))],
    )

    style.configure(
        "TButton",
        background=carte,
        foreground=texte,
        borderwidth=0,
        padding=(12, 7),
        font=(FAMILY, 10),
    )
    style.map("TButton", background=[("active", COLORS["bordure"])])
    style.configure("Accent.TButton", background=COLORS["accent"], foreground="#ffffff")
    style.map("Accent.TButton", background=[("active", "#e8564d")])

    style.configure(
        "TScale", background=fond, troughcolor=COLORS["bordure"], borderwidth=0
    )
    style.configure(
        "TRadiobutton", background=fond, foreground=texte, font=(FAMILY, 10)
    )
    style.map("TRadiobutton", background=[("active", fond)])
    style.configure("TSeparator", background=COLORS["bordure"])
    return style


def confidence_colour(samples: int | None) -> str:
    """La couleur qui dit ce que vaut un temps, d'un coup d'œil.

    Trois niveaux, et le premier compte autant que les autres : **gris quand
    personne n'a mesuré**. Un temps absent n'est pas un mauvais temps, c'est une
    invitation à être le premier, et le peindre en rouge le ferait passer pour
    une panne.

    Le seuil de cinq n'est pas statistique, il est honnête : la base contient
    onze mesures d'un seul joueur, donc presque tout sera orange, et c'est
    exactement ce qu'il faut montrer.
    """
    if samples is None or samples <= 0:
        return COLORS["absent"]
    return COLORS["sur"] if samples >= 5 else COLORS["moyen"]
