"""Une infobulle, que Tk ne fournit pas.

Elle n'existe que pour une chose : dire **pourquoi** une commande est refusée.
Un bouton grisé sans explication est la même faute que le reste des silences de
ce projet, il ne distingue pas ses causes. « Pas maintenant » et « cassé » se
ressemblent beaucoup vus d'un clic sans effet.

Le texte vit ailleurs, dans `presentation.py`, qui est vérifiable sans écran.
Ce module ne s'occupe que de le montrer.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .theme import COLORS

#: Délai avant l'apparition, en millisecondes.
#:
#: Assez court pour répondre à qui survole exprès un bouton refusé, assez long
#: pour ne pas clignoter quand la souris ne fait que traverser la barre de
#: boutons pour en atteindre un autre.
DELAY_MS = 400


class Tooltip:
    """Attache une infobulle à un composant.

    Le texte est modifiable après coup, par `update`, parce qu'un même bouton
    est tantôt verrouillé tantôt libre, et qu'un bouton libre ne doit pas
    expliquer un verrou levé. Un texte vide n'affiche rien du tout : c'est ainsi
    qu'on éteint l'infobulle sans détruire l'attache.
    """

    def __init__(
        self,
        widget: tk.Widget,
        text: str = "",
        when: Callable[[int, int], bool] | None = None,
    ) -> None:
        """`when` limite l'infobulle à une partie du composant.

        Nécessaire pour un carnet d'onglets, qui est un seul composant portant
        quatre onglets : sans cela, l'explication du verrou de l'onglet Zones
        apparaîtrait en survolant n'importe lequel des trois autres, ce qui
        laisserait croire qu'ils sont verrouillés aussi.
        """
        self._widget = widget
        self._text = text
        self._when = when
        self._fenetre: tk.Toplevel | None = None
        self._prevu: str | None = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Motion>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        # Un clic fait souvent disparaître le composant sous la souris, et
        # l'infobulle resterait seule à l'écran, orpheline.
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def update(self, text: str) -> None:
        self._text = text
        if not text:
            self._hide()

    def _on_enter(self, event: object = None) -> None:
        if not self._text:
            return
        if self._when is not None:
            x = getattr(event, "x", None)
            y = getattr(event, "y", None)
            if x is None or y is None or not self._when(int(x), int(y)):
                self._on_leave()
                return
        if self._fenetre is not None or self._prevu is not None:
            return  # deja montree, ou deja prevue : ne pas relancer a chaque pixel
        self._prevu = self._widget.after(DELAY_MS, self._show)

    def _on_leave(self, _event: object = None) -> None:
        self._cancel()
        self._hide()

    def _cancel(self) -> None:
        if self._prevu is not None:
            self._widget.after_cancel(self._prevu)
            self._prevu = None

    def _show(self) -> None:
        if self._fenetre is not None or not self._text:
            return
        # Sous le composant et non dessus : une infobulle qui recouvre le bouton
        # qu'elle explique empêche de le viser une fois lue.
        x = self._widget.winfo_rootx()
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._fenetre = tk.Toplevel(self._widget)
        self._fenetre.wm_overrideredirect(True)
        self._fenetre.wm_geometry(f"+{x}+{y}")
        # Au-dessus de la fenêtre principale, qui est elle-même toujours au
        # premier plan : sans cela l'infobulle naîtrait derrière elle.
        self._fenetre.attributes("-topmost", True)
        ttk.Label(
            self._fenetre,
            text=self._text,
            style="Faible.TLabel",
            background=COLORS["carte"],
            wraplength=320,
            justify="left",
            padding=(8, 6),
        ).pack()

    def _hide(self) -> None:
        if self._fenetre is not None:
            self._fenetre.destroy()
            self._fenetre = None


__all__ = ["DELAY_MS", "Tooltip"]
