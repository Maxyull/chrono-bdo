"""Choisir une zone de lecture en la dessinant sur une capture du jeu.

Régler un rectangle par des nombres suppose de savoir où ils tombent. Personne
ne le sait : les zones sont calculées depuis des mesures relevées sur un écran
en 2559 x 1439, et ni une interface agrandie, ni une disposition déplacée par le
joueur ne s'y conforment. Le seul réglage honnête est celui qu'on voit.

La fenêtre montre donc **une photographie du jeu**, à l'échelle, et le joueur
trace dessus le rectangle qu'il veut lire. Ce qui est tracé est exactement ce
qui sera capturé.

## Pourquoi une image et pas un aperçu en direct

Un aperçu qui se rafraîchit demanderait une capture par image, et le jeu bouge :
on tracerait sur un décor qui a déjà changé. Une photographie prise au moment où
l'on ouvre la fenêtre est figée, donc on vise ce qu'on voit.

## L'image passe par du PNG encodé, pas par ImageTk

`tkinter.PhotoImage` sait relire du PNG depuis une chaîne encodée en base64,
depuis Tk 8.6. Passer par `PIL.ImageTk` obligerait à ce que Pillow ait été
compilé avec le support de Tk, ce qui n'est pas garanti et se découvre à
l'exécution, chez l'utilisateur, au pire moment.
"""

from __future__ import annotations

import base64
import io
import tkinter as tk
from collections.abc import Callable
from typing import Final

from ..capture import Rect
from .theme import COLORS

#: Largeur maximale de l'aperçu. Au-delà, la fenêtre déborde des écrans
#: ordinaires alors qu'on vise des rectangles de trois cents pixels.
MAX_PREVIEW: Final = 900


def scale_for(window: Rect, max_width: int = MAX_PREVIEW) -> float:
    """Facteur de réduction pour que la capture tienne à l'écran."""
    if window.width <= max_width:
        return 1.0
    return max_width / window.width


def to_game(rect: Rect, window: Rect, scale: float) -> Rect:
    """Convertit un rectangle tracé sur l'aperçu en coordonnées d'écran.

    Les deux conversions sont séparées et testées parce que c'est exactement le
    genre de calcul qui se trompe d'un facteur ou d'une origine sans lever la
    moindre erreur : on obtient une zone plausible, au mauvais endroit, et le
    logiciel ne mesure plus rien sans dire pourquoi.
    """
    return Rect(
        left=window.left + int(rect.left / scale),
        top=window.top + int(rect.top / scale),
        width=max(1, int(rect.width / scale)),
        height=max(1, int(rect.height / scale)),
    )


def normalise(x1: int, y1: int, x2: int, y2: int) -> Rect:
    """Un rectangle positif, quel que soit le sens du tracé.

    On trace aussi bien de bas à droite vers haut à gauche. Sans cela, la
    largeur serait négative, la zone rejetée à la relecture, et le joueur
    croirait avoir mal cliqué.
    """
    return Rect(
        left=min(x1, x2), top=min(y1, y2), width=abs(x2 - x1), height=abs(y2 - y1)
    )


def png_data(image: object) -> str:
    """Encode une image Pillow en PNG base64, pour `tk.PhotoImage`."""
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")  # type: ignore[attr-defined]
    return base64.b64encode(tampon.getvalue()).decode("ascii")


class ZonePicker:
    """Une fenêtre où l'on trace la zone à lire sur une photo du jeu."""

    def __init__(
        self,
        parent: tk.Tk,
        window: Rect,
        title: str,
        on_chosen: Callable[[Rect], None],
    ) -> None:
        self._window = window
        self._on_chosen = on_chosen
        self._scale = scale_for(window)
        self._start: tuple[int, int] | None = None
        self._rect_id: int | None = None

        from PIL import Image

        from ..capture import ScreenCapture

        with ScreenCapture(window) as capture:
            brut = capture.grab_color()
        image = Image.fromarray(brut)
        largeur = int(window.width * self._scale)
        hauteur = int(window.height * self._scale)
        image = image.resize((largeur, hauteur))

        self.top = tk.Toplevel(parent)
        self.top.title(f"{title} — tracez la zone à lire")
        self.top.configure(background=COLORS["fond"])
        self.top.transient(parent)

        tk.Label(
            self.top,
            text="Tracez un rectangle autour de ce que Rubin doit lire.",
            background=COLORS["fond"],
            foreground=COLORS["texte"],
            pady=8,
        ).pack(fill="x")

        # Gardée sur l'instance : Tk ne retient pas les images, et une image
        # ramassée par le collecteur laisse un cadre vide sans la moindre erreur.
        self._photo = tk.PhotoImage(data=png_data(image))
        self._canvas = tk.Canvas(
            self.top,
            width=largeur,
            height=hauteur,
            highlightthickness=0,
            background=COLORS["fond"],
        )
        self._canvas.pack()
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._canvas.bind("<Button-1>", self._press)
        self._canvas.bind("<B1-Motion>", self._drag)
        self._canvas.bind("<ButtonRelease-1>", self._release)

    def _press(self, event: tk.Event[tk.Canvas]) -> None:
        self._start = (event.x, event.y)
        if self._rect_id is not None:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline=COLORS["accent"], width=2
        )

    def _drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._start is None or self._rect_id is None:
            return
        self._canvas.coords(self._rect_id, self._start[0], self._start[1], event.x, event.y)

    def _release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._start is None:
            return
        tracé = normalise(self._start[0], self._start[1], event.x, event.y)
        self._start = None
        if tracé.width < 8 or tracé.height < 8:
            # Un clic sans glisser, ou un tracé minuscule. Une zone de huit
            # pixels ne contient aucun texte : la retenir rendrait le logiciel
            # muet, et le joueur croirait avoir choisi quelque chose.
            return
        self._on_chosen(to_game(tracé, self._window, self._scale))
        self.top.destroy()
