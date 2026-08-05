"""La fenêtre de Rubin.

Tk, de la bibliothèque standard, et ce choix n'est pas de la paresse : le
paquet Windows pèse déjà 59 Mo, et Qt en ajouterait cent cinquante pour trois
curseurs et une liste. Tk sait faire le « toujours au-dessus » et la
transparence sous Windows, et n'ajoute aucun octet à l'exécutable.

Tout ce qui se calcule vit dans `presentation.py` et se vérifie sans écran. Ce
fichier ne fait que poser des composants et les rafraîchir.

## Le fil de mesure ne touche jamais à Tk

Tk n'est pas sûr entre fils d'exécution : appeler un composant depuis un autre
fil que celui de la boucle d'événements produit des blocages et des plantages
qui n'arrivent qu'une fois sur cent, donc jamais pendant qu'on regarde. Le fil
de mesure ne fait donc que déposer dans une file, que la boucle vide à
intervalle régulier depuis le bon fil.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tkinter import ttk
from typing import Any, Final

from ..capture import Rect, ScreenCapture, banner_region, find_game_window, tracker_region
from ..placement import choose, conflicts
from ..reference import Catalog
from ..settings import LANGUAGES, LIMITS, load, save
from .presentation import ZoneState, describe_conflict, describe_reading, describe_zone

#: Taille de la fenêtre. Assez large pour un nom de quête complet, assez étroite
#: pour tenir à côté du panneau de suivi sans mordre dessus.
WINDOW_SIZE: Final = (460, 560)

#: Période de rafraîchissement de l'affichage, en millisecondes. Huit fois par
#: seconde suffisent : c'est déjà la cadence de capture, et l'œil n'en demande
#: pas plus sur du texte.
REFRESH_MS: Final = 125


class RubinApp:
    """La fenêtre principale, ses trois onglets et ses réglages."""

    def __init__(self, home: Path, catalog: Catalog | None = None) -> None:
        self._home = home
        self._settings = load(home)
        self._catalog = catalog
        self._messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stop = threading.Event()

        self.root = tk.Tk()
        self.root.title("Rubin, chronomètre de quêtes")
        self.root.minsize(*WINDOW_SIZE)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_tabs()
        self._apply_window_style()
        self._place_beside_the_game()
        self.root.after(REFRESH_MS, self._drain)

    # ------------------------------------------------------------------ mise en place

    def _build_tabs(self) -> None:
        carnet = ttk.Notebook(self.root)
        carnet.pack(fill="both", expand=True, padx=8, pady=8)

        self._session = ttk.Frame(carnet)
        self._zones = ttk.Frame(carnet)
        self._reglages = ttk.Frame(carnet)
        carnet.add(self._session, text="Session")
        carnet.add(self._zones, text="Zones")
        carnet.add(self._reglages, text="Réglages")

        self._build_session()
        self._build_zones()
        self._build_settings()

    def _build_session(self) -> None:
        self._etat = ttk.Label(self._session, text="En attente du jeu…", anchor="w")
        self._etat.pack(fill="x", pady=(4, 8))

        ttk.Label(self._session, text="À suivre", anchor="w").pack(fill="x")
        self._liste = tk.Text(self._session, height=14, wrap="none", state="disabled")
        self._liste.pack(fill="both", expand=True, pady=4)

        self._compteurs = ttk.Label(self._session, text="", anchor="w")
        self._compteurs.pack(fill="x", pady=(8, 0))

    def _build_zones(self) -> None:
        explication = (
            "Rubin lit ces deux rectangles. S'ils tombent à côté, il ne mesure rien\n"
            "et ne peut pas dire pourquoi. Le bouton montre ce qu'il y lit maintenant."
        )
        ttk.Label(self._zones, text=explication, anchor="w", justify="left").pack(
            fill="x", pady=(4, 8)
        )

        self._zone_labels: dict[str, ttk.Label] = {}
        self._zone_readings: dict[str, tk.Text] = {}
        for clé, nom in (("banner", "Bandeau de quête"), ("tracker", "Panneau de suivi")):
            cadre = ttk.LabelFrame(self._zones, text=nom)
            cadre.pack(fill="both", expand=True, pady=4)
            self._zone_labels[clé] = ttk.Label(cadre, text="", anchor="w")
            self._zone_labels[clé].pack(fill="x", padx=6, pady=2)
            lecture = tk.Text(cadre, height=5, wrap="word", state="disabled")
            lecture.pack(fill="both", expand=True, padx=6, pady=(0, 6))
            self._zone_readings[clé] = lecture

        boutons = ttk.Frame(self._zones)
        boutons.pack(fill="x", pady=4)
        ttk.Button(boutons, text="Lire maintenant", command=self.read_zones_now).pack(side="left")
        ttk.Button(
            boutons, text="Revenir aux zones calculées", command=self.reset_zones
        ).pack(side="left", padx=6)

        self._avertissement = ttk.Label(self._zones, text="", anchor="w", justify="left")
        self._avertissement.pack(fill="x", pady=(6, 0))
        self.refresh_zones()

    def _build_settings(self) -> None:
        self._vars: dict[str, tk.DoubleVar] = {}
        libellés = {
            "ui_scale": "Échelle de l'interface du jeu",
            "presence_threshold": "Seuil de détection du bandeau",
            "poll_interval": "Cadence de capture (secondes)",
            "upcoming_count": "Quêtes affichées",
            "opacity": "Opacité de cette fenêtre",
        }
        for nom, libellé in libellés.items():
            bas, haut, _ = LIMITS[nom]
            cadre = ttk.Frame(self._reglages)
            cadre.pack(fill="x", pady=3)
            valeur = tk.DoubleVar(value=float(getattr(self._settings, nom)))
            self._vars[nom] = valeur
            étiquette = ttk.Label(cadre, text=f"{libellé} : {valeur.get():g}", anchor="w")
            étiquette.pack(fill="x")
            ttk.Scale(
                cadre,
                from_=bas,
                to=haut,
                variable=valeur,
                command=self._slider_moved(nom, libellé, étiquette),
            ).pack(fill="x")

        langue = ttk.LabelFrame(self._reglages, text="Langue du client de jeu")
        langue.pack(fill="x", pady=8)
        ttk.Label(
            langue,
            text=(
                "Celle du jeu, pas la vôtre : on peut être francophone\n"
                "et jouer sur le client anglais."
            ),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=6)
        self._langue = tk.StringVar(value=self._settings.language)
        for code in LANGUAGES:
            ttk.Radiobutton(
                langue, text=code.upper(), value=code, variable=self._langue
            ).pack(side="left", padx=6, pady=4)

        ttk.Button(self._reglages, text="Enregistrer", command=self.save_settings).pack(
            pady=8, anchor="w"
        )
        self._reglages_etat = ttk.Label(self._reglages, text="", anchor="w")
        self._reglages_etat.pack(fill="x")

    def _slider_moved(
        self, name: str, label: str, widget: ttk.Label
    ) -> Callable[[str], None]:
        """Fabrique le rappel d'un curseur, avec sa propre étiquette.

        Une fabrique plutôt qu'une lambda à valeurs par défaut : les cinq
        curseurs partagent la boucle qui les crée, et une lambda y capturerait
        la variable de boucle, donc la dernière valeur pour tous les cinq. Le
        défaut ne se verrait qu'en bougeant un curseur et en voyant le libellé
        d'un autre changer.
        """

        def rappel(_event: str) -> None:
            widget.config(text=f"{label} : {self._vars[name].get():.3g}")

        return rappel

    # ------------------------------------------------------------------ fenêtre

    def _apply_window_style(self) -> None:
        """Toujours au-dessus, et à l'opacité choisie.

        « Toujours au-dessus » est une propriété de fenêtre ordinaire, accordée
        par le système. Rien n'est injecté dans le jeu, aucune fonction
        graphique n'est accrochée : la limite du projet vise l'injection, et
        elle tient.
        """
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", self._settings.opacity)

    def _place_beside_the_game(self) -> None:
        """Pose la fenêtre à côté des quêtes, jamais dessus."""
        fenêtre = find_game_window()
        if fenêtre is None:
            return
        place = choose(fenêtre, self.zones(fenêtre), WINDOW_SIZE)
        if place is None:
            # Aucune position n'évite les zones lues. On ne pose rien de force :
            # ce serait casser la mesure en silence pour un confort d'affichage.
            return
        self.root.geometry(f"{place.width}x{place.height}+{place.left}+{place.top}")

    def zones(self, window: Rect) -> tuple[Rect, Rect]:
        """Les deux zones lues, choisies par le joueur ou calculées."""
        échelle = self._settings.ui_scale
        bandeau = self._settings.banner or banner_region(window, ui_scale=échelle)
        suivi = self._settings.tracker or tracker_region(window, ui_scale=échelle)
        return bandeau, suivi

    # ------------------------------------------------------------------ actions

    def refresh_zones(self) -> None:
        """Réaffiche la position des deux zones, et l'avertissement éventuel."""
        fenêtre = find_game_window()
        if fenêtre is None:
            for étiquette in self._zone_labels.values():
                étiquette.config(text="jeu introuvable")
            return
        bandeau, suivi = self.zones(fenêtre)
        états = {
            "banner": ZoneState("Bandeau", bandeau, chosen=self._settings.banner is not None),
            "tracker": ZoneState("Suivi", suivi, chosen=self._settings.tracker is not None),
        }
        for clé, état in états.items():
            self._zone_labels[clé].config(text=describe_zone(état))
        self._warn_if_blinding(bandeau, suivi)

    def _warn_if_blinding(self, bandeau: Rect, suivi: Rect) -> None:
        """Prévient si la fenêtre couvre ce qu'elle lit."""
        try:
            ici = Rect(
                self.root.winfo_x(),
                self.root.winfo_y(),
                self.root.winfo_width(),
                self.root.winfo_height(),
            )
        except tk.TclError:  # pragma: pas de couverture
            return
        aveuglées = conflicts(ici, (bandeau, suivi))
        message = describe_conflict(
            aveuglées, {"le bandeau de quête": bandeau, "le panneau de suivi": suivi}
        )
        self._avertissement.config(text=message or "")

    def read_zones_now(self) -> None:
        """Lit les deux zones et montre ce que la reconnaissance en tire.

        C'est l'apport réel de cet onglet. Sans lui, régler un rectangle revient
        à le déplacer à l'aveugle puis à jouer une session entière pour
        découvrir qu'il était à côté.

        La lecture est lente, une à deux secondes pour le panneau de suivi, donc
        elle a lieu sur demande et jamais en boucle.
        """
        fenêtre = find_game_window()
        if fenêtre is None:
            self._set_reading("banner", ())
            self._set_reading("tracker", ())
            return
        from ..reading import RapidOcrReader

        lecteur = RapidOcrReader()
        for clé, zone in zip(("banner", "tracker"), self.zones(fenêtre), strict=True):
            try:
                with ScreenCapture(zone) as capture:
                    lignes = lecteur.read(capture.grab_gray())
            except Exception:  # pragma: pas de couverture
                lignes = []
            self._set_reading(clé, tuple(texte for texte, _score in lignes))
        self.refresh_zones()

    def _set_reading(self, clé: str, lignes: tuple[str, ...]) -> None:
        état = ZoneState(clé, Rect(0, 0, 1, 1), chosen=False, lines=lignes)
        composant = self._zone_readings[clé]
        composant.config(state="normal")
        composant.delete("1.0", "end")
        composant.insert("1.0", describe_reading(état))
        composant.config(state="disabled")

    def reset_zones(self) -> None:
        """Oublie les zones choisies, et revient au calcul qui suit la fenêtre."""
        self._settings = replace(self._settings, banner=None, tracker=None)
        save(self._settings, self._home)
        self.refresh_zones()

    def save_settings(self) -> None:
        """Enregistre les réglages, bornés, et applique ce qui est immédiat."""
        self._settings = replace(
            self._settings,
            language=self._langue.get(),
            ui_scale=self._vars["ui_scale"].get(),
            presence_threshold=self._vars["presence_threshold"].get(),
            poll_interval=self._vars["poll_interval"].get(),
            upcoming_count=int(self._vars["upcoming_count"].get()),
            opacity=self._vars["opacity"].get(),
        ).normalised()
        chemin = save(self._settings, self._home)
        self.root.wm_attributes("-alpha", self._settings.opacity)
        self._reglages_etat.config(text=f"enregistré dans {chemin}")
        self.refresh_zones()

    # ------------------------------------------------------------------ boucle

    def _drain(self) -> None:
        """Vide la file du fil de mesure, depuis le fil de Tk.

        Tout passe par ici : c'est le seul endroit d'où les composants sont
        touchés, et c'est ce qui rend l'ensemble sûr malgré le fil de mesure.
        """
        try:
            while True:
                genre, charge = self._messages.get_nowait()
                self._handle(genre, charge)
        except queue.Empty:
            pass
        if not self._stop.is_set():
            self.root.after(REFRESH_MS, self._drain)

    def _handle(self, genre: str, charge: Any) -> None:
        if genre == "etat":
            self._etat.config(text=str(charge))
        elif genre == "compteurs":
            self._compteurs.config(text=str(charge))
        elif genre == "suivantes":
            self._liste.config(state="normal")
            self._liste.delete("1.0", "end")
            self._liste.insert("1.0", str(charge))
            self._liste.config(state="disabled")

    def publish(self, genre: str, charge: Any) -> None:
        """Dépose un message pour l'affichage. Appelable depuis n'importe quel fil."""
        self._messages.put((genre, charge))

    def close(self) -> None:
        self._stop.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
