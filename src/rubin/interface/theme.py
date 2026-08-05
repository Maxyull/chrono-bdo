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


#: Nombre de mesures au-delà duquel le score plafonne à cent.
#:
#: Vingt, et c'est un choix assumé plutôt que calculé. Le score ne prétend pas
#: être une statistique : il dit **combien c'est mesuré**, sur une échelle
#: lisible, et rien de plus.
FULL_SCORE_AT: Final = 20


#: Plafond du score quand la place de la quête dans sa chaîne n'est pas sûre.
#:
#: Une quête dont on connaît parfaitement le temps mais pas la place ne peut pas
#: valoir cent : le score répond à « qu'est-ce qui m'attend et quand », et la
#: moitié de cette question est « où ça tombe ». Soixante dit « le temps est
#: bon, la place ne l'est pas », ce qui est exactement la situation.
UNPLACED_CAP: Final = 60


def confidence_score(samples: int | None, placed: bool = True) -> int:
    """Un score sur cent, tel que défini : 0 sans rien, 100 quand tout est su.

    Deux conditions, et **la plus faible commande**, jamais la moyenne :

    - assez de mesures pour qu'une médiane veuille dire quelque chose ;
    - assez de certitude sur la **place de la quête dans sa chaîne**.

    Une moyenne laisserait un temps très bien mesuré compenser une position
    inconnue, et donnerait un bon score à une quête dont on ne sait pas quand
    elle arrive. Les deux moitiés de la question doivent tenir ensemble.

    `placed` est faux quand le référentiel a un trou juste avant cette quête. Ce
    n'est pas un détail : 82 chaînes sur 349 en portent, et le jeu compte 19 235
    quêtes là où le référentiel en connaît 18 999. Une quête peut donc s'insérer
    à l'écran sans figurer dans la liste, et le temps affiché serait juste au
    mauvais endroit.

    ⚠️ **La part « temps » compte des mesures, pas des joueurs**, et c'est la
    limite connue. Vingt passages d'une même personne convergent vers le temps
    de cette personne, pas vers celui des joueurs : le score dirait cent là où
    une seule main a parlé. Le serveur ne distingue pas encore les
    contributeurs ; le jour où il le fera, c'est le nombre de joueurs distincts
    qui devra plafonner cette part.

    En attendant, deux garde-fous. Le nombre brut de mesures est **toujours
    affiché à côté**, donc le score n'ajoute rien qu'on ne puisse vérifier et
    ne remplace aucune information. Et la formule est écrite ici, en clair.
    """
    if samples is None or samples <= 0:
        return 0
    temps = min(100, round(100 * samples / FULL_SCORE_AT))
    return temps if placed else min(temps, UNPLACED_CAP)


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
