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
import time
import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tkinter import ttk
from typing import Any, Final

import requests

from ..capture import (
    Rect,
    ScreenCapture,
    banner_region,
    choice_region,
    find_game_window,
    tracker_region,
)
from ..placement import choose, conflicts
from ..protocol import PlayerIdentity
from ..reference import Catalog, Quest, QuestId
from ..references import RANKING_LIMIT, RankedQuest, ReferenceClient
from ..settings import LANGUAGES, LIMITS, WindowSize, load, save
from ..timing import Quality
from ..upcoming import upcoming
from .autozone import search as search_banner_zone
from .help import EXAMPLES, HelpWindow
from .picker import ZonePicker, png_data
from .presentation import (
    COVERAGE_TAGS,
    DEMO_BANNER,
    LOCKED_WHILE_MEASURING,
    SEARCH_MIN_LENGTH,
    ZoneState,
    demo_active,
    demo_ranking,
    describe_conflict,
    describe_reading,
    describe_zone,
    format_coverage,
    format_current_reference,
    format_duration,
    format_gap,
    format_link,
    format_measure_line,
    format_other_quests,
    format_quest_times,
    format_ranking,
    format_reference,
    format_running,
    format_search_result,
    format_upcoming_line,
    format_watching,
    lock_label,
    main_quest_total,
    other_quest_total,
    ranking_message,
    running_seconds,
    search_quests,
    zone_lock_reason,
)
from .session import MeasuringSession
from .theme import COLORS, FAMILY, MONO_FAMILY, confidence_score
from .theme import apply as apply_theme
from .tooltip import Tooltip

#: Taille de la fenêtre. Assez large pour un nom de quête complet, assez étroite
#: pour tenir à côté du panneau de suivi sans mordre dessus.
WINDOW_SIZE: Final = (470, 700)

#: Période de rafraîchissement de l'affichage, en millisecondes. Huit fois par
#: seconde suffisent : c'est déjà la cadence de capture, et l'œil n'en demande
#: pas plus sur du texte.
REFRESH_MS: Final = 125

#: Ce qu'on écrit sous le nom de la quête, selon le bandeau vu.
#:
#: Les deux derniers ne produisent aucune mesure, et le disent. Sans cela, un
#: joueur qui enchaîne les objectifs d'une même quête voit un logiciel muet et
#: en conclut qu'il ne marche pas, alors qu'il lit parfaitement.
SEEN_LABELS: Final = {
    "acceptee": "quête acceptée, chronomètre lancé",
    "accomplie": "quête accomplie, temps enregistré",
    "objectif-partiel": "objectif en cours (ne borne aucune durée)",
    "objectif-accompli": "objectif accompli (ne borne aucune durée)",
}

#: Largeur des aperçus de zone, en pixels.
PREVIEW_WIDTH: Final = 400

#: Les trois zones lues, et **à quoi elles servent**.
#:
#: Le rôle est affiché sous chaque titre. Sans lui, le joueur voit trois
#: rectangles sans savoir lequel compte, ni ce qu'il casse en le déplaçant. Or
#: les trois n'ont pas du tout le même poids : sans le bandeau, rien n'est jamais
#: mesuré ; sans le panneau de suivi, on perd seulement de quoi lever une
#: ambiguïté ; sans le panneau de choix, on perd les noms coupés et le chemin
#: pris à un carrefour, mais aucune durée.
ZONE_ROLES: Final = (
    (
        "banner",
        "BANDEAU DE QUÊTE",
        "En bas à droite. Il apparaît quand vous acceptez ou terminez une "
        "quête, et c'est LUI qui déclenche le chronomètre. Mal placé, rien "
        "n'est jamais mesuré.",
    ),
    (
        "tracker",
        "PANNEAU DE SUIVI",
        "Sous la minimap. Il dit dans quelle chaîne vous êtes, ce qui permet "
        "de trancher quand un nom lu désigne plusieurs quêtes. Mal placé, on "
        "mesure quand même, on identifie seulement moins bien.",
    ),
    (
        "choice",
        "PANNEAU DE CHOIX",
        "Au centre, quand une quête vous fait choisir entre deux suites. Il "
        "sert à deux choses : identifier les quêtes dont le jeu coupe le "
        "préfixe de région, et savoir laquelle des deux branches vous avez "
        "prise. Mal placé, ces quêtes ne sont pas reconnues et la branche "
        "reste inconnue, mais aucune durée n'est perdue. ZONE ESTIMÉE, jamais "
        "mesurée en jeu : c'est celle qui a le plus besoin d'être tracée à la "
        "main.",
    ),
)

