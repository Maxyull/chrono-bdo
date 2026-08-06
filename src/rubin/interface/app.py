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
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Final

import requests

from .. import __version__
from ..autoupdate import download_installer, launch_installer
from ..capture import (
    Rect,
    ScreenCapture,
    banner_region,
    choice_region,
    find_game_window,
    tracker_region,
)
from ..history import personal_best
from ..notes import load_notes, save_note
from ..placement import choose, conflicts
from ..protocol import PlayerIdentity
from ..reference import Catalog, Chain, Quest, QuestId
from ..references import RANKING_LIMIT, RankedQuest, ReferenceClient
from ..settings import LANGUAGES, LIMITS, WindowSize, load, save
from ..timing import Quality
from ..upcoming import upcoming
from ..updates import UpdateStatus, check_for_update
from .autozone import search as search_banner_zone
from .help import EXAMPLES, HelpWindow
from .picker import ZonePicker, png_data
from .presentation import (
    AUTRES_CHAIN_CATEGORY,
    CLASS_CHAIN_CATEGORY,
    COVERAGE_TAGS,
    DEMO_BANNER,
    LOCKED_WHILE_MEASURING,
    QUEST_LIST_LIMIT,
    SEARCH_MIN_LENGTH,
    ListedQuest,
    ZoneState,
    chain_sections,
    demo_active,
    demo_ranking,
    describe_conflict,
    describe_reading,
    describe_zone,
    format_category_header,
    format_chain_header,
    format_coverage,
    format_current_reference,
    format_duration,
    format_gap,
    format_link,
    format_listed_quest,
    format_measure_line,
    format_note_placeholder,
    format_other_quests,
    format_packet_header,
    format_personal_best,
    format_quest_times,
    format_ranking,
    format_reference,
    format_running,
    format_search_result,
    format_upcoming_line,
    format_watching,
    group_chains_by_category,
    group_chains_by_game_order,
    lock_label,
    main_quest_total,
    other_quest_total,
    quest_list_cap_warning,
    ranking_message,
    running_seconds,
    samples_by_quest,
    search_quests,
    zone_lock_reason,
)
from .session import MeasuringSession
from .theme import COLORS, FAMILY, MONO_FAMILY, confidence_score
from .theme import apply as apply_theme
from .tooltip import Tooltip

#: Taille de la fenêtre. Assez large pour un nom de quête complet, assez étroite
#: pour tenir à côté du panneau de suivi sans mordre dessus.
#:
#: 700 de haut, la valeur d'origine, coupait le bas des onglets Session et
#: Classement même une fois le défilement ajouté (`_scrollable`) : la
#: molette rattrape ce qui dépasse, mais Maxime voyait trop peu d'un coup
#: sans faire défiler. Signalé le 06/08/2026. 820 reste raisonnable à côté
#: du jeu sur un écran 1080p ; `choose` refuse de toute façon toute position
#: qui recouvrirait une zone lue, quelle que soit la taille demandée ici.
WINDOW_SIZE: Final = (470, 820)

#: Période de rafraîchissement de l'affichage, en millisecondes. Huit fois par
#: seconde suffisent : c'est déjà la cadence de capture, et l'œil n'en demande
#: pas plus sur du texte.
REFRESH_MS: Final = 125

#: Intervalle entre deux vérifications de version, en millisecondes.
#:
#: `_ask_server` en vérifie déjà une au lancement et après chaque quête
#: mesurée, mais un joueur qui laisse Rubin ouvert sans jouer, ou en pleine
#: quête très longue, ne verrait sinon rien tant qu'il ne relance pas. Un vrai
#: push (WebSocket, connexion permanente) réglerait ça aussi, mais pour un
#: événement aussi rare qu'une nouvelle version, il ferait porter au serveur
#: une connexion ouverte par joueur pour un gain qu'un sondage périodique
#: donne déjà. Choisi avec Maxime le 06/08/2026. Cinq minutes : assez
#: réactif pour ne pas rater une soirée de jeu, assez rare pour ne peser sur
#: rien.
UPDATE_POLL_MS: Final = 5 * 60 * 1000

#: Le Discord du projet, demandé par Maxime le 06/08/2026.
DISCORD_URL: Final = "https://discord.gg/qCuvN2Zna7"

#: L'iid Tk de la catégorie « Renaissance et Éveil », fixe et distinct de
#: tout `str(chain.number)` : un numéro de chaîne est toujours numérique,
#: cet iid ne l'est jamais, les deux espaces ne se recouvrent donc jamais.
_CLASS_CATEGORY_IID: Final = "categorie:classes"

