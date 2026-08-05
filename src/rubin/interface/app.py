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
from ..references import ReferenceClient
from ..settings import LANGUAGES, LIMITS, load, save
from ..timing import Quality
from ..upcoming import upcoming
from .picker import ZonePicker
from .presentation import (
    ZoneState,
    describe_conflict,
    describe_reading,
    describe_zone,
    format_duration,
    format_gap,
    format_reference,
    format_upcoming_line,
)
from .session import MeasuringSession
from .theme import COLORS, FAMILY, MONO_FAMILY, confidence_score
from .theme import apply as apply_theme

#: Taille de la fenêtre. Assez large pour un nom de quête complet, assez étroite
#: pour tenir à côté du panneau de suivi sans mordre dessus.
WINDOW_SIZE: Final = (460, 560)

#: Période de rafraîchissement de l'affichage, en millisecondes. Huit fois par
#: seconde suffisent : c'est déjà la cadence de capture, et l'œil n'en demande
#: pas plus sur du texte.
REFRESH_MS: Final = 125


class RubinApp:
    """La fenêtre principale, ses trois onglets et ses réglages."""

    def __init__(
        self, home: Path, catalog: Catalog | None = None, server: str | None = None
    ) -> None:
        self._home = home
        self._settings = load(home)
        self._catalog = catalog
        self._messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stop = threading.Event()
        self._server = server
        self._references = ReferenceClient(server)
        self._engine: MeasuringSession | None = None

        self.root = tk.Tk()
        self.root.title("Rubin, chronomètre de quêtes")
        self.root.minsize(*WINDOW_SIZE)
        self.root.configure(background=COLORS["fond"])
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        # L'habillage d'abord : les composants créés ensuite en héritent, alors
        # qu'appliquer un style après coup en laisse toujours un au gris natif.
        apply_theme(self.root)
        self._build_header()
        self._build_tabs()
        self._apply_window_style()
        self._place_beside_the_game()
        self.root.after(REFRESH_MS, self._drain)

    # ------------------------------------------------------------------ mise en place

    def _build_header(self) -> None:
        """Le bandeau du haut : ce qu'on lit sans quitter le jeu des yeux.

        Une seule chose y est grande, la quête en cours. Tout était à la même
        taille dans le premier jet, donc rien ne ressortait, et il fallait lire
        la fenêtre entière pour y trouver l'unique information qu'on cherchait.
        """
        cadre = ttk.Frame(self.root)
        cadre.pack(fill="x", padx=14, pady=(12, 6))
        ttk.Label(cadre, text="RUBIN", style="Section.TLabel").pack(anchor="w")
        self._titre = ttk.Label(cadre, text="En attente du jeu", style="Titre.TLabel")
        self._titre.pack(anchor="w", pady=(2, 0))
        self._sous_titre = ttk.Label(
            cadre, text="lancez Black Desert, puis jouez", style="Faible.TLabel"
        )
        self._sous_titre.pack(anchor="w")

    def _build_tabs(self) -> None:
        carnet = ttk.Notebook(self.root)
        carnet.pack(fill="both", expand=True, padx=10, pady=(4, 10))

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
        commandes = ttk.Frame(self._session)
        commandes.pack(fill="x", padx=12, pady=(12, 6))
        self._bouton = ttk.Button(
            commandes,
            text="Je commence mes quêtes",
            style="Accent.TButton",
            command=self.toggle_session,
        )
        self._bouton.pack(side="left")

        self._etat = ttk.Label(
            self._session, text="", style="Faible.TLabel", anchor="w", wraplength=400
        )
        self._etat.pack(fill="x", padx=12, pady=(0, 6))

        ttk.Label(
            self._session, text="QUÊTES FAITES", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(2, 3))
        self._faites = self._text_box(self._session, height=6)
        self._faites.pack(fill="both", expand=True, padx=12)

        ttk.Label(
            self._session, text="LES QUÊTES QUI SUIVENT", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(8, 3))

        self._liste = self._text_box(self._session, height=7)
        self._liste.pack(fill="both", expand=True, padx=12)

        legende = ttk.Frame(self._session)
        legende.pack(fill="x", padx=12, pady=(8, 4))
        for couleur, texte in (
            (COLORS["sur"], "5 mesures ou plus"),
            (COLORS["moyen"], "peu de mesures"),
            (COLORS["absent"], "jamais mesurée"),
        ):
            # Une pastille et son sens, parce qu'une couleur seule ne se devine
            # pas, et parce que tout ne doit pas reposer sur la couleur.
            pastille = ttk.Label(legende, text="●", foreground=couleur, background=COLORS["fond"])
            pastille.pack(side="left")
            ttk.Label(legende, text=f" {texte}   ", style="Faible.TLabel").pack(side="left")

        self._compteurs = ttk.Label(self._session, text="", style="Faible.TLabel", anchor="w")
        self._compteurs.pack(fill="x", padx=12, pady=(0, 10))

    def _text_box(self, parent: tk.Misc, height: int, mono: bool = False) -> tk.Text:
        """Une zone de texte habillée, `tk.Text` n'obéissant pas aux styles ttk.

        Les lignes de la reconnaissance sont en chasse fixe **exprès** : on y
        cherche des caractères précis, des espaces avalés, un « l » là où il
        devrait y avoir un crochet. Une police proportionnelle masque exactement
        ce qu'on veut voir.
        """
        police = (MONO_FAMILY, 9) if mono else (FAMILY, 10)
        boite = tk.Text(
            parent,
            height=height,
            wrap="word" if mono else "none",
            state="disabled",
            background=COLORS["carte"],
            foreground=COLORS["texte"],
            insertbackground=COLORS["texte"],
            selectbackground=COLORS["accent"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=police,
            padx=10,
            pady=8,
            spacing1=2,
            spacing3=2,
        )
        for nom, couleur in (
            ("sur", COLORS["sur"]),
            ("moyen", COLORS["moyen"]),
            ("absent", COLORS["absent"]),
            ("faible", COLORS["faible"]),
        ):
            boite.tag_configure(nom, foreground=couleur)
        return boite

    def _build_zones(self) -> None:
        ttk.Label(
            self._zones,
            text=(
                "Rubin lit ces deux rectangles. S'ils tombent à côté, il ne mesure\n"
                "rien et ne peut pas dire pourquoi."
            ),
            style="Faible.TLabel",
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(12, 8))

        self._zone_labels: dict[str, ttk.Label] = {}
        self._zone_readings: dict[str, tk.Text] = {}
        for clé, nom in (("banner", "BANDEAU DE QUÊTE"), ("tracker", "PANNEAU DE SUIVI")):
            ttk.Label(self._zones, text=nom, style="Section.TLabel", anchor="w").pack(
                fill="x", padx=12, pady=(6, 2)
            )
            self._zone_labels[clé] = ttk.Label(
                self._zones, text="", style="Faible.TLabel", anchor="w"
            )
            self._zone_labels[clé].pack(fill="x", padx=12)
            lecture = self._text_box(self._zones, height=4, mono=True)
            lecture.pack(fill="both", expand=True, padx=12, pady=(4, 2))
            self._zone_readings[clé] = lecture

        boutons = ttk.Frame(self._zones)
        boutons.pack(fill="x", padx=12, pady=(8, 4))
        ttk.Button(
            boutons, text="Lire maintenant", style="Accent.TButton", command=self.read_zones_now
        ).pack(side="left")
        ttk.Button(boutons, text="Zones calculées", command=self.reset_zones).pack(
            side="left", padx=8
        )

        tracer = ttk.Frame(self._zones)
        tracer.pack(fill="x", padx=12, pady=(0, 4))
        for clé, libellé in (("banner", "Tracer le bandeau"), ("tracker", "Tracer le suivi")):
            ttk.Button(
                tracer, text=libellé, command=self._pick(clé)
            ).pack(side="left", padx=(0, 8))

        self._avertissement = ttk.Label(
            self._zones, text="", style="Alerte.TLabel", anchor="w", justify="left", wraplength=400
        )
        self._avertissement.pack(fill="x", padx=12, pady=(4, 10))
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
            cadre.pack(fill="x", padx=12, pady=(8, 0))
            valeur = tk.DoubleVar(value=float(getattr(self._settings, nom)))
            self._vars[nom] = valeur

            # Le libellé à gauche, la valeur à droite en accent : l'œil suit une
            # colonne de chiffres, il ne relit pas cinq phrases pour trouver
            # celui qui a bougé.
            ligne = ttk.Frame(cadre)
            ligne.pack(fill="x")
            ttk.Label(ligne, text=libellé, anchor="w").pack(side="left")
            étiquette = ttk.Label(ligne, text=f"{valeur.get():g}", style="Valeur.TLabel")
            étiquette.pack(side="right")
            ttk.Scale(
                cadre,
                from_=bas,
                to=haut,
                variable=valeur,
                command=self._slider_moved(nom, étiquette),
            ).pack(fill="x", pady=(2, 0))

        ttk.Label(
            self._reglages, text="LANGUE DU CLIENT DE JEU", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(16, 2))
        langue = ttk.Frame(self._reglages)
        langue.pack(fill="x", padx=12)
        ttk.Label(
            langue,
            text=(
                "Celle du jeu, pas la vôtre : on peut être francophone\n"
                "et jouer sur le client anglais."
            ),
            style="Faible.TLabel",
            anchor="w",
            justify="left",
        ).pack(fill="x")
        self._langue = tk.StringVar(value=self._settings.language)
        for code in LANGUAGES:
            ttk.Radiobutton(
                langue, text=code.upper(), value=code, variable=self._langue
            ).pack(side="left", padx=(0, 14), pady=6)

        ttk.Button(
            self._reglages, text="Enregistrer", style="Accent.TButton",
            command=self.save_settings,
        ).pack(padx=12, pady=(14, 4), anchor="w")
        self._reglages_etat = ttk.Label(
            self._reglages, text="", style="Faible.TLabel", anchor="w", wraplength=400
        )
        self._reglages_etat.pack(fill="x", padx=12, pady=(0, 10))

    def _slider_moved(self, name: str, widget: ttk.Label) -> Callable[[str], None]:
        """Fabrique le rappel d'un curseur, avec sa propre étiquette.

        Une fabrique plutôt qu'une lambda à valeurs par défaut : les cinq
        curseurs partagent la boucle qui les crée, et une lambda y capturerait
        la variable de boucle, donc la dernière valeur pour tous les cinq. Le
        défaut ne se verrait qu'en bougeant un curseur et en voyant la valeur
        d'un autre changer.
        """

        def rappel(_event: str) -> None:
            widget.config(text=f"{self._vars[name].get():.3g}")

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

    def _pick(self, which: str) -> Callable[[], None]:
        """Ouvre le tracé de zone, sur une photographie du jeu.

        Une fabrique et non une lambda : les deux boutons naissent d'une boucle,
        et une lambda y capturerait la variable, donc la même zone pour les deux.
        """

        def ouvrir() -> None:
            fenêtre = find_game_window()
            if fenêtre is None:
                self._avertissement.config(text="jeu introuvable, impossible de tracer")
                return
            titre = "Bandeau de quête" if which == "banner" else "Panneau de suivi"
            ZonePicker(self.root, fenêtre, titre, self._zone_chosen(which))

        return ouvrir

    def _zone_chosen(self, which: str) -> Callable[[Rect], None]:
        def retenir(zone: Rect) -> None:
            # Deux branches explicites plutôt qu'un nom de champ calculé :
            # le vérificateur de types ne sait rien d'une clé construite à
            # l'exécution, et une faute de frappe y passerait inaperçue
            # jusqu'au moment où le réglage ne s'enregistre pas.
            if which == "banner":
                self._settings = replace(self._settings, banner=zone)
            else:
                self._settings = replace(self._settings, tracker=zone)
            save(self._settings, self._home)
            self.refresh_zones()
            # Lire tout de suite : le seul moyen de savoir si le tracé est bon
            # est de voir ce qu'on en tire, et l'attente d'une session entière
            # est précisément ce qu'on cherche à supprimer.
            self.read_zones_now()

        return retenir

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
        elif genre == "demarre":
            self._set_running(bool(charge))
        elif genre == "progres":
            self._show_progress(charge)
        elif genre == "mesure":
            self._add_measure(*charge)
        elif genre == "position":
            self._show_upcoming(*charge)

    def _set_running(self, running: bool) -> None:
        self._bouton.config(
            text="Arrêter" if running else "Je commence mes quêtes",
            style="TButton" if running else "Accent.TButton",
        )

    def _show_progress(self, progress: Any) -> None:
        morceaux = [f"{progress.measured} mesurées"]
        if progress.deduced:
            morceaux.append(f"{progress.deduced} déduites")
        if progress.failed:
            # Dit ce qui a échoué plutôt que de le taire : un silence total ne
            # distingue pas « le jeu ne montre rien » de « je ne sais pas lire ».
            morceaux.append(f"{progress.failed} illisibles")
        morceaux.append(f"{int(progress.elapsed)} s")
        self._compteurs.config(text="   ".join(morceaux))

    def _add_measure(self, measure: Any, language: str) -> None:
        """Ajoute une quête terminée en haut de la liste des faites."""
        quest = self._catalog.get(measure.quest_id, language) if self._catalog else None
        nom = quest.name if quest else str(measure.quest_id)
        reference = self._references.quest(measure.quest_id) if self._references else None
        échantillons = reference.samples if reference else 0
        score = confidence_score(échantillons)
        écart = reference.compare(measure.seconds) if reference else ""
        marque = "" if measure.quality is Quality.EXACT else "  (déduite)"

        self._faites.config(state="normal")
        self._faites.insert("1.0", f"{format_duration(measure.seconds)}  {nom}{marque}\n")
        self._faites.insert("1.0", "")  # ancre pour la balise de couleur
        self._faites.tag_add(_tag_for(échantillons), "1.0", "1.end")
        détail = f"    {score}/100  ({échantillons} mesures)"
        if écart:
            détail += f"  {écart}"
        self._faites.insert("2.0", "")
        self._faites.config(state="disabled")
        self._faites.see("1.0")

    def _show_upcoming(self, chain: int, position: int, references: Any) -> None:
        """Réaffiche la liste des quêtes à venir, avec leur score."""
        if self._catalog is None:
            return
        suivantes = upcoming(
            self._catalog,
            chain,
            position,
            language=self._settings.language,
            count=self._settings.upcoming_count,
            references=references,
        )
        self._liste.config(state="normal")
        self._liste.delete("1.0", "end")
        for item in suivantes:
            trou = format_gap(item)
            if trou:
                self._liste.insert("end", f"  {trou}\n", "faible")
            échantillons = item.reference.samples if item.reference else 0
            # Un trou juste avant plafonne le score : le temps peut être bon,
            # la place ne l'est pas, et les deux moitiés de la question doivent
            # tenir ensemble.
            score = confidence_score(échantillons, placed=not item.gap_before)
            self._liste.insert("end", f"{score:>3}  ", _tag_for(échantillons))
            self._liste.insert("end", f"{format_upcoming_line(item)}\n")
            self._liste.insert("end", f"     {format_reference(item)}\n", "faible")
        self._liste.config(state="disabled")

    def publish(self, genre: str, charge: Any) -> None:
        """Dépose un message pour l'affichage. Appelable depuis n'importe quel fil."""
        self._messages.put((genre, charge))

    def toggle_session(self) -> None:
        """Démarre ou arrête la mesure, selon l'état.

        Un bouton, pas un démarrage automatique : capturer l'écran de
        quelqu'un doit être un geste qu'il fait. Il dit aussi au logiciel
        « je commence les quêtes », ce qu'une session ouverte pendant qu'on
        est au marché ne dirait pas.
        """
        if self._engine is not None and self._engine.running:
            self._etat.config(text="arrêt en cours, bilan de la session…")
            self._engine.stop()
            return
        if self._catalog is None:
            self._etat.config(text="référentiel indisponible, mesure impossible")
            return
        self._engine = MeasuringSession(
            self._home, self._catalog, self._settings, self.publish, self._server
        )
        self._engine.start()

    def close(self) -> None:
        # Le moteur d'abord : il écrit le lot de la session, et le perdre
        # parce qu'on a fermé la fenêtre serait irrattrapable.
        if self._engine is not None and self._engine.running:
            self._engine.stop()
        self._stop.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def _tag_for(samples: int) -> str:
    """La balise de couleur d'un score, selon ce qui l'adosse."""
    if samples <= 0:
        return "absent"
    return "sur" if samples >= 5 else "moyen"