#: Les clés des zones, dans l'ordre exact où `RubinApp.zones` les rend.
#:
#: Une seule source pour cet ordre : deux listes parallèles finiraient par
#: diverger, et une zone appariée à la mauvaise lui prêterait la lecture d'une
#: autre, ce qui ne lève aucune erreur et ne se voit qu'à l'œil.
ZONE_KEYS: Final = tuple(zone[0] for zone in ZONE_ROLES)


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
        self._auto: threading.Thread | None = None
        self._reading: threading.Thread | None = None
        #: Le classement rendu par le serveur, tel qu'il est arrivé. `None` tant
        #: qu'il n'a rien dit, ce qui ne veut pas dire « aucune quête classée » :
        #: voir `ranking_message`.
        self._ranking: tuple[RankedQuest, ...] | None = None
        #: Les quêtes proposées par la recherche, dans l'ordre de la liste
        #: affichée. Gardées à part parce qu'une ligne de liste est du texte, et
        #: qu'on a besoin de l'identifiant pour interroger le serveur.
        self._found: tuple[Quest, ...] = ()
        #: Compteur pour donner à chaque nom cliquable de « QUÊTES FAITES » une
        #: étiquette Tk unique. Un tag partagé entre plusieurs lignes déclenche
        #: le clic sur TOUTES en même temps ; en principe inoffensif ici, le nom
        #: étant le même, mais fragile le jour où deux quêtes homonymes de
        #: chaînes différentes coexistent dans la liste.
        self._compteur_liens = 0

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
        self._ask_server()
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
        # Le temps qui court, en accent : c'est la deuxième chose qu'on vient
        # chercher d'un coup d'œil, après le nom de la quête. En dessous du
        # sous-titre et non à côté, pour qu'un nom de quête long ne le pousse
        # jamais hors de la fenêtre.
        self._chrono = ttk.Label(cadre, text="", style="Valeur.TLabel")
        self._chrono.pack(anchor="w", pady=(4, 0))
        # Le meilleur temps connu de la quête EN COURS, sous le chronomètre qui
        # tourne : voir une référence pendant qu'on joue, pas seulement une fois
        # la quête finie. Voir `format_current_reference`.
        self._record_en_cours = ttk.Label(cadre, text="", style="Faible.TLabel")
        self._record_en_cours.pack(anchor="w", pady=(0, 0))
        # Le témoin de connexion, sous le chronomètre : visible depuis n'importe
        # quel onglet, parce que la question « est-ce que je suis relié ? » se
        # pose de partout. Un mot **et** une couleur, jamais la couleur seule.
        self._lien = ttk.Label(
            cadre, text="serveur : vérification…", style="Faible.TLabel",
            wraplength=430, justify="left",
        )
        self._lien.pack(anchor="w", pady=(4, 0))

    def _build_tabs(self) -> None:
        carnet = ttk.Notebook(self.root)
        carnet.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        # Retenu : l'onglet Zones se verrouille entier pendant la mesure, et il
        # faut pouvoir le désigner plus tard. Voir `_lock_zone_controls`.
        self._carnet = carnet

        self._session = ttk.Frame(carnet)
        self._classement = ttk.Frame(carnet)
        self._zones = ttk.Frame(carnet)
        self._reglages = ttk.Frame(carnet)
        carnet.add(self._session, text="Session")
        carnet.add(self._classement, text="Classement")
        carnet.add(self._zones, text="Zones")
        carnet.add(self._reglages, text="Réglages")

        # L'infobulle du carnet ne parle QUE de l'onglet Zones : c'est un seul
        # composant qui en porte quatre, et une explication de verrou apparue
        # au survol de « Réglages » ferait croire qu'il est verrouillé aussi.
        self._carnet_tip = Tooltip(carnet, when=self._over_zones_tab)

        self._build_session()
        self._build_ranking()
        self._build_zones()
        self._build_settings()

        # Entrer dans l'onglet des zones déclenche la lecture. Voir
        # `_tab_changed` : elle a lieu dans un fil, parce qu'elle coûte une
        # seconde et demie et figerait la fenêtre autrement.
        self._carnet = carnet
        carnet.bind("<<NotebookTabChanged>>", self._tab_changed)

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
        self._etat.pack(fill="x", padx=12, pady=(0, 2))

        # Ce que la surveillance voit, rafraîchi à chaque tour de la boucle de
        # mesure. Juste sous l'état, parce que les deux se lisent ensemble :
        # « mesure en cours » dit ce que le logiciel CROIT faire, cette
        # ligne-ci dit ce qu'il voit RÉELLEMENT. Le 5 août 2026, les deux se
        # contredisaient pendant quinze minutes et rien ne le montrait.
        self._surveillance = ttk.Label(
            self._session, text="", style="Faible.TLabel", anchor="w", wraplength=400
        )
        self._surveillance.pack(fill="x", padx=12, pady=(0, 6))

        ttk.Label(
            self._session, text="QUÊTES FAITES", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(2, 3))
        self._faites = self._text_box(self._session, height=6)
        self._faites.pack(fill="both", expand=True, padx=12)
        # Configuré une seule fois, réutilisé par chaque nom cliquable. Après
        # les tags de couleur posés par `_text_box` : à recouvrement, Tk donne
        # priorité au tag configuré le plus récemment, donc la couleur du lien
        # gagne sur la couleur de confiance pour la portion du nom.
        self._faites.tag_configure("lien", foreground=COLORS["accent"], underline=True)
        self._faites.tag_bind("lien", "<Enter>", lambda _e: self._faites.config(cursor="hand2"))
        self._faites.tag_bind("lien", "<Leave>", lambda _e: self._faites.config(cursor=""))

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
        self._compteurs.pack(fill="x", padx=12, pady=(0, 2))

        # La couverture des 3 924 quêtes principales, juste sous la légende qui
        # dit ce que chaque couleur veut dire.
        #
        # Trois étiquettes et non une seule : une `ttk.Label` n'a qu'une couleur
        # de texte, et ici la couleur EST l'information, celle qui rattache
        # chaque compte à sa pastille. Le séparateur voyage dans le texte du
        # morceau qui précède, sinon des virgules orphelines resteraient à
        # l'écran tant que le serveur n'a pas répondu.
        self._couverture = ttk.Frame(self._session)
        self._couverture.pack(fill="x", padx=12, pady=(0, 10))
        self._couverture_parts = [
            ttk.Label(
                self._couverture,
                text="",
                foreground=COLORS[balise],
                background=COLORS["fond"],
                font=(FAMILY, 9),
            )
            for balise in COVERAGE_TAGS
        ]
        for morceau in self._couverture_parts:
            morceau.pack(side="left")
        self._couverture_etat = ttk.Label(
            self._couverture, text="couverture : demandée au serveur…", style="Faible.TLabel"
        )
        self._couverture_etat.pack(side="left")

        # Les quêtes hors périmètre, sur leur propre ligne et **jamais** dans le
        # total au-dessus. Rubin ne mesure que les principales, par conception :
        # les mêler donnerait un chiffre décourageant et faux, puisqu'on n'a
        # jamais eu l'intention de mesurer les autres.
        self._autres = ttk.Label(
            self._session, text="", style="Faible.TLabel", anchor="w", wraplength=420
        )
        self._autres.pack(fill="x", padx=12, pady=(0, 10))

    def _build_ranking(self) -> None:
        """L'onglet de consultation : chercher une quête, et voir les plus rapides.

        Deux sections dans un seul onglet, parce qu'elles répondent à la même
        question par deux bouts : « combien de temps prend celle-ci » et
        « lesquelles vont vite ». Les deux ne lisent que le serveur, ne mesurent
        rien et n'envoient rien.

        ⚠️ **L'onglet défile**, et ce n'est pas une précaution de style. Mesuré
        à l'écran : son contenu demande 628 pixels là où la fenêtre en offre
        505, et le panneau des temps grandit encore quand on choisit une quête.
        Sans défilement, Tk n'affiche simplement pas ce qui dépasse, et c'est la
        ligne d'état du bas qui disparaissait, **présente et invisible** :
        justement celle qui dit « aucune quête n'a encore assez de mesures ». Le
        message le plus important de l'onglet était le premier sacrifié.

        La ligne d'état est en outre posée **avant** le tableau, pour qu'elle
        reste lisible même si le bas venait à être coupé un jour.
        """
        dedans = self._scrollable(self._classement)
        ttk.Label(
            dedans, text="CHERCHER UNE QUÊTE", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(12, 2))
        ttk.Label(
            dedans,
            text=(
                "Trois lettres suffisent, accents et crochets sans importance.\n"
                "Quêtes principales seulement : les seules que Rubin mesure."
            ),
            style="Faible.TLabel", anchor="w", justify="left",
        ).pack(fill="x", padx=12)

        self._recherche = tk.StringVar()
        champ = ttk.Entry(dedans, textvariable=self._recherche)
        champ.pack(fill="x", padx=12, pady=(6, 4))
        # `trace_add` plutôt qu'une touche relâchée : le collage à la souris ne
        # produit aucune touche, et une recherche qui ignore le collage passe
        # pour une recherche cassée.
        self._recherche.trace_add("write", self._search_changed)

        # Une liste et non une zone de texte : on vient y cliquer, et `tk.Text`
        # ne sait pas dire quelle ligne a été choisie sans qu'on la calcule.
        self._resultats = tk.Listbox(
            dedans,
            height=4,
            background=COLORS["carte"],
            foreground=COLORS["texte"],
            selectbackground=COLORS["accent"],
            selectforeground=COLORS["texte"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            font=(FAMILY, 10),
        )
        self._resultats.pack(fill="x", padx=12)
        self._resultats.bind("<<ListboxSelect>>", self._result_chosen)

        self._temps = ttk.Label(
            dedans, text="", style="Faible.TLabel", anchor="w",
            justify="left", wraplength=400,
        )
        self._temps.pack(fill="x", padx=12, pady=(4, 0))

        ttk.Label(
            dedans,
            text="LES QUÊTES LES PLUS RAPIDES",
            style="Section.TLabel",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))
        ttk.Label(
            dedans,
            text=(
                "Au temps médian, jamais au record : un record se falsifie en un\n"
                "envoi. À partir de trois mesures, sans quoi la première place\n"
                "irait toujours à une quête mesurée une seule fois."
            ),
            style="Faible.TLabel", anchor="w", justify="left",
        ).pack(fill="x", padx=12)

        self._demo = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dedans,
            text="Mode démonstration (lignes fabriquées, marquées TEST)",
            variable=self._demo,
            command=self._refresh_ranking,
        ).pack(anchor="w", padx=12, pady=(4, 0))
        self._demo_bandeau = ttk.Label(
            dedans, text="", style="Alerte.TLabel", anchor="w",
            justify="left", wraplength=400,
        )
        self._demo_bandeau.pack(fill="x", padx=12)

        self._classement_etat = ttk.Label(
            dedans, text="classement : demandé au serveur…",
            style="Faible.TLabel", anchor="w", justify="left", wraplength=400,
        )
        self._classement_etat.pack(fill="x", padx=12, pady=(2, 0))
        self._classement_texte = self._text_box(dedans, height=8)
        self._classement_texte.pack(fill="both", expand=True, padx=12, pady=(4, 6))

    def _scrollable(self, parent: ttk.Frame) -> ttk.Frame:
        """Un cadre qui défile, pour que le contenu ne soit jamais coupé.

        Défaut constaté à l'usage : l'onglet des zones demandait 578 pixels de
        haut dans une fenêtre de 560, et Tk n'affiche simplement pas ce qui
        dépasse. Les boutons du bas étaient **présents et invisibles** : le
        joueur en concluait qu'ils n'existaient pas, ce qui est pire qu'un
        bouton grisé, lequel se voit.

        Agrandir la fenêtre ne résout que le cas d'aujourd'hui ; un écran plus
        petit, une police plus grande ou une ligne de plus rétabliraient le
        défaut sans prévenir.
        """
        # Un conteneur à part : mélanger `side="top"` et `side="left"` dans un
        # même cadre donne une mise en page écrasée, sans la moindre erreur. Les
        # boutons au-dessus sont empilés vers le haut, la toile et sa barre
        # côte à côte : les deux ne peuvent pas cohabiter directement.
        cadre = ttk.Frame(parent)
        cadre.pack(fill="both", expand=True)
        toile = tk.Canvas(
            cadre, background=COLORS["fond"], highlightthickness=0, borderwidth=0
        )
        barre = ttk.Scrollbar(cadre, orient="vertical", command=toile.yview)
        dedans = ttk.Frame(toile)
        fenêtre = toile.create_window((0, 0), window=dedans, anchor="nw")

        def contenu_change(_event: object = None) -> None:
            toile.configure(scrollregion=toile.bbox("all"))

        def toile_change(event: tk.Event[tk.Misc]) -> None:
            # La largeur vient de l'événement, jamais de `winfo_width()` : au
            # premier passage la toile n'est pas encore disposée et rend 1, ce
            # qui écrase tout le contenu dans une colonne d'un pixel. Le défaut
            # ne se voit qu'à l'écran, aucune erreur n'est levée.
            toile.itemconfigure(fenêtre, width=event.width)
            toile.configure(scrollregion=toile.bbox("all"))

        dedans.bind("<Configure>", contenu_change)
        toile.bind("<Configure>", toile_change)
        toile.configure(yscrollcommand=barre.set)
        toile.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")

        def molette(event: tk.Event[tk.Misc]) -> None:
            toile.yview_scroll(-event.delta // 120, "units")

        # Liée à la toile et non à toute la fenêtre : sinon la molette ferait
        # défiler cet onglet même quand on regarde ailleurs.
        toile.bind("<MouseWheel>", molette)
        dedans.bind("<MouseWheel>", molette)
        return dedans

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
        # Les commandes d'abord : ce sont elles qu'on vient chercher, et
        # elles ne doivent jamais dépendre de ce qui les précède.
        boutons = ttk.Frame(self._zones)
        boutons.pack(fill="x", padx=12, pady=(12, 2))
        # Les commandes sont retenues par clé, et les clés sont celles de
        # `LOCKED_WHILE_MEASURING`. Une seule table pour le libellé, le cadenas
        # et l'état : un bouton oublié resterait cliquable pendant la mesure
        # sans que rien ne le signale.
        self._zone_buttons: dict[str, ttk.Button] = {}
        self._zone_labels_texts: dict[str, str] = {}
        self._zone_tips: dict[str, Tooltip] = {}

        def commande(parent: ttk.Frame, clé: str, libellé: str, action: Any, **kw: Any) -> None:
            bouton = ttk.Button(parent, text=libellé, command=action, **kw)
            bouton.pack(side="left", padx=kw.pop("padx", 0) or 0)
            self._zone_buttons[clé] = bouton
            self._zone_labels_texts[clé] = libellé
            self._zone_tips[clé] = Tooltip(bouton)

        commande(boutons, "read_now", "Lire maintenant", self.read_zones_now,
                 style="Accent.TButton")
        commande(boutons, "reset", "Zones calculées", self.reset_zones)
        self._zone_buttons["reset"].pack_configure(padx=8)
        commande(boutons, "auto", "Choix automatique", self.auto_zone)

        # Sur sa propre ligne, pas serré dans `boutons` avec les trois autres :
        # à la largeur minimale de la fenêtre (470 px), quatre boutons
        # dépassaient du bord, invisibles et injoignables sans l'élargir à la
        # main. Cette ligne-ci ne le fait pas non plus, contrairement à
        # l'aperçu des zones plus bas, mais un seul bouton tient toujours dans
        # 470 px, vu et vérifié.
        reprise = ttk.Frame(self._zones)
        reprise.pack(fill="x", padx=12, pady=(0, 6))
        # Désactivé par défaut : `refresh_zones`, appelé à la fin de cette
        # méthode, décide s'il y a quelque chose à reprendre. Le bouton EST le
        # « geste » que `Settings.adopted_for` attend avant d'appliquer un
        # ancien tracé, voir son en-tête dans `settings.py`.
        commande(reprise, "adopt", "Reprendre l'ancien tracé", self.adopt_zones, state="disabled")

        tracer = ttk.Frame(self._zones)
        tracer.pack(fill="x", padx=12, pady=(0, 6))
        for clé, libellé in (
            ("banner", "Tracer le bandeau"),
            ("tracker", "Tracer le suivi"),
            ("choice", "Tracer le choix"),
        ):
            commande(tracer, f"pick_{clé}", libellé, self._pick(clé))
            self._zone_buttons[f"pick_{clé}"].pack_configure(padx=(0, 8))
        # La même raison que l'infobulle, mais VISIBLE sans survoler quoi que ce
        # soit. Une infobulle ne se découvre qu'en cherchant, or celui qui vient
        # ici pour régler sa zone doit apprendre tout de suite qu'il ne le peut
        # pas maintenant, et pourquoi.
        self._zones_verrou = ttk.Label(
            self._zones, text="", style="Alerte.TLabel", anchor="w", justify="left",
            wraplength=400,
        )
        self._zones_verrou.pack(fill="x", padx=12, pady=(0, 4))

        self._avertissement = ttk.Label(
            self._zones, text="", style="Alerte.TLabel", anchor="w", justify="left",
            wraplength=400,
        )
        self._avertissement.pack(fill="x", padx=12, pady=(0, 6))

        self._zones_defilant = self._scrollable(self._zones)
        ttk.Label(
            self._zones_defilant,
            text=(
                "Rubin lit ces trois rectangles. Les deux premiers sont mesurés ;\n"
                "s'ils tombent à côté, il ne mesure rien et ne peut pas dire\n"
                "pourquoi. Le troisième est ESTIMÉ : tracez-le vous-même."
            ),
            style="Faible.TLabel",
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(12, 8))

        self._zone_labels: dict[str, ttk.Label] = {}
        self._zone_readings: dict[str, tk.Text] = {}
        self._zone_previews: dict[str, ttk.Label] = {}
        self._zone_photos: dict[str, tk.PhotoImage] = {}
        for clé, nom, rôle in ZONE_ROLES:
            entête = ttk.Frame(self._zones)
            entête.pack(fill="x", padx=12, pady=(8, 1))
            ttk.Label(entête, text=nom, style="Section.TLabel", anchor="w").pack(side="left")
            # Le « ? » montre une VRAIE capture de la cible : décrire « le
            # bandeau en bas à droite » désigne une zone que le joueur croit
            # connaître, jusqu'à ce qu'il tombe à côté.
            ttk.Button(entête, text="?", width=2, command=self._help(clé)).pack(
                side="left", padx=8
            )
            # À quoi sert cette zone, en une phrase. Sans elle, le joueur voit
            # deux rectangles sans savoir lequel compte ni ce qu'il casse en le
            # déplaçant.
            ttk.Label(
                self._zones, text=rôle, style="Faible.TLabel", anchor="w",
                justify="left", wraplength=400,
            ).pack(fill="x", padx=12)
            self._zone_labels[clé] = ttk.Label(
                self._zones, text="", style="Faible.TLabel", anchor="w"
            )
            self._zone_labels[clé].pack(fill="x", padx=12, pady=(2, 0))
            # L'image de ce qui est réellement capturé. Une position en chiffres
            # ne dit pas si elle tombe au bon endroit ; l'image le dit d'un coup.
            self._zone_previews[clé] = ttk.Label(self._zones, background=COLORS["carte"])
            self._zone_previews[clé].pack(fill="x", padx=12, pady=(4, 0))
            lecture = self._text_box(self._zones, height=3, mono=True)
            lecture.pack(fill="both", expand=True, padx=12, pady=(3, 2))
            self._zone_readings[clé] = lecture

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

        ttk.Label(
            self._reglages, text="COMPTE DISCORD", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(16, 2))
        ttk.Label(
            self._reglages,
            text=(
                "Facultatif, et sans effet sur la mesure. Se connecter permet\n"
                "d'apparaître au classement sous votre nom au lieu d'un\n"
                "identifiant anonyme. Seul le pseudonyme est demandé : ni\n"
                "courriel, ni serveurs, ni liste d'amis."
            ),
            style="Faible.TLabel", anchor="w", justify="left",
        ).pack(fill="x", padx=12)
        ttk.Button(
            self._reglages, text="Se connecter avec Discord", command=self.link_discord
        ).pack(padx=12, pady=(8, 2), anchor="w")
        self._discord_etat = ttk.Label(
            self._reglages, text="", style="Faible.TLabel", anchor="w", wraplength=400
        )
        self._discord_etat.pack(fill="x", padx=12)
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
        """Pose la fenêtre à côté des quêtes, jamais dessus.

        ⚠️ Seules les deux zones **mesurées** entrent dans ce calcul. La zone du
        panneau de choix en est écartée exprès, pour deux raisons qui vont dans
        le même sens : elle est estimée, donc large et probablement fausse, et
        elle occupe le centre de l'écran, donc l'inclure chasserait la fenêtre
        du coin haut-droit où le joueur lit déjà ses quêtes. Céder la seule
        bonne place à une supposition serait payer cher un rectangle que
        personne n'a vérifié.

        Ce que la fenêtre recouvre au centre reste visible là où il faut : dans
        l'aperçu de la zone de choix, qui montre l'image réellement capturée.
        """
        fenêtre = find_game_window()
        if fenêtre is None:
            return
        bandeau, suivi, _choix = self.zones(fenêtre)
        place = choose(fenêtre, (bandeau, suivi), WINDOW_SIZE)
        if place is None:
            # Aucune position n'évite les zones lues. On ne pose rien de force :
            # ce serait casser la mesure en silence pour un confort d'affichage.
            return
        self.root.geometry(f"{place.width}x{place.height}+{place.left}+{place.top}")

    def zones(self, window: Rect) -> tuple[Rect, Rect, Rect]:
        """Les trois zones lues, choisies par le joueur ou calculées.

        Dans l'ordre de `ZONE_ROLES` : bandeau, suivi, choix. Les deux premières
        reposent sur des mesures, la troisième sur une estimation.

        La zone tracée n'est rendue que pour la taille EXACTE de `window`, via
        `Settings.zone_for` : voir l'en-tête de `settings.py`. C'est le chemin
        que #58 avait construit sans jamais le brancher ici, laissant les vieux
        champs `banner`/`tracker`/`choice` s'appliquer sans condition. Une zone
        tracée à une résolution restait donc active à toutes les autres, y
        compris fausse et coupant le titre du bandeau : c'est le défaut qui a
        coûté une matinée de mesures le 5 août 2026.
        """
        échelle = self._settings.ui_scale
        taille = (window.width, window.height)
        bandeau = self._settings.zone_for("banner", taille) or banner_region(
            window, ui_scale=échelle
        )
        suivi = self._settings.zone_for("tracker", taille) or tracker_region(
            window, ui_scale=échelle
        )
        choix = self._settings.zone_for("choice", taille) or choice_region(
            window, ui_scale=échelle
        )
        return bandeau, suivi, choix

    # ------------------------------------------------------------------ actions

    def refresh_zones(self) -> None:
        """Réaffiche la position des trois zones, et l'avertissement éventuel."""
        fenêtre = find_game_window()
        if fenêtre is None:
            for étiquette in self._zone_labels.values():
                étiquette.config(text="jeu introuvable")
            # ⚠️ Avant le `return`, pas après : la disponibilité du bouton
            # d'adoption ne dépend que de `Settings.unkeyed`, jamais de la
            # taille de fenêtre. Le placer après aurait laissé le bouton inerte
            # tant que le jeu n'est pas détecté, alors qu'il n'a besoin de rien
            # savoir de la fenêtre pour SAVOIR s'il y a quelque chose à offrir,
            # seulement pour agir une fois cliqué.
            mesure_en_cours = self._engine is not None and self._engine.running
            if not mesure_en_cours:
                self._refresh_adopt_button()
            return
        bandeau, suivi, choix = self.zones(fenêtre)
        taille = (fenêtre.width, fenêtre.height)

        def état(clé: str, nom: str, rect: Rect) -> ZoneState:
            return ZoneState(
                nom,
                rect,
                chosen=self._settings.zone_for(clé, taille) is not None,
                # Un tracé existe (`unkeyed`) mais ne s'applique à AUCUNE
                # taille, donc pas à celle-ci non plus : c'est le cas exact du
                # 5 août 2026, et la seule raison de le montrer est de le
                # rendre visible avant qu'il coûte une session.
                stray=self._settings.unkeyed(clé) is not None
                and self._settings.zone_for(clé, taille) is None,
            )

        états = {
            "banner": état("banner", "Bandeau", bandeau),
            "tracker": état("tracker", "Suivi", suivi),
            "choice": état("choice", "Choix", choix),
        }
        for clé, état_zone in états.items():
            self._zone_labels[clé].config(text=describe_zone(état_zone))
        self._warn_if_blinding(bandeau, suivi)

        # Seulement hors mesure : pendant une session, `_lock_zone_controls` a
        # déjà tranché, et le recroiser ici lui ferait perdre son cadenas.
        mesure_en_cours = self._engine is not None and self._engine.running
        if not mesure_en_cours:
            self._refresh_adopt_button()

    def _warn_if_blinding(self, bandeau: Rect, suivi: Rect) -> None:
        """Prévient si la fenêtre couvre une zone dont dépend la mesure.

        ⚠️ La zone du panneau de choix n'y figure pas, **exprès**. Estimée, elle
        couvre la moitié centrale de l'écran : l'y ajouter ferait apparaître
        l'avertissement à chaque lancement, puisque la place retenue pour la
        fenêtre la recoupe forcément. Un avertissement toujours allumé n'avertit
        plus de rien, et celui-ci doit rester le signal fort qu'il est
        aujourd'hui, celui qui dit « tu ne mesureras rien ».

        Le message serait faux, en plus d'être permanent : couvrir le panneau
        de choix ne coûte aucune durée, seulement une identification. Ce que
        cette zone capture vraiment se voit d'un coup dans son aperçu, juste à
        côté, et c'est le bon endroit pour s'en apercevoir.
        """
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

    def _tab_changed(self, _event: object = None) -> None:
        """Entrer dans l'onglet des zones suffit à voir ce qui est lu.

        Le bouton restait nécessaire pour relire après avoir bougé quelque chose
        en jeu, mais l'exiger pour un premier aperçu faisait ouvrir un onglet
        vide, qui ne disait rien de l'état.

        ⚠️ La lecture ne peut pas devenir automatique **telle quelle** : elle
        coûte environ une seconde et demie, la reconnaissance travaillant sur
        349x115 puis 340x380, et elle tournait sur le fil de Tk. La rendre
        automatique sans la déporter aurait figé la fenêtre à chaque bascule
        d'onglet, ce qui est pire que le bouton. Voir `read_zones_now`.
        """
        try:
            # Les annotations de tkinter laissent ces deux-là sans type ; c'est
            # une lacune des stubs, pas un doute sur ce qu'elles rendent.
            onglet = self._carnet.tab(  # type: ignore[no-untyped-call]
                self._carnet.select(), "text"  # type: ignore[no-untyped-call]
            )
        except tk.TclError:  # pragma: pas de couverture
            return
        if onglet == "Zones":
            self.read_zones_now()

    def read_zones_now(self) -> None:
        """Lit les trois zones et montre ce que la reconnaissance en tire.

        C'est l'apport réel de cet onglet. Sans lui, régler un rectangle revient
        à le déplacer à l'aveugle puis à jouer une session entière pour
        découvrir qu'il était à côté.

        ⚠️ **La lecture a lieu dans un fil, et ne touche à aucun composant.**
        Elle coûte environ une seconde et demie pour les trois zones, et le fil
        de Tk est celui qui redessine la fenêtre : l'y laisser gelait tout
        pendant ce temps. Le fil dépose dans la file, `_drain` affiche, comme le
        moteur de mesure.

        **Une seule lecture à la fois.** Basculer d'onglet trois fois de suite
        lancerait sinon trois reconnaissances concurrentes sur les mêmes zones,
        pour le même résultat, en se disputant le processeur.

        C'est aussi, à ce jour, le **seul** endroit qui lit la zone de choix :
        la session de mesure ne s'en sert pas. C'est délibéré, et ça se dit
        plutôt que de se laisser croire, parce qu'une zone réglable donne
        l'impression d'être exploitée partout.
        """
        if self._reading is not None and self._reading.is_alive():
            return
        fenêtre = find_game_window()
        if fenêtre is None:
            for clé in ZONE_KEYS:
                self._set_reading(clé, ())
            return
        zones = dict(zip(ZONE_KEYS, self.zones(fenêtre), strict=True))
        # Le dire tout de suite : sans cela l'onglet paraît vide pendant une
        # seconde et demie, et on reclique en croyant que rien ne s'est passé.
        for clé in ZONE_KEYS:
            self._set_reading(clé, ("lecture en cours…",))

        def lire() -> None:
            from ..reading import RapidOcrReader

            lecteur = RapidOcrReader()
            for clé, zone in zones.items():
                image: Any = None
                try:
                    with ScreenCapture(zone) as capture:
                        image = capture.grab_color()
                        lignes = lecteur.read(capture.grab_gray())
                except Exception:  # pragma: pas de couverture
                    image, lignes = None, []
                textes = tuple(texte for texte, _score in lignes)
                self.publish("zone_lue", (clé, zone, image, textes))
            self.publish("zones_lues", None)

        self._reading = threading.Thread(target=lire, daemon=True)
        self._reading.start()

    def _show_preview(self, clé: str, image: object, zone: Rect) -> None:
        """Montre l'image de ce que la zone capture vraiment.

        Une position en chiffres ne dit pas si elle tombe au bon endroit.
        L'image le dit d'un coup, et c'est elle qui a révélé, sur ce poste, que
        la zone du bandeau lisait le chat de guilde.
        """
        try:
            from PIL import Image

            vignette = Image.fromarray(image)  # type: ignore[arg-type]
            largeur = min(PREVIEW_WIDTH, zone.width)
            hauteur = max(1, int(zone.height * largeur / zone.width))
            vignette = vignette.resize((largeur, hauteur))
            # Gardée sur l'instance : Tk ne retient pas ses images, et une image
            # ramassée par le collecteur laisse un cadre vide, sans erreur.
            self._zone_photos[clé] = tk.PhotoImage(data=png_data(vignette))
            self._zone_previews[clé].config(image=self._zone_photos[clé])
        except Exception as erreur:  # pragma: pas de couverture
            # Un aperçu est un confort : son échec ne doit pas empêcher de lire
            # la zone, qui est l'information utile. Mais il se dit, plutôt que
            # de laisser un cadre vide qu'on prendrait pour une zone qui ne
            # capture rien, ce qui est un tout autre problème.
            self._zone_previews[clé].config(image="", text=f"aperçu indisponible : {erreur}")

    def _set_reading(self, clé: str, lignes: tuple[str, ...]) -> None:
        état = ZoneState(clé, Rect(0, 0, 1, 1), chosen=False, lines=lignes)
        composant = self._zone_readings[clé]
        composant.config(state="normal")
        composant.delete("1.0", "end")
        composant.insert("1.0", describe_reading(état))
        composant.config(state="disabled")

    def auto_zone(self) -> None:
        """Cherche seule où le bandeau apparaît, pendant que le joueur joue.

        Lancée dans un fil : la recherche dure jusqu'à deux minutes, et la
        fenêtre doit rester vivante pendant ce temps. Le fil ne touche à aucun
        composant, il passe par la file comme le moteur de mesure.
        """
        if self._auto is not None and self._auto.is_alive():
            return

        def chercher() -> None:
            zone = search_banner_zone(
                lambda message: self.publish("etat_zone", message),
                self._stop.is_set,
            )
            if zone is not None:
                self.publish("zone_trouvee", zone)

        self._auto = threading.Thread(target=chercher, daemon=True)
        self._auto.start()

    def _ask_server(self) -> None:
        """Interroge le serveur et compte le catalogue, dans un fil.

        Dans un fil parce que chaque appel dure jusqu'à cinq secondes quand le
        serveur ne répond pas, et qu'une fenêtre figée quinze secondes au
        lancement est un défaut bien plus visible que ces compteurs ne sont
        utiles. Le fil ne touche à aucun composant : il passe par la file, comme
        le moteur de mesure.

        Une seule fois par lancement, et c'est assumé : rien ne peut bouger
        pendant la session, puisque les mesures ne partent qu'à son arrêt. Les
        compteurs montrent donc l'état au démarrage, et la contribution du jour
        se voit au lancement suivant.

        L'ordre n'est pas indifférent : le témoin de connexion part en premier,
        parce que c'est lui qui explique les silences des deux autres.
        """
        if self._catalog is None:
            self._couverture_etat.config(
                text="couverture inconnue : le référentiel n'est pas chargé"
            )
        elif not self._references.enabled:
            # Sans serveur, rien de faux ne s'affiche : le total des quêtes
            # principales est connu, mais la part mesurée ne l'est pas, et
            # afficher « 3 924 jamais mesurées » serait une affirmation.
            self._couverture_etat.config(
                text="couverture inconnue : aucun serveur, relancez avec --envoyer"
            )
        if not self._references.enabled:
            self._classement_etat.config(
                text="classement indisponible : aucun serveur, relancez avec --envoyer"
            )
        catalogue, langue = self._catalog, self._settings.language

        def demander() -> None:
            self.publish("lien", self._references.health())
            if catalogue is not None:
                # Ne dépend d'aucun serveur : c'est un fait du catalogue, et il
                # s'affiche même quand rien n'est joignable.
                self.publish("autres_quetes", other_quest_total(catalogue, langue))
            if not self._references.enabled:
                return
            self.publish("classement", self._references.fastest_quests(RANKING_LIMIT))
            if catalogue is not None:
                total = main_quest_total(catalogue, langue)
                self.publish("couverture", format_coverage(self._references.coverage(), total))

        threading.Thread(target=demander, daemon=True).start()

    def _search_changed(self, *_arguments: object) -> None:
        """Refiltre le catalogue à chaque frappe, sans aucun réseau.

        Le catalogue est déjà en mémoire, donc la recherche est locale et
        instantanée. Rien n'est demandé au serveur tant qu'on n'a pas choisi une
        quête : chercher ne doit pas coûter une requête par lettre.
        """
        self._found = search_quests(
            self._catalog, self._recherche.get(), self._settings.language
        )
        self._resultats.delete(0, "end")
        for quest in self._found:
            self._resultats.insert("end", format_search_result(quest))
        if not self._found:
            # Distinguer « pas assez de lettres » de « rien trouvé » : les deux
            # donnent une liste vide, et le geste à faire n'est pas le même.
            tapé = self._recherche.get().strip()
            self._temps.config(
                text=""
                if not tapé
                else (
                    f"tapez au moins {SEARCH_MIN_LENGTH} lettres"
                    if len(tapé) < SEARCH_MIN_LENGTH
                    else "aucune quête principale ne porte ce nom"
                )
            )

    def _result_chosen(self, _event: object = None) -> None:
        # Sans type dans les stubs de tkinter, comme `Notebook.select`.
        choix = self._resultats.curselection()  # type: ignore[no-untyped-call]
        if not choix or choix[0] >= len(self._found):
            return
        self._query_reference(self._found[choix[0]])

    def _query_reference(self, quest: Quest) -> None:
        """Demande au serveur les temps d'une quête connue, dans un fil.

        Dans un fil comme tout le reste du réseau : un serveur lent ne doit pas
        figer la fenêtre pendant qu'on clique. Le fil ne touche à aucun
        composant, il passe par la file.

        Extraite de `_result_chosen`, pour servir aussi le clic sur un nom dans
        « QUÊTES FAITES » : la quête y est déjà connue avec certitude, il n'y a
        pas de recherche à refaire, seulement la même requête à poser.
        """
        self._temps.config(text=f"{quest.name} : interrogation du serveur…")
        if not self._references.enabled:
            self._temps.config(
                text=f"{quest.name} : aucun serveur, relancez avec --envoyer"
            )
            return

        def demander() -> None:
            self.publish("temps", (quest, self._references.quest(quest.id)))

        threading.Thread(target=demander, daemon=True).start()

    def _go_to_ranking(self, quest: Quest) -> Callable[[object], None]:
        """Le clic sur un nom de « QUÊTES FAITES » : direction sa fiche.

        Vers la **recherche individuelle**, jamais vers « les plus rapides » :
        ce second classement exige `MIN_SAMPLES_PER_QUEST` (trois) avant d'y
        faire apparaître une quête, exprès, pour ne pas donner la première
        place à une quête mesurée une seule fois par chance. Une quête tout
        juste mesurée n'y figure donc jamais tant que deux autres joueurs ne
        l'ont pas mesurée aussi, et un joueur qui vient de la terminer et qui
        la chercherait là ne la trouverait jamais, sans qu'aucune interface ne
        lui dise pourquoi. La fiche de recherche, elle, montre une quête dès sa
        première mesure, avec la mention « peu sûr » si l'assise est faible :
        c'est l'information, pas son absence.
        """

        def cliquer(_event: object = None) -> None:
            self._carnet.select(self._classement)  # type: ignore[no-untyped-call]
            self._recherche.set(quest.name)
            self._query_reference(quest)

        return cliquer

    def _show_times(self, quest: Quest, reference: Any) -> None:
        """Affiche ce que le serveur sait d'une quête, absence comprise."""
        self._temps.config(text=format_quest_times(quest, reference))

    def _refresh_ranking(self) -> None:
        """Réaffiche le classement, vrai ou de démonstration.

        Un seul endroit qui écrit dans ce tableau : la case à cocher et la
        réponse du serveur y passent toutes les deux, sans quoi cocher la case
        après l'arrivée du classement effacerait ce dernier, ou l'inverse.
        """
        démo = demo_active(self._ranking, self._demo.get())
        lignes = (
            demo_ranking(self._catalog, self._settings.language)
            if démo
            else format_ranking(self._ranking, self._catalog, self._settings.language)
        )
        self._demo_bandeau.config(text=DEMO_BANNER if démo else "")
        self._classement_texte.config(state="normal")
        self._classement_texte.delete("1.0", "end")
        for index, ligne in enumerate(lignes):
            # Les lignes fabriquées sont peintes en « absent », la couleur de ce
            # qui n'est adossé à rien, et portent TEST en clair : la couleur ne
            # fait que doubler le mot, elle ne le remplace pas.
            balise = (
                "absent"
                if démo
                else _tag_for(self._ranking[index].samples if self._ranking else 0)
            )
            self._classement_texte.insert("end", f"{ligne}\n", balise)
        self._classement_texte.config(state="disabled")
        message = None if démo else ranking_message(self._ranking)
        if démo:
            message = "les vraies lignes remplaceront celles-ci dès qu'il y en aura assez"
        self._classement_etat.config(text=message or "")

    def _help(self, which: str) -> Callable[[], None]:
        """Ouvre l'exemple de ce que cette zone doit contenir."""

        def ouvrir() -> None:
            HelpWindow(self.root, which)

        return ouvrir

    def _pick(self, which: str) -> Callable[[], None]:
        """Ouvre le tracé de zone, sur une photographie du jeu.

        Une fabrique et non une lambda : les trois boutons naissent d'une
        boucle, et une lambda y capturerait la variable, donc la même zone pour
        les trois.
        """

        def ouvrir() -> None:
            fenêtre = find_game_window()
            if fenêtre is None:
                self._avertissement.config(text="jeu introuvable, impossible de tracer")
                return
            # Le titre vient de l'aide, pour qu'il n'y ait qu'un seul endroit à
            # corriger le jour où une zone est renommée. Une chaîne calculée ici
            # aurait fini par contredire celle de la fenêtre d'aide sans que
            # rien ne le signale.
            titre = EXAMPLES[which][0]
            ZonePicker(
                self.root, fenêtre, titre, self._zone_chosen(which, (fenêtre.width, fenêtre.height))
            )

        return ouvrir

    def _zone_chosen(self, which: str, size: WindowSize) -> Callable[[Rect], None]:
        """`size` est la taille de fenêtre où le tracé vient d'être fait.

        Sans elle, le rectangle s'appliquerait à toutes les tailles, ce qui est
        exactement le défaut que #58 avait corrigé côté réglages sans jamais le
        brancher ici : voir l'en-tête de `Settings.with_zone`.
        """

        def retenir(zone: Rect) -> None:
            self._settings = self._settings.with_zone(which, size, zone)
            save(self._settings, self._home)
            self.refresh_zones()
            # Lire tout de suite : le seul moyen de savoir si le tracé est bon
            # est de voir ce qu'on en tire, et l'attente d'une session entière
            # est précisément ce qu'on cherche à supprimer.
            self.read_zones_now()

        return retenir

    def reset_zones(self) -> None:
        """Oublie les zones choisies **pour la taille de fenêtre courante**.

        ⚠️ Pour le panneau de choix, « revenir au calcul » revient à revenir à
        une estimation. C'est un recul assumé, et le même que pour les autres :
        un rectangle tracé sur une fenêtre qui a changé de taille est pire
        qu'un rectangle calculé.

        Les tracés faits pour d'AUTRES tailles ne sont pas touchés : c'est tout
        l'intérêt de la table de #58, et l'effacer en bloc referait le défaut
        qu'elle corrige. Si le jeu est introuvable, seuls les champs hérités
        d'avant #58 sont effacés : sans taille de fenêtre, la table indexée ne
        peut rien cibler.
        """
        fenêtre = find_game_window()
        if fenêtre is None:
            self._settings = replace(self._settings, banner=None, tracker=None, choice=None)
        else:
            taille = (fenêtre.width, fenêtre.height)
            réglages = self._settings
            for nom in ZONE_KEYS:
                réglages = réglages.with_zone(nom, taille, None)
            self._settings = réglages
        save(self._settings, self._home)
        self.refresh_zones()

    def adopt_zones(self) -> None:
        """Reprend les tracés d'avant #58, pour la taille de fenêtre courante.

        Le seul chemin par lequel une zone tracée dans un ancien fichier
        redevient active : voir `Settings.adopted_for`, qui refuse de le faire
        toute seule, exprès. Ce bouton EST le geste que ce refus attend.
        """
        fenêtre = find_game_window()
        if fenêtre is None:
            self._avertissement.config(text="jeu introuvable, impossible de reprendre le tracé")
            return
        self._settings = self._settings.adopted_for((fenêtre.width, fenêtre.height))
        save(self._settings, self._home)
        self.refresh_zones()
        self.read_zones_now()

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
        self._refresh_chrono()
        if not self._stop.is_set():
            self.root.after(REFRESH_MS, self._drain)

    def _refresh_chrono(self) -> None:
        """Le temps qui court sur la quête en cours, huit fois par seconde.

        Rafraîchi ici et nulle part ailleurs. `_drain` est déjà le seul endroit
        d'où les composants sont touchés, et il tourne déjà à la bonne cadence :
        un second `after` n'ajouterait qu'un point d'entrée de plus dans Tk,
        pour rien.

        **Ce n'est pas qu'un confort.** Un bandeau de DÉPART ignoré est
        aujourd'hui parfaitement silencieux, et le joueur ne s'aperçoit qu'une
        heure plus tard qu'il manque des quêtes. Un chronomètre qui reste sur
        « aucune quête chronométrée » alors qu'il vient d'en accepter une le lui
        dit sur-le-champ.

        L'horloge est `time.monotonic`, la même que celle du journal
        d'événements. Voir `running_seconds` : mêler les deux horloges donnerait
        un nombre absurde sans lever la moindre erreur.
        """
        moteur = self._engine
        if moteur is None or not moteur.running or moteur.timeline is None:
            # Hors session, pas de chronomètre : « aucune quête chronométrée »
            # sur une fenêtre qui ne mesure pas encore serait un reproche, pas
            # une information.
            self._chrono.config(text="")
            return
        écoulé = running_seconds(moteur.timeline.pending_since, time.monotonic())
        self._chrono.config(text=format_running(écoulé))

    def _handle(self, genre: str, charge: Any) -> None:
        if genre == "etat":
            self._etat.config(text=str(charge))
        elif genre == "demarre":
            self._set_running(bool(charge))
        elif genre == "surveillance":
            self._surveillance.config(text=format_watching(charge))
        elif genre == "progres":
            self._show_progress(charge)
        elif genre == "mesure":
            self._add_measure(*charge)
        elif genre == "vu":
            self._show_seen(*charge)
        elif genre == "etat_zone":
            self._avertissement.config(text=str(charge))
        elif genre == "zone_trouvee":
            # La fenêtre trouvée à l'instant, pas celle du début de la
            # recherche : `search` a pu tourner jusqu'à deux minutes, la
            # fenêtre a pu changer de taille entre-temps.
            fenêtre = find_game_window()
            if fenêtre is not None:
                self._settings = self._settings.with_zone(
                    "banner", (fenêtre.width, fenêtre.height), charge
                )
                save(self._settings, self._home)
            self.refresh_zones()
            self.read_zones_now()
        elif genre == "sous_chrono":
            self._add_split(*charge)
        elif genre == "sans_chaine":
            self._show_no_chain(str(charge))
        elif genre == "position":
            self._show_upcoming(*charge)
        elif genre == "reference_en_cours":
            self._show_current_reference(*charge)
        elif genre == "couverture":
            self._show_coverage(charge)
        elif genre == "autres_quetes":
            self._autres.config(text=format_other_quests(int(charge)) or "")
        elif genre == "lien":
            self._show_link(charge)
        elif genre == "classement":
            self._ranking = charge
            self._refresh_ranking()
        elif genre == "temps":
            self._show_times(*charge)
        elif genre == "zone_lue":
            self._show_zone_reading(*charge)
        elif genre == "zones_lues":
            self.refresh_zones()

    def _set_running(self, running: bool) -> None:
        self._bouton.config(
            text="Arrêter" if running else "Je commence mes quêtes",
            style="TButton" if running else "Accent.TButton",
        )
        # ⚠️ Le titre doit suivre, sans quoi la fenêtre se contredit. Le 5 août
        # 2026, elle a affiché « En attente du jeu / lancez Black Desert, puis
        # jouez » **pendant que la session mesurait**, jeu lancé et trouvé. Ces
        # deux phrases sont le texte de départ des composants, qu'aucune quête
        # lue n'était encore venue remplacer, mais elles se lisent comme un
        # diagnostic. Cherchant pourquoi rien n'était mesuré, j'ai perdu du
        # temps sur une piste que la fenêtre elle-même désignait à tort.
        if running:
            self._titre.config(text="Aucun bandeau lu pour l'instant")
            self._sous_titre.config(text="acceptez ou terminez une quête")
        else:
            self._titre.config(text="En attente du jeu")
            self._sous_titre.config(text="lancez Black Desert, puis jouez")
            self._surveillance.config(text="")
            self._record_en_cours.config(text="")
        self._lock_zone_controls(running)

    def _over_zones_tab(self, x: int, y: int) -> bool:
        """La souris est-elle sur l'étiquette de l'onglet Zones ?

        `index("@x,y")` lève quand le point ne tombe sur aucun onglet, ce qui
        est le cas courant : la souris passe la moitié de son temps dans le
        contenu de l'onglet, pas sur ses étiquettes.
        """
        try:
            ici = self._carnet.index(f"@{x},{y}")  # type: ignore[no-untyped-call]
            return bool(ici == self._carnet.index(self._zones))  # type: ignore[no-untyped-call]
        except tk.TclError:
            return False

    def _lock_zone_controls(self, locked: bool) -> None:
        """Verrouille les commandes de zone pendant la mesure, et dit pourquoi.

        Le cadenas est dans le libellé et l'explication dans une infobulle. Un
        bouton seulement grisé serait le même silence que le reste : « pas
        maintenant » et « cassé » se ressemblent beaucoup vus d'un clic sans
        effet. Voir `zone_lock_reason`, qui porte la raison et sa mesure.
        """
        raison = zone_lock_reason() if locked else ""
        # L'onglet entier d'abord. Un bouton verrouillé au milieu d'un onglet
        # ouvert invite encore à essayer, et laisse croire que le reste de
        # l'onglet, lui, agit sur la session en cours. Ce n'est le cas d'aucune
        # de ses commandes.
        #
        # ⚠️ Quitter l'onglet AVANT de le désactiver : Tk laisse un onglet
        # désactivé rester sélectionné, et le joueur se retrouverait devant une
        # page morte sans savoir comment en sortir.
        if locked and self._carnet.select() == str(self._zones):  # type: ignore[no-untyped-call]
            self._carnet.select(self._session)  # type: ignore[no-untyped-call]
        self._carnet.tab(  # type: ignore[no-untyped-call]
            self._zones,
            text=lock_label("Zones", locked),
            state="disabled" if locked else "normal",
        )
        self._carnet_tip.update(raison)
        for clé in LOCKED_WHILE_MEASURING:
            bouton = self._zone_buttons.get(clé)
            if bouton is None:  # pragma: pas de couverture
                continue
            bouton.config(
                text=lock_label(self._zone_labels_texts[clé], locked),
                state="disabled" if locked else "normal",
            )
            self._zone_tips[clé].update(raison)
        self._zones_verrou.config(text=raison)
        # « adopt » n'a pas deux états mais trois : verrouillé pendant la
        # mesure, désactivé s'il n'y a rien à reprendre, actif sinon. La boucle
        # au-dessus vient de le mettre à "normal" sans le savoir ; ce troisième
        # état corrige seulement le cas où il n'y a rien à reprendre, sans
        # jamais réactiver un bouton verrouillé.
        if not locked:
            self._refresh_adopt_button()

    def _refresh_adopt_button(self) -> None:
        """Active « Reprendre l'ancien tracé » seulement s'il y a un tracé à reprendre.

        Appelée d'ici et de `refresh_zones`, jamais dupliquée : un bouton qui
        reste cliquable sans rien à faire est le même défaut que celui que
        #65 corrigeait, en plus discret puisqu'il ne casse rien au clic, il ne
        fait juste rien.
        """
        if "adopt" not in self._zone_buttons:  # pragma: pas de couverture
            return
        à_reprendre = any(self._settings.unkeyed(nom) is not None for nom in ZONE_KEYS)
        self._zone_buttons["adopt"].config(state="normal" if à_reprendre else "disabled")

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

    def _show_seen(self, reading: Any, language: str) -> None:
        """Annonce un bandeau vu, qu'il produise une mesure ou non.

        Un bandeau d'objectif ne borne aucune durée, et c'est voulu : il se
        passe pendant une quête. Mais se taire dessus laissait croire que rien
        n'était vu, alors que la lecture marchait. Le silence ne distingue pas
        « je ne vois rien » de « je vois, ça ne se mesure pas ».
        """
        quoi = SEEN_LABELS.get(reading.kind.value, reading.kind.value)
        self._titre.config(text=reading.quest_name or "quête non identifiée")
        self._sous_titre.config(text=quoi)

    def _add_measure(self, measure: Any, language: str) -> None:
        """Ajoute une quête terminée en haut de la liste des faites.

        Le nom est cliquable, s'il a pu être résolu en une vraie quête : voir
        `_go_to_ranking`. Demandé par Maxime le 05/08/2026, une fois les
        mesures enfin revenues après la panne du jour.
        """
        quest = self._catalog.get(measure.quest_id, language) if self._catalog else None
        nom = quest.name if quest else str(measure.quest_id)
        reference = self._references.quest(measure.quest_id) if self._references else None
        échantillons = reference.samples if reference else 0
        score = confidence_score(échantillons)
        écart = reference.compare(measure.seconds) if reference else ""
        marque = "" if measure.quality is Quality.EXACT else "  (déduite)"

        ligne, début_nom, fin_nom = format_measure_line(
            format_duration(measure.seconds), nom, marque, score
        )
        détail = f"     {échantillons} mesures"
        if écart:
            détail += f"   {écart}"

        # Les deux lignes sont insérées en tête, le détail d'abord pour qu'il se
        # retrouve SOUS son titre une fois celui-ci inséré à son tour. La
        # dernière quête finie apparaît ainsi en haut, et les précédentes
        # descendent sans être effacées.
        #
        # Le premier jet insérait le titre puis une chaîne vide, et construisait
        # le détail sans jamais l'écrire : le score, le nombre de mesures et
        # l'écart aux autres joueurs étaient calculés pour rien. Une insertion
        # de chaîne vide ne lève aucune erreur, elle ne fait simplement rien.
        self._faites.config(state="normal")
        self._faites.insert("1.0", f"{détail}\n", "faible")
        self._faites.insert("1.0", f"{ligne}\n")
        self._faites.tag_add(_tag_for(échantillons), "1.0", "1.end")
        if quest is not None:
            # « lien » porte le style et le curseur, commun à tous les noms ;
            # le tag numéroté porte le clic, propre à CETTE ligne : deux tags
            # qui se recouvrent, Tk applique les deux.
            self._compteur_liens += 1
            tag_lien = f"lien_{self._compteur_liens}"
            self._faites.tag_add("lien", f"1.{début_nom}", f"1.{fin_nom}")
            self._faites.tag_add(tag_lien, f"1.{début_nom}", f"1.{fin_nom}")
            self._faites.tag_bind(tag_lien, "<Button-1>", self._go_to_ranking(quest))
        self._faites.config(state="disabled")
        self._faites.see("1.0")

    def _add_split(self, quest_name: str, index: int, seconds: float) -> None:
        """Affiche le temps d'un objectif franchi.

        Marqué « objectif » et non simplement chronométré : ces temps ne
        quittent pas ce poste, contrairement aux mesures de quête, et le joueur
        doit pouvoir faire la différence en un coup d'œil. Voir `session.py`.
        """
        self._faites.config(state="normal")
        self._faites.insert(
            "1.0",
            f"{format_duration(seconds):>10}   objectif {index}   {quest_name}\n",
            "faible",
        )
        self._faites.config(state="disabled")
        self._faites.see("1.0")

    def _show_no_chain(self, name: str) -> None:
        """Explique une liste vide au lieu de la laisser muette.

        Constaté en jouant : la fenêtre affichait « Les fanatiques » en titre et
        une liste vide dessous. Le nom avait bien été lu, mais il ne s'était
        résolu en aucune quête connue, donc la chaîne était inconnue, donc il
        n'y avait pas de suite à montrer.

        Une liste vide et muette se lit comme « il n'y a rien après ». La vraie
        réponse est « je ne sais pas où tu es », ce qui est très différent et
        indique quoi regarder : le nom lu, et le référentiel.
        """
        self._liste.config(state="normal")
        self._liste.delete("1.0", "end")
        self._liste.insert(
            "1.0",
            f"« {name} » n'a pas été retrouvée au référentiel, "
            "donc la chaîne est inconnue et la suite ne peut pas être "
            "affichée.\n\n"
            "Ce n'est pas forcément une panne : les quêtes hors "
            "« Principales » ne sont pas mesurées, et le nom peut avoir "
            "été mal lu. L'onglet Zones montre ce qui est lu à l'instant.",
            "faible",
        )
        self._liste.config(state="disabled")

    def _show_upcoming(self, chain: int, position: int, references: Any) -> None:
        """Réaffiche la liste des quêtes à venir, avec leur score."""
        self._ask_current_reference(chain, position, references)
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

    def _ask_current_reference(self, chain: int, position: int, references: Any) -> None:
        """Demande, dans un fil, le meilleur temps connu de la quête en cours.

        Sur le même signal que `_show_upcoming`, « position » : c'est lui qui
        change exactement quand une quête vient d'être acceptée. Dans un fil,
        comme tout le reste du réseau : un serveur lent ne doit pas figer la
        fenêtre pendant qu'une quête vient de démarrer.
        """
        quest_id = QuestId(chain, position)

        def demander() -> None:
            reference = references.quest(quest_id) if references is not None else None
            self.publish("reference_en_cours", (quest_id, reference))

        threading.Thread(target=demander, daemon=True).start()

    def _show_current_reference(self, quest_id: QuestId, reference: Any) -> None:
        """Affiche le meilleur temps connu, s'il concerne toujours la quête en cours.

        ⚠️ La requête part dans un fil et peut répondre après que le joueur ait
        déjà avancé : sans ce contrôle, la réponse d'une quête abandonnée
        s'afficherait sous le nom d'une autre, silencieusement fausse.
        """
        moteur = self._engine
        if (
            moteur is None
            or moteur.timeline is None
            or (moteur.timeline.current_chain, moteur.timeline.current_position)
            != (quest_id.chain, quest_id.position)
        ):
            return
        self._record_en_cours.config(text=format_current_reference(reference))

    def _show_coverage(self, parts: tuple[str, str, str] | None) -> None:
        """Affiche « 0 verte, 11 orange, 3 913 jamais mesurées », ou son absence.

        L'absence se dit. Trois zéros à la place se liraient comme « personne
        n'a jamais rien mesuré », qui est une affirmation, et une fausse quand
        c'est seulement le serveur qui n'a pas répondu.
        """
        if parts is None:
            for morceau in self._couverture_parts:
                morceau.config(text="")
            # « ne l'a pas donnée » et non « n'a pas répondu ». Éprouvé le
            # 05/08/2026 : rubin.maxyull.fr répond parfaitement, mais rend 404
            # sur cette adresse, parce qu'il tourne encore sur une version
            # antérieure au point d'entrée. Annoncer une panne de réseau aurait
            # envoyé chercher l'erreur exactement du mauvais côté.
            self._couverture_etat.config(
                text="couverture inconnue : le serveur ne l'a pas donnée"
            )
            return
        for index, (morceau, texte) in enumerate(
            zip(self._couverture_parts, parts, strict=True)
        ):
            morceau.config(text=texte + (", " if index < len(parts) - 1 else ""))
        self._couverture_etat.config(text="")

    def _show_zone_reading(self, clé: str, zone: Rect, image: Any, lignes: Any) -> None:
        """Pose l'aperçu et les lignes d'une zone, depuis le fil de Tk.

        Le fil de lecture n'a fait que capturer et reconnaître ; c'est ici, et
        seulement ici, qu'on touche aux composants.
        """
        if image is not None:
            self._show_preview(clé, image, zone)
        self._set_reading(clé, tuple(lignes))

    def _show_link(self, health: Any) -> None:
        """Le témoin de connexion : un mot, une adresse, une couleur.

        Les trois états sont distincts **exprès**, parce qu'ils appellent trois
        gestes différents. « Aucun serveur » n'est pas une panne, c'est un
        lancement sans `--envoyer` ; « injoignable » veut dire qu'il y a quelque
        chose à réparer.

        ⚠️ Ce témoin regarde `/sante`, et rien d'autre. Un serveur qui répond
        parfaitement mais tourne sur une version antérieure, sans le point
        d'entrée d'un compteur, reste **connecté** : c'est le compteur qui dit
        qu'il n'a pas eu sa réponse, pas la connexion qui est en cause. Le cas
        est réel, il date du 05/08/2026.
        """
        texte, balise = format_link(self._server, health)
        self._lien.config(text=f"serveur : {texte}", foreground=COLORS[balise])

    def publish(self, genre: str, charge: Any) -> None:
        """Dépose un message pour l'affichage. Appelable depuis n'importe quel fil."""
        self._messages.put((genre, charge))

    def link_discord(self) -> None:
        """Ouvre le rattachement du compte Discord dans le navigateur.

        Le rattachement est **facultatif et sans effet sur la mesure**. Un
        joueur qui n'en veut pas alimente les médianes exactement comme les
        autres ; il n'apparaît simplement pas nommé.

        L'identifiant anonyme voyage signé dans le paramètre `state`, que le
        serveur vérifie au retour : sans cette signature, n'importe qui
        pourrait rattacher son compte Discord à l'identifiant d'un autre.

        Rien n'est ouvert avant d'avoir demandé au serveur s'il sait le faire.
        Envoyer quelqu'un vers une page d'erreur qu'il ne peut pas comprendre
        serait pire que de lui dire tout de suite que ce n'est pas gréé.
        """
        if not self._server:
            self._discord_etat.config(
                text="aucun serveur indiqué : relancez avec --envoyer pour vous connecter"
            )
            return
        try:
            identity = PlayerIdentity.load_or_create(self._home / "identite")
        except OSError as erreur:  # pragma: pas de couverture
            self._discord_etat.config(text=f"identifiant illisible : {erreur}")
            return

        adresse = f"{self._server.rstrip('/')}/v1/discord/connexion?player={identity.value}"
        try:
            réponse = requests.get(adresse, timeout=5, allow_redirects=False)
        except requests.RequestException as erreur:
            self._discord_etat.config(text=f"serveur injoignable : {erreur}")
            return
        if réponse.status_code == 503:
            # L'état d'aujourd'hui : les routes existent, les identifiants
            # Discord ne sont pas posés. Le dire tel quel plutôt que d'ouvrir
            # un navigateur sur une erreur.
            self._discord_etat.config(
                text="le serveur n'a pas encore ses identifiants Discord, "
                "le rattachement n'est pas disponible"
            )
            return
        if réponse.status_code >= 400:
            self._discord_etat.config(text=f"le serveur a refusé ({réponse.status_code})")
            return

        webbrowser.open(adresse)
        self._discord_etat.config(
            text="autorisez Rubin dans votre navigateur, puis revenez ici"
        )

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