#: Même principe que `_CLASS_CATEGORY_IID`, pour la catégorie des chaînes
#: sans région confirmée. Voir `group_chains_by_game_order`.
_AUTRES_CATEGORY_IID: Final = "categorie:autres"

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

        #: Les 3 924 quêtes principales, groupées par chaîne, telles que
        #: `chain_sections` les a rendues la dernière fois. Vide tant que le
        #: serveur n'a rien dit : `_show_chains` la remplit, `_chains_open` la
        #: lit pour peupler une chaîne à son ouverture, jamais avant. Indexée
        #: par `str(chain.number)`, l'identifiant employé comme iid Tk.
        self._chain_sections: dict[str, tuple[Chain, tuple[ListedQuest, ...]]] = {}
        #: Le classement brut à l'origine de la table ci-dessus, gardé pour ne
        #: reconstruire l'arbre que si le serveur a vraiment dit autre chose :
        #: sinon, chaque quête finie replierait les chaînes que le joueur
        #: vient d'ouvrir, `_ask_server` étant rappelée après chacune.
        self._chains_ranked: tuple[RankedQuest, ...] | None = None
        #: Les chaînes déjà peuplées dans l'arbre Tk, pour ne le faire qu'une
        #: fois chacune : voir l'en-tête de `ListedQuest`.
        self._chains_loaded: set[str] = set()
        #: La quête derrière chaque ligne cliquable de l'arbre, par identifiant
        #: Tk. Même raison que `_compteur_liens` : une ligne de l'arbre est du
        #: texte, retrouver la quête qu'elle désigne demande cette table.
        self._chain_quest_for_item: dict[str, Quest] = {}
        self._compteur_chain_liens = 0
        #: Les chaînes de classe (Renaissance/Éveil), regroupées sous une
        #: catégorie à part en tête d'arbre. Indexée par iid de catégorie,
        #: valeur = les iid de chaînes qu'il faut poser à son ouverture.
        #: Demandé par Maxime le 06/08/2026, voir `is_class_chain`.
        self._category_members: dict[str, tuple[str, ...]] = {}

        #: Les notes du joueur, chargées une fois au démarrage et tenues à
        #: jour à chaque écriture par `_save_note` : voir `notes.py`. Purement
        #: locales, jamais envoyées au serveur.
        self._notes = load_notes(self._home)
        #: La quête à laquelle s'applique le champ de note affiché, ou `None`
        #: tant qu'aucune quête n'est en cours. Même garde-fou de fraîcheur
        #: que `_show_current_reference` : voir `_save_note`.
        self._note_quest_id: QuestId | None = None

        #: Le message d'une panne qui vient d'arrêter la session, en attente
        #: d'être montré. `None` tant qu'aucune panne n'a eu lieu, ou une fois
        #: la question posée : voir `_ask_resume_after_crash`. Distingue une
        #: panne d'un clic volontaire sur « Arrêter », qui ne publie jamais
        #: « panne ».
        self._crash_message: str | None = None

        #: La dernière réponse connue sur les versions, `None` tant que
        #: `check_for_update` n'a rien dit ou que tout est à jour. Gardée pour
        #: que `_install_update` sache quelle version télécharger sans la
        #: redemander : voir `_show_update_status`.
        self._update_status: UpdateStatus | None = None

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
        self._poll_for_update()
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
        # Le numéro de version, demandé par Maxime le 06/08/2026 : savoir
        # d'un coup d'œil quelle version tourne, et si une plus récente
        # existe, sans avoir à chercher dans les onglets. Mis à jour par
        # `_show_update_status`, la même donnée que `_maj_bouton` plus bas.
        self._rubin_titre = ttk.Label(
            cadre, text=f"RUBIN v{__version__}", style="Section.TLabel"
        )
        self._rubin_titre.pack(anchor="w")
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
        # Le record PERSONNEL sur cette même quête, juste en dessous : une
        # étiquette à part et non la même ligne, parce que les deux répondent à
        # des questions différentes, « le meilleur de tout le monde » et « mon
        # meilleur à moi », et qu'un joueur doit pouvoir les distinguer d'un coup
        # d'œil. Voir `format_personal_best`, purement local.
        self._record_personnel = ttk.Label(cadre, text="", style="Faible.TLabel")
        self._record_personnel.pack(anchor="w", pady=(0, 0))
        # Le témoin de connexion, sous le chronomètre : visible depuis n'importe
        # quel onglet, parce que la question « est-ce que je suis relié ? » se
        # pose de partout. Un mot **et** une couleur, jamais la couleur seule.
        self._lien = ttk.Label(
            cadre, text="serveur : vérification…", style="Faible.TLabel",
            wraplength=430, justify="left",
        )
        self._lien.pack(anchor="w", pady=(4, 0))

        # L'adresse elle-même n'est plus écrite en toutes lettres dans
        # `_lien` (demandé par Maxime le 06/08/2026). Ce lien-ci n'ouvre plus
        # une page à lire, mais l'onglet Envois : montrer les paquets réels,
        # poids et contenu, plutôt qu'une description de ce qu'ils
        # contiennent. Revu le 06/08/2026, voir `_build_envois`.
        self._voir_envois = ttk.Label(
            cadre, text="voir ce qui est envoyé", foreground=COLORS["accent"],
            background=COLORS["fond"], font=(FAMILY, 9), cursor="hand2",
        )
        self._voir_envois.pack(anchor="w")
        self._voir_envois.bind("<Button-1>", self._show_envois_tab)

        # Le Discord du projet. Demandé par Maxime le 06/08/2026 : un lien
        # depuis la fenêtre elle-même, pas seulement depuis le dépôt.
        self._discord_lien = ttk.Label(
            cadre, text="rejoindre le Discord", foreground=COLORS["accent"],
            background=COLORS["fond"], font=(FAMILY, 9), cursor="hand2",
        )
        self._discord_lien.pack(anchor="w")
        self._discord_lien.bind(
            "<Button-1>", lambda _e: webbrowser.open(DISCORD_URL)
        )

        # Le bouton de mise à jour, invisible tant qu'aucune n'est connue.
        # Demandé par Maxime le 06/08/2026 : un clic doit suffire, contre le
        # lien qu'il fallait ouvrir à la main jusqu'ici. Voir `autoupdate.py`
        # et `_check_for_update`.
        self._maj_bouton = ttk.Button(
            cadre, text="", command=self._install_update,
        )

    def _build_tabs(self) -> None:
        carnet = ttk.Notebook(self.root)
        carnet.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        # Retenu : l'onglet Zones se verrouille entier pendant la mesure, et il
        # faut pouvoir le désigner plus tard. Voir `_lock_zone_controls`.
        self._carnet = carnet

        self._session = ttk.Frame(carnet)
        self._classement = ttk.Frame(carnet)
        self._zones = ttk.Frame(carnet)
        self._envois = ttk.Frame(carnet)
        self._reglages = ttk.Frame(carnet)
        carnet.add(self._session, text="Session")
        carnet.add(self._classement, text="Classement")
        carnet.add(self._zones, text="Zones")
        carnet.add(self._envois, text="Envois")
        carnet.add(self._reglages, text="Réglages")

        # L'infobulle du carnet ne parle QUE de l'onglet Zones : c'est un seul
        # composant qui en porte quatre, et une explication de verrou apparue
        # au survol de « Réglages » ferait croire qu'il est verrouillé aussi.
        self._carnet_tip = Tooltip(carnet, when=self._over_zones_tab)

        self._build_session()
        self._build_ranking()
        self._build_zones()
        self._build_envois()
        self._build_settings()

        # Entrer dans l'onglet des zones déclenche la lecture. Voir
        # `_tab_changed` : elle a lieu dans un fil, parce qu'elle coûte une
        # seconde et demie et figerait la fenêtre autrement.
        self._carnet = carnet
        carnet.bind("<<NotebookTabChanged>>", self._tab_changed)

    def _build_session(self) -> None:
        """L'onglet Session : démarrer, suivre, voir ce qui vient.

        ⚠️ **L'onglet défile**, depuis le 5 août 2026 au soir, même raison que
        `_build_ranking` : « QUÊTES FAITES » et « LES QUÊTES QUI SUIVENT »
        s'étoffent avec la partie, et une session déjà bien avancée dépassait
        la hauteur de la fenêtre sans que rien ne le dise. La légende des
        couleurs et la couverture, tout en bas, étaient **présentes et
        invisibles** : vu chez Maxime, qui les croyait absentes.
        """
        dedans = self._scrollable(self._session)
        commandes = ttk.Frame(dedans)
        commandes.pack(fill="x", padx=12, pady=(12, 6))
        self._bouton = ttk.Button(
            commandes,
            text="Je commence mes quêtes",
            style="Accent.TButton",
            command=self.toggle_session,
        )
        self._bouton.pack(side="left")

        self._etat = ttk.Label(
            dedans, text="", style="Faible.TLabel", anchor="w", wraplength=400
        )
        self._etat.pack(fill="x", padx=12, pady=(0, 2))

        # Ce que la surveillance voit, rafraîchi à chaque tour de la boucle de
        # mesure. Juste sous l'état, parce que les deux se lisent ensemble :
        # « mesure en cours » dit ce que le logiciel CROIT faire, cette
        # ligne-ci dit ce qu'il voit RÉELLEMENT. Le 5 août 2026, les deux se
        # contredisaient pendant quinze minutes et rien ne le montrait.
        self._surveillance = ttk.Label(
            dedans, text="", style="Faible.TLabel", anchor="w", wraplength=400
        )
        self._surveillance.pack(fill="x", padx=12, pady=(0, 6))

        # La note de la quête en cours : le monstre à tuer, l'instance, le
        # choix pris à un carrefour, un mot ou un nombre à noter dans le chat.
        # Demandé par Maxime le 05/08/2026 au soir. Purement locale, voir
        # `notes.py` ; le champ n'est activé que le temps qu'une quête est en
        # cours, sur le même garde-fou de fraîcheur que le record personnel.
        ttk.Label(
            dedans, text="NOTE DE QUÊTE", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(2, 3))
        self._note_etat = ttk.Label(
            dedans, text=format_note_placeholder(has_note=False),
            style="Faible.TLabel", anchor="w", justify="left", wraplength=400,
        )
        self._note_etat.pack(fill="x", padx=12)
        ligne_note = ttk.Frame(dedans)
        ligne_note.pack(fill="x", padx=12, pady=(4, 10))
        self._note_texte = tk.StringVar()
        self._note_champ = ttk.Entry(
            ligne_note, textvariable=self._note_texte, state="disabled"
        )
        self._note_champ.pack(side="left", fill="x", expand=True)
        self._note_champ.bind("<Return>", self._save_note)
        self._note_bouton = ttk.Button(
            ligne_note, text="Enregistrer", command=self._save_note, state="disabled"
        )
        self._note_bouton.pack(side="left", padx=(6, 0))

        ttk.Label(
            dedans, text="QUÊTES FAITES", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(2, 3))
        self._faites = self._text_box(dedans, height=6)
        self._faites.pack(fill="both", expand=True, padx=12)
        # Configuré une seule fois, réutilisé par chaque nom cliquable. Après
        # les tags de couleur posés par `_text_box` : à recouvrement, Tk donne
        # priorité au tag configuré le plus récemment, donc la couleur du lien
        # gagne sur la couleur de confiance pour la portion du nom.
        self._faites.tag_configure("lien", foreground=COLORS["accent"], underline=True)
        self._faites.tag_bind("lien", "<Enter>", lambda _e: self._faites.config(cursor="hand2"))
        self._faites.tag_bind("lien", "<Leave>", lambda _e: self._faites.config(cursor=""))

        ttk.Label(
            dedans, text="LES QUÊTES QUI SUIVENT", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(8, 3))

        self._liste = self._text_box(dedans, height=7)
        self._liste.pack(fill="both", expand=True, padx=12)

        legende = ttk.Frame(dedans)
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

        self._compteurs = ttk.Label(dedans, text="", style="Faible.TLabel", anchor="w")
        self._compteurs.pack(fill="x", padx=12, pady=(0, 2))

        # La couverture des 3 924 quêtes principales, juste sous la légende qui
        # dit ce que chaque couleur veut dire.
        #
        # Trois étiquettes et non une seule : une `ttk.Label` n'a qu'une couleur
        # de texte, et ici la couleur EST l'information, celle qui rattache
        # chaque compte à sa pastille. Le séparateur voyage dans le texte du
        # morceau qui précède, sinon des virgules orphelines resteraient à
        # l'écran tant que le serveur n'a pas répondu.
        self._couverture = ttk.Frame(dedans)
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
            dedans, text="", style="Faible.TLabel", anchor="w", wraplength=420
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

        # « Toutes les quêtes par chaîne » avant « les plus rapides » :
        # ordre inversé le 06/08/2026 sur demande de Maxime. La liste par
        # chaîne est déjà utile avec une seule mesure ; le classement, lui,
        # exige trois mesures par quête et reste souvent vide tant que la
        # base est jeune, voir la note « en construction » plus bas.
        self._build_chains(dedans)

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
        ttk.Label(
            dedans,
            text=(
                "⚠ En construction : trop peu de quêtes ont encore leurs trois\n"
                "mesures. Cette liste s'étoffera avec la base."
            ),
            style="Alerte.TLabel", anchor="w", justify="left",
        ).pack(fill="x", padx=12, pady=(2, 0))

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

    def _build_chains(self, dedans: ttk.Frame) -> None:
        """Toutes les quêtes principales, repliées par chaîne, une pastille au bout.

        Demandée par Maxime le 05/08/2026, revue le 06/08/2026 : le premier
        jet groupait par lettre du nom, ce qui n'est PAS ce que montre le
        journal du jeu. Celui-ci liste des chaînes, chacune avec son propre
        décompte, du type « [Abyss One] Magnus : 0/104 » : c'est cette forme
        qui est reprise ici, voir `format_chain_header`. Sous « LES QUÊTES LES
        PLUS RAPIDES », dans le même onglet et le même `dedans` défilant : les
        deux répondent à la même question de consultation, et ouvrir un
        onglet à part pour celle-ci aurait touché à la taille de la fenêtre et
        à la logique de verrouillage des onglets, pour rien de plus qu'une
        troisième façon de lire les mêmes temps.

        ⚠️ **Peuplée par chaîne, jamais d'un coup.** Un `ttk.Treeview` qui
        recevrait 3 924 lignes de quête à la construction referait l'erreur
        que ce projet a déjà commise ailleurs, un coût certain payé pour un
        bénéfice hypothétique : personne n'aura peut-être jamais déplié la
        moitié de ces 349 chaînes. Seules les chaînes elles-mêmes sont posées
        ici ; le contenu de chacune arrive à l'ouverture, voir `_chains_open`.
        """
        ttk.Label(
            dedans,
            text="TOUTES LES QUÊTES, PAR CHAÎNE",
            style="Section.TLabel",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))
        ttk.Label(
            dedans,
            text=(
                "Dépliez une chaîne pour voir ses quêtes, chacune avec sa\n"
                "pastille de couverture. Sert à repérer ce qui manque encore."
            ),
            style="Faible.TLabel", anchor="w", justify="left",
        ).pack(fill="x", padx=12)

        self._chains_etat = ttk.Label(
            dedans, text="arbre : demandé au serveur…",
            style="Faible.TLabel", anchor="w", justify="left", wraplength=400,
        )
        self._chains_etat.pack(fill="x", padx=12, pady=(2, 0))
        self._chains_avertissement = ttk.Label(
            dedans, text="", style="Alerte.TLabel", anchor="w",
            justify="left", wraplength=400,
        )
        self._chains_avertissement.pack(fill="x", padx=12)

        cadre = ttk.Frame(dedans)
        cadre.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        # `show="tree"` : pas de colonne supplémentaire ni d'en-tête, une
        # seule colonne d'arbre comme le veut cette liste.
        self._chains = ttk.Treeview(cadre, show="tree", height=14, selectmode="none")
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self._chains.yview)
        self._chains.configure(yscrollcommand=barre.set)
        self._chains.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")
        # Les mêmes trois balises que partout ailleurs dans ce projet : voir
        # `_tag_for` et la légende de l'onglet Session. Aucune couleur neuve.
        for balise in COVERAGE_TAGS:
            self._chains.tag_configure(balise, foreground=COLORS[balise])
        self._chains.bind("<<TreeviewOpen>>", self._chains_open)

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

    def _show_envois_tab(self, _event: object = None) -> None:
        self._carnet.select(self._envois)  # type: ignore[no-untyped-call]

    def _build_envois(self) -> None:
        """L'onglet Envois : les paquets réellement envoyés au serveur, en clair.

        Demandé par Maxime le 06/08/2026, à la place d'un lien vers la
        politique de confidentialité : montrer les paquets eux-mêmes, poids
        et contenu, plutôt qu'en décrire la teneur. Un texte peut mentir sans
        que personne ne le remarque ; le contenu réellement posté sur le fil
        ne peut pas.

        Ne montre que les envois **de cette session**, jamais reconstruits ni
        relus depuis le disque : la fenêtre affiche ce qu'elle fait, pas un
        historique. Vide tant qu'aucune mesure n'est encore partie.
        """
        dedans = self._scrollable(self._envois)
        ttk.Label(
            dedans, text="CE QUI EST ENVOYÉ", style="Section.TLabel", anchor="w"
        ).pack(fill="x", padx=12, pady=(12, 2))
        ttk.Label(
            dedans,
            text=(
                "Chaque paquet réellement posté au serveur pendant cette\n"
                "session, poids et contenu. Rien d'autre ne part jamais."
            ),
            style="Faible.TLabel", anchor="w", justify="left",
        ).pack(fill="x", padx=12)
        self._envois_etat = ttk.Label(
            dedans, text="rien envoyé pour l'instant",
            style="Faible.TLabel", anchor="w",
        )
        self._envois_etat.pack(fill="x", padx=12, pady=(4, 0))
        self._envois_texte = self._text_box(dedans, height=16, mono=True)
        self._envois_texte.pack(fill="both", expand=True, padx=12, pady=(4, 12))

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

        Appelée au lancement, puis à nouveau après chaque quête mesurée, voir
        `_finish_measure`.

        ⚠️ Ce commentaire a longtemps affirmé l'inverse, « une seule fois par
        lancement, rien ne peut bouger pendant la session, puisque les mesures
        ne partent qu'à son arrêt ». C'était vrai avant #59, qui écrit et
        envoie chaque mesure au fil de l'eau : depuis, ça bouge à chaque quête
        finie, et les compteurs restaient figés sur l'état du lancement pendant
        qu'une vraie session tournait à côté. Vu en jouant le 5 août 2026 au
        soir : la couverture affichait toujours 21 quêtes peu mesurées après
        deux mesures envoyées avec succès, quand le serveur, lui, en comptait
        déjà 28.

        L'ordre n'est pas indifférent : le témoin de connexion part en premier,
        parce que c'est lui qui explique les silences des deux autres.
        """
        if self._catalog is None:
            self._couverture_etat.config(
                text="couverture inconnue : le référentiel n'est pas chargé"
            )
            self._chains_etat.config(
                text="arbre indisponible : le référentiel n'est pas chargé"
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
            if self._catalog is not None:
                self._chains_etat.config(
                    text="arbre indisponible : aucun serveur, relancez avec --envoyer"
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
                # Une seule requête en masse, jamais une par quête : voir
                # l'en-tête de `ListedQuest`. `min_samples=1` et non le
                # défaut à trois : l'arbre veut TOUTE quête mesurée, même une
                # seule fois, la nuance « peu sûr » se lisant déjà sur
                # `format_listed_quest`.
                self.publish(
                    "chaines",
                    self._references.fastest_quests(QUEST_LIST_LIMIT, min_samples=1),
                )

        threading.Thread(target=demander, daemon=True).start()

    def _poll_for_update(self) -> None:
        """Revérifie une mise à jour toutes les `UPDATE_POLL_MS`, sans s'arrêter.

        Se replanifie elle-même à chaque passage : c'est ce qui la distingue
        de `_ask_server`, rappelée seulement au lancement et après chaque
        quête mesurée. Un joueur qui laisse Rubin ouvert sans jouer verrait
        sinon passer une release entière sans le savoir.
        """
        server = self._server

        def demander() -> None:
            self.publish("maj", check_for_update(server))

        threading.Thread(target=demander, daemon=True).start()
        self.root.after(UPDATE_POLL_MS, self._poll_for_update)

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

    def _show_chains(self, ranked: tuple[RankedQuest, ...] | None) -> None:
        """Reçoit le classement brut et pose les chaînes de l'arbre, jamais leur contenu.

        `ranked` vient de `ReferenceClient.fastest_quests(QUEST_LIST_LIMIT,
        min_samples=1)`, la même méthode que « LES QUÊTES LES PLUS RAPIDES »
        avec un seuil et une limite différents : voir l'en-tête de
        `_ask_server`. `None` veut dire que le serveur n'a rien répondu, une
        absence qui ne se remplace jamais par un arbre vide : voir
        `ranking_message` pour la même règle appliquée au classement voisin.

        ⚠️ **Ne reconstruit l'arbre que si `ranked` a changé.** `_ask_server`
        est rappelée après chaque quête finie, et `ReferenceClient` garde ses
        réponses en mémoire pour la durée de la session : la plupart des
        rappels rendront donc exactement le même classement. Le reconstruire
        quand même replierait sous les doigts du joueur la chaîne qu'il vient
        d'ouvrir, pour rien.
        """
        if self._catalog is None:
            self._chains_etat.config(text="arbre indisponible : le référentiel n'est pas chargé")
            self._chains_avertissement.config(text="")
            return
        if ranked is None:
            self._chains_etat.config(text="arbre indisponible : le serveur ne l'a pas donné")
            self._chains_avertissement.config(text="")
            return
        self._chains_etat.config(text="")
        self._chains_avertissement.config(text=quest_list_cap_warning(ranked) or "")
        if ranked == self._chains_ranked:
            return
        self._chains_ranked = ranked
        sections = chain_sections(
            self._catalog, self._settings.language, samples_by_quest(ranked)
        )
        classes, scénario = group_chains_by_category(sections)
        ordonnées, autres = group_chains_by_game_order(scénario)
        self._chain_sections = {
            str(chain.number): (chain, entrées) for chain, entrées in sections
        }
        self._chains_loaded.clear()
        self._chain_quest_for_item.clear()
        self._chains.delete(*self._chains.get_children())

        # Les chaînes de classe d'abord, repliées sous une seule catégorie :
        # sur 349 chaînes, 64 sont des Renaissance/Éveil, une paire par
        # classe jouable, et mélangées au reste elles noient les chaînes de
        # scénario sous « [R » et « [É ». Demandé par Maxime le 06/08/2026.
        # Voir `is_class_chain`.
        self._category_members = {}
        if classes:
            nœud = self._chains.insert(
                "", "end", iid=_CLASS_CATEGORY_IID,
                text=format_category_header(CLASS_CHAIN_CATEGORY, classes), open=False,
            )
            self._chains.insert(nœud, "end", text="")
            self._category_members[_CLASS_CATEGORY_IID] = tuple(
                str(chain.number) for chain, _entrées in classes
            )

        # Puis les chaînes de scénario dans l'ordre réel du jeu, relevé en
        # observant l'écran de Maxime le 06/08/2026. Voir
        # `group_chains_by_game_order` : ce n'est ni un tri alphabétique ni
        # un ordre inventé, c'est ce que montre l'onglet « Principales ».
        for chain, entrées in ordonnées:
            self._insert_chain_node("", chain, entrées)

        # Et enfin les chaînes dont on n'a pas pu confirmer la place dans cet
        # ordre (aucune région connue, ou une région jamais vue en jeu). Ce
        # sont de vraies quêtes, pas des chaînes écartées : les rassembler à
        # part plutôt que de deviner leur position, sur demande explicite de
        # Maxime le 06/08/2026.
        if autres:
            nœud = self._chains.insert(
                "", "end", iid=_AUTRES_CATEGORY_IID,
                text=format_category_header(AUTRES_CHAIN_CATEGORY, autres), open=False,
            )
            self._chains.insert(nœud, "end", text="")
            self._category_members[_AUTRES_CATEGORY_IID] = tuple(
                str(chain.number) for chain, _entrées in autres
            )

    def _insert_chain_node(
        self, parent: str, chain: Chain, entrées: tuple[ListedQuest, ...]
    ) -> None:
        """Pose une chaîne repliée, avec son enfant vide pour la flèche de dépliage.

        `parent` est `""` pour une chaîne de scénario, posée directement à la
        racine de l'arbre, ou l'iid de la catégorie « Renaissance et Éveil »
        pour une chaîne de classe : la même fonction sert aux deux niveaux,
        voir `_show_chains`. `_chains_open` remplace l'enfant vide par le vrai
        contenu à l'ouverture, jamais avant.
        """
        nœud = self._chains.insert(
            parent, "end", iid=str(chain.number),
            text=format_chain_header(chain, entrées), open=False,
        )
        self._chains.insert(nœud, "end", text="")

    def _chains_open(self, _event: object = None) -> None:
        """Peuple une chaîne ou une catégorie de l'arbre à son ouverture, jamais avant.

        C'est tout l'intérêt de l'arbre lazy : voir l'en-tête de
        `_build_chains`. `<<TreeviewOpen>>` place le nœud ouvert au focus
        avant de lever l'événement, ce qui évite d'avoir à le retrouver
        autrement qu'en le demandant à Tk.
        """
        iid = self._chains.focus()
        if iid in self._chains_loaded:
            return
        if iid in self._category_members:
            self._chains.delete(*self._chains.get_children(iid))
            for membre in self._category_members[iid]:
                chain, entrées = self._chain_sections[membre]
                self._insert_chain_node(iid, chain, entrées)
            self._chains_loaded.add(iid)
            return
        if iid not in self._chain_sections:
            return
        _chain, entrées = self._chain_sections[iid]
        self._chains.delete(*self._chains.get_children(iid))
        for entrée in entrées:
            self._compteur_chain_liens += 1
            tag_lien = f"chaine_lien_{self._compteur_chain_liens}"
            enfant = self._chains.insert(
                iid, "end",
                text=format_listed_quest(entrée),
                tags=(_tag_for(entrée.samples), tag_lien),
            )
            self._chain_quest_for_item[enfant] = entrée.quest
            # Même geste que le nom cliquable de « QUÊTES FAITES » : direction
            # la fiche de recherche individuelle. Voir `_go_to_ranking`.
            self._chains.tag_bind(tag_lien, "<Button-1>", self._go_to_ranking(entrée.quest))
        self._chains_loaded.add(iid)
        self._chains_loaded.add(iid)

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
        elif genre == "panne":
            # Retenu ici, jamais montré tout de suite : « panne » arrive
            # avant « demarre » à `False` dans le même passage de `_run`
            # (voir sa docstring), et la question ne doit se poser qu'une
            # fois `_set_running` revenu à l'état arrêté, sans quoi une
            # reprise immédiate croirait la session encore en cours.
            self._crash_message = str(charge)
        elif genre == "surveillance":
            self._surveillance.config(text=format_watching(charge))
        elif genre == "progres":
            self._show_progress(charge)
        elif genre == "mesure":
            self._add_measure(*charge)
        elif genre == "mesure_reference":
            self._finish_measure(*charge)
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
        elif genre == "maj":
            self._show_update_status(charge)
        elif genre == "maj_echouee":
            self._show_update_failed()
        elif genre == "maj_lancee":
            self._show_update_launched()
        elif genre == "paquet":
            self._show_packet(*charge)
        elif genre == "classement":
            self._ranking = charge
            self._refresh_ranking()
        elif genre == "chaines":
            self._show_chains(charge)
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
            # Jamais de mise à jour pendant une session : voir l'en-tête de
            # `_show_update_status`.
            self._maj_bouton.pack_forget()
        else:
            self._titre.config(text="En attente du jeu")
            self._sous_titre.config(text="lancez Black Desert, puis jouez")
            self._surveillance.config(text="")
            self._record_en_cours.config(text="")
            self._record_personnel.config(text="")
            self._note_quest_id = None
            self._note_texte.set("")
            self._note_etat.config(text=format_note_placeholder(has_note=False))
            self._note_champ.config(state="disabled")
            self._note_bouton.config(state="disabled")
            # Réaffiche le bouton de mise à jour si une version en attendait
            # une, cachée pendant la session qui vient de finir.
            self._show_update_status(self._update_status)
        self._lock_zone_controls(running)
        if not running and self._crash_message is not None:
            message, self._crash_message = self._crash_message, None
            self._ask_resume_after_crash(message)

    def _ask_resume_after_crash(self, message: str) -> None:
        """Demande si le joueur fait encore des quêtes, après un arrêt non voulu.

        Demandé par Maxime le 06/08/2026 : la session se désactivait parfois
        toute seule, et rien ne le signalait autrement qu'une ligne de texte
        vite recouverte (voir `_log_crash` dans `session.py`, qui garde la
        trace complète sur le disque pour comprendre la cause). Le bouton
        revenant à « Je commence mes quêtes » se voit à peine si le joueur a
        les yeux sur le jeu, pas sur Rubin.

        Une boîte de dialogue **bloquante** est le bon outil ici, alors que le
        reste de la fenêtre s'interdit tout ce qui gèle l'affichage : c'est la
        seule façon de garantir que le joueur la voit avant de continuer à
        jouer sans que rien ne se mesure. Elle n'apparaît jamais pour un clic
        volontaire sur « Arrêter », qui ne publie pas « panne ».
        """
        reprendre = messagebox.askyesno(
            "Rubin s'est arrêté",
            "Rubin a rencontré un problème et a arrêté la mesure :\n"
            f"{message}\n\n"
            "Faites-vous encore des quêtes ?",
        )
        if reprendre:
            self.toggle_session()

    def _show_update_status(self, status: UpdateStatus | None) -> None:
        """Affiche ou cache le bouton de mise à jour, selon ce que le serveur a dit.

        Demandé par Maxime le 06/08/2026 : un clic doit suffire, contre le
        lien à ouvrir soi-même dans `updates.py`. Le bouton reste caché tant
        qu'aucune mise à jour n'est connue : un bouton présent en permanence,
        même grisé, inviterait à cliquer pour voir ce qu'il fait.

        ⚠️ **Jamais pendant une session.** Remplacer les fichiers de Rubin
        pendant qu'un fil mesure serait risquer de perdre la fin d'une quête
        en cours pour un confort de mise à jour : voir `_set_running`, qui
        cache ce même bouton au démarrage et le laisse réapparaître à l'arrêt
        via ce message, republié par `_ask_server` après chaque quête finie.
        """
        self._update_status = status
        en_session = self._engine is not None and self._engine.running
        if status is None or not status.outdated or en_session:
            self._maj_bouton.pack_forget()
            self._rubin_titre.config(text=f"RUBIN v{__version__}")
            return
        self._maj_bouton.config(text=f"Mettre à jour ({status.latest})", state="normal")
        self._maj_bouton.pack(anchor="w", pady=(4, 0))
        self._rubin_titre.config(
            text=f"RUBIN v{__version__}   —   mise à jour disponible : v{status.latest}"
        )

    def _install_update(self) -> None:
        """Télécharge l'installateur et le lance, dans un fil.

        La vérification d'empreinte est dans `autoupdate.download_installer`,
        jamais ici : ce bouton ne fait qu'orchestrer, il ne décide rien seul
        de ce qui est sûr à exécuter.
        """
        status = self._update_status
        if status is None:
            return
        self._maj_bouton.config(text="téléchargement…", state="disabled")

        def télécharger() -> None:
            # ⚠️ Jamais `tempfile.TemporaryDirectory()` : son nettoyage
            # automatique tenterait de supprimer l'installateur dès que ce
            # fil rend la main, alors que `launch_installer` vient tout juste
            # de le lancer en arrière-plan. Windows verrouille un exécutable
            # tant qu'un processus tourne dessus, donc la suppression
            # échouerait, mais ce n'est pas une raison de compter sur l'échec
            # plutôt que de ne pas la tenter. Le fichier reste dans le dossier
            # temporaire du système, comme n'importe quel téléchargement.
            installateur = (
                Path(tempfile.gettempdir()) / f"rubin-installateur-{status.latest}.exe"
            )
            if not download_installer(status.latest, installateur):
                self.publish("maj_echouee", None)
                return
            launch_installer(installateur)
            self.publish("maj_lancee", None)

        threading.Thread(target=télécharger, daemon=True).start()

    def _show_update_failed(self) -> None:
        """Le téléchargement ou la vérification de l'installateur a échoué.

        Cause la plus probable, jamais nommée à tort : le réseau, ou une
        empreinte qui ne correspond pas (voir `download_installer`). Le
        bouton redevient cliquable, pour réessayer sans redémarrer Rubin.
        """
        status = self._update_status
        texte = f"Mettre à jour ({status.latest}) : échec, réessayer" if status else "échec"
        self._maj_bouton.config(text=texte, state="normal")

    def _show_update_launched(self) -> None:
        """L'installateur est lancé : Rubin continue de tourner, exprès.

        ⚠️ **Bogue réel corrigé le 06/08/2026**, trouvé par Maxime en cliquant
        pour de vrai : la première version fermait Rubin elle-même, 1,5 s
        après avoir lancé l'installateur (`self.root.after(1500,
        self.close)`). C'était exactement l'erreur à éviter. Le Gestionnaire
        de redémarrage de Windows (`CloseApplications=force`,
        `RestartApplications=yes` dans `rubin.iss`) ne relance que les
        applications **qu'il a lui-même fermées** : un Rubin déjà éteint de
        son propre chef au moment où l'installateur commence n'est plus rien
        à relancer pour lui. Résultat vécu : Rubin se fermait, l'installateur
        travaillait bien, mais rien ne rouvrait Rubin ensuite.

        La correction est de ne rien faire de plus ici : rester ouvert, pour
        que ce soit l'installateur qui ferme Rubin lui-même le moment venu,
        et le relance une fois fini.
        """
        self._maj_bouton.config(
            text="installation en cours, Rubin va se fermer puis se rouvrir…",
            state="disabled",
        )

    def _show_packet(self, at: str, size: int, endpoint: str, content: str) -> None:
        """Ajoute un paquet réellement envoyé à l'onglet Envois, en clair.

        Demandé par Maxime le 06/08/2026, à la place d'un lien vers la
        politique de confidentialité. Publié par
        `MeasuringSession._send_and_report`, juste avant chaque tentative
        d'envoi, réussie ou non.
        """
        self._envois_etat.config(text="")
        self._envois_texte.config(state="normal")
        self._envois_texte.insert("end", format_packet_header(at, size, endpoint) + "\n")
        self._envois_texte.insert("end", content + "\n\n")
        self._envois_texte.config(state="disabled")
        self._envois_texte.see("end")

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
        """Demande la référence de la quête dans un fil, avant d'en afficher la mesure.

        Appelée depuis `_handle`, donc depuis le fil de Tk, à chaque bandeau de
        fin lu. `ReferenceClient.quest` fait un GET synchrone quand la quête
        n'est pas déjà en cache, et un appel peut durer jusqu'à cinq secondes
        quand le serveur ne répond pas, voir `_ask_server`. La conserver ici
        aurait gelé la fenêtre entière à chaque première mesure d'une quête
        inconnue de la session, exactement le défaut que `_ask_server` et
        `_query_reference` évitent déjà en passant par un fil.

        Le fil ne touche à aucun composant, il dépose la référence obtenue dans
        la file : `_finish_measure`, appelée depuis `_handle` comme ici, termine
        l'affichage sur le fil de Tk une fois la réponse connue.
        """

        def demander() -> None:
            reference = self._references.quest(measure.quest_id) if self._references else None
            self.publish("mesure_reference", (measure, language, reference))

        threading.Thread(target=demander, daemon=True).start()

    def _finish_measure(self, measure: Any, language: str, reference: Any) -> None:
        """Ajoute une quête terminée en haut de la liste des faites.

        Le nom est cliquable, s'il a pu être résolu en une vraie quête : voir
        `_go_to_ranking`. Demandé par Maxime le 05/08/2026, une fois les
        mesures enfin revenues après la panne du jour.

        Suite de `_add_measure`, une fois sa référence connue : voir l'en-tête
        de `_add_measure` pour pourquoi cette partie ne peut pas s'exécuter
        avant, sur le fil qui a lu le bandeau.
        """
        quest = self._catalog.get(measure.quest_id, language) if self._catalog else None
        nom = quest.name if quest else str(measure.quest_id)
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
        # La couverture, le classement et le témoin de serveur datent tous du
        # lancement, sinon : voir l'en-tête de `_ask_server`, corrigée le
        # 5 août 2026 au soir sur le même défaut.
        self._ask_server()

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

        Le record personnel local est demandé dans ce MÊME fil, alors qu'il ne
        touche jamais le réseau. Deux raisons à ce choix : lire quelques
        dizaines de fichiers ne coûte rien de plus qu'attendre une réponse
        réseau, et surtout, les deux résultats arrivent ensemble sur une seule
        ligne « reference_en_cours », donc `_show_current_reference` n'a besoin
        que d'UN garde-fou de fraîcheur pour les deux affichages, jamais deux
        copies du même contrôle qui pourraient un jour diverger.
        """
        quest_id = QuestId(chain, position)

        def demander() -> None:
            reference = references.quest(quest_id) if references is not None else None
            record = personal_best(self._home, quest_id)
            self.publish("reference_en_cours", (quest_id, reference, record))

        threading.Thread(target=demander, daemon=True).start()

    def _show_current_reference(
        self, quest_id: QuestId, reference: Any, record: float | None
    ) -> None:
        """Affiche les deux références, si elles concernent toujours la quête en cours.

        ⚠️ La requête part dans un fil et peut répondre après que le joueur ait
        déjà avancé : sans ce contrôle, la réponse d'une quête abandonnée
        s'afficherait sous le nom d'une autre, silencieusement fausse. Le même
        contrôle protège le record personnel que le meilleur temps connu : les
        deux arrivent sur le même message, voir `_ask_current_reference`.
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
        self._record_personnel.config(text=format_personal_best(record))
        self._show_note(quest_id)

    def _show_note(self, quest_id: QuestId) -> None:
        """Ouvre le champ de note sur la quête en cours, avec sa note existante.

        Purement local (`self._notes`, chargé une fois au démarrage) : pas de
        fil à part, contrairement au reste de `_show_current_reference`, qui
        interroge le réseau.
        """
        self._note_quest_id = quest_id
        note = self._notes.get(quest_id, "")
        self._note_texte.set(note)
        self._note_etat.config(text=format_note_placeholder(has_note=bool(note)))
        self._note_champ.config(state="normal")
        self._note_bouton.config(state="normal")

    def _save_note(self, _event: object = None) -> None:
        """Enregistre le contenu du champ comme note de la quête en cours.

        `_note_quest_id` peut avoir été mis à jour par une quête suivante
        pendant que le joueur tapait : ce n'est pas un risque à couvrir comme
        `_show_current_reference` couvre le sien, c'est le comportement
        voulu, le champ note toujours la quête qu'il affiche à l'instant du
        clic.
        """
        if self._note_quest_id is None:
            return
        self._notes = save_note(self._home, self._note_quest_id, self._note_texte.get())
        note = self._notes.get(self._note_quest_id, "")
        self._note_etat.config(text=format_note_placeholder(has_note=bool(note)))

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
