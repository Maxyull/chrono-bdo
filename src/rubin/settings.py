"""Les réglages du joueur : ses zones de lecture, ses seuils.

Tout ce que ce module contient a une valeur par défaut qui marche, mesurée sur
un écran réel. Il n'existe que parce que **cet écran-là n'est pas celui de tout
le monde**.

Les zones de lecture sont calculées à partir de mesures relevées en 2559 x 1439,
interface du jeu à l'échelle par défaut. Elles suivent la fenêtre, mais elles ne
suivent ni une interface agrandie, ni un jeu en fenêtré, ni une disposition que
le joueur a modifiée. Quand elles tombent à côté, le logiciel ne mesure rien et
ne peut pas dire pourquoi : il capture bien une image, elle ne contient
simplement pas ce qu'il cherche.

Le remède n'est pas d'ajouter des mesures de référence, c'est de laisser voir et
corriger. D'où ce module, et l'onglet qui s'appuie dessus.

## Pourquoi un réglage faux ne fabrique pas de mesure fausse

C'est ce qui autorise à donner ces boutons au joueur.

Une **zone mal placée** capture autre chose que le bandeau. L'analyse exige d'y
trouver un titre connu, « Nouvelle quête » ou « Quête accomplie » ; du décor de
jeu n'en contient pas, donc elle ne rend rien. Le résultat est une mesure
manquante, pas une mesure erronée.

La **zone du panneau de choix** est le cas extrême, puisque son calcul d'origine
est estimé et non mesuré : elle tombe donc à côté plus souvent que les deux
autres. Elle reste sans danger pour la même raison, en plus forte. Ce qu'on y
cherche est un nom de quête retrouvé par la fin, ce qui exige une
correspondance **unique** sur au moins huit caractères ; du décor, un texte de
dialogue ou un libellé de bouton n'en produisent aucune. Une zone de choix mal
placée n'identifie rien, elle n'identifie jamais autre chose.

Un **seuil trop haut** rate des bandeaux. Un **seuil trop bas** en propose
davantage à l'analyse, qui les refuse faute de titre. Dans les deux cas on perd
des mesures, on n'en invente aucune.

Une **cadence trop lente** laisse passer des bandeaux entre deux captures. Là
encore, un trou.

C'est la seule raison pour laquelle ces réglages peuvent être exposés sans
danger : le pire qu'ils produisent est un silence, jamais un chiffre faux.

## Une zone n'a de sens qu'avec la taille de fenêtre où elle a été tracée

C'est le détail qui commande toute la mémoire des zones. Un rectangle tracé en
2560 x 1440 ne veut **rien dire** en 1920 x 1080 : l'interface du jeu garde sa
taille en pixels quand la résolution change, donc c'est la distance au coin qui
se conserve, et un rectangle posé en absolu tombe ailleurs.

Une seule zone gardée sans clé serait donc le pire cas du projet : un réglage
**faux ET persistant**. Le joueur passe en fenêtré, sa zone d'hier ne capture
plus rien, et comme elle est enregistrée, elle survit au redémarrage. Rien ne
l'annonce, puisqu'une zone mal placée est silencieuse par construction.

Les zones sont donc retenues dans une table indexée par **taille de fenêtre**,
et `zone_for` ne rend une zone que pour la taille **exacte** où elle a été
tracée. Sur toute autre taille, on retombe sur le calcul d'origine, qui suit la
fenêtre. Rien n'est extrapolé d'une résolution à l'autre : une zone mise à
l'échelle serait une zone inventée, et le principe du projet vaut ici comme
ailleurs.

Ce qui rend la mémorisation sans danger reste l'argument du dessus : **une zone
proposée à tort ne fabrique aucune mesure fausse.** L'analyse exige un titre
connu, que du décor ne contient pas.

## Ce qu'il advient d'une zone tracée avant cette table

Les fichiers écrits jusqu'ici portent `zone_bandeau`, `zone_suivi` et
`zone_choix` **sans taille de fenêtre**. On ne sait donc pas à quelle résolution
ces rectangles ont été tracés, et c'est une information qui ne se devine pas.

Trois traitements étaient possibles, deux sont mauvais :

- les **jeter** perdrait le travail du joueur, pour un fichier parfaitement
  valide la veille. Une mise à jour qui efface un réglage sans le dire est une
  surprise, et celle-là serait irréversible ;
- les **appliquer partout** referait très exactement le défaut qu'on corrige,
  cette fois en le rendant permanent : le rectangle d'hier s'appliquerait à
  toutes les résolutions de demain ;
- les **garder sans les appliquer d'office**, ce qui est retenu.

Une zone sans taille connue est donc relue, conservée en mémoire et **réécrite
telle quelle** dans les champs `banner`, `tracker` et `choice`. Rien n'est
perdu. Mais `zone_for` ne la rend pour aucune taille : elle attend d'être
attribuée à une taille de fenêtre par `adopted_for`, ce qui est un geste, pas
une supposition. Le joueur perd au pire un tracé à refaire d'un clic ; il ne
gagne jamais une zone fausse et durable.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, TypeAlias

from .capture import Rect

#: Nom du fichier, dans le dossier de données du joueur.
FILE_NAME: Final = "reglages.json"

#: Une taille de fenêtre de jeu, en pixels : (largeur, hauteur).
#:
#: C'est la **fenêtre du jeu** qui sert de clé, pas l'écran : un joueur en
#: fenêtré change la première sans toucher au second, et ce sont bien les zones
#: qui bougent dans ce cas-là.
WindowSize: TypeAlias = tuple[int, int]

#: Les trois surfaces lisibles, dans l'ordre où l'interface les présente.
ZONE_NAMES: Final = ("banner", "tracker", "choice")

#: Le nom de chaque zone dans le fichier, en français comme le reste.
ZONE_FILE_KEYS: Final = {
    "banner": "zone_bandeau",
    "tracker": "zone_suivi",
    "choice": "zone_choix",
}

#: Clé du bloc des zones rangées par taille de fenêtre.
ZONES_KEY: Final = "zones_par_taille"

#: Langues de client prises en charge, dans l'ordre où elles sont proposées.
#:
#: Le référentiel porte les deux, et l'identifiant d'une quête est le même des
#: deux côtés : c'est ce qui permet à un joueur du client français et à un
#: joueur du client anglais d'alimenter le même classement.
LANGUAGES: Final = ("fr", "en")

#: Bornes des réglages numériques : (minimum, maximum, défaut).
#:
#: Les défauts sont les valeurs mesurées, celles qui tournent aujourd'hui. Les
#: bornes ne sont pas décoratives : elles empêchent un curseur poussé au bout
#: de rendre le logiciel silencieux d'une façon que personne ne saurait
#: diagnostiquer. Un seuil de présence à zéro, par exemple, ferait analyser
#: chaque image du décor, huit fois par seconde.
LIMITS: Final = {
    "ui_scale": (0.5, 2.0, 1.0),
    "presence_threshold": (0.30, 0.99, 0.70),
    "poll_interval": (0.05, 1.0, 0.125),
    "upcoming_count": (0, 20, 5),
    # Opaque par défaut, et c'est un choix corrigé après coup. La fenêtre était
    # livrée à 0,92, ce qui laissait passer le jeu à travers le texte : sur un
    # décor clair et mouvant, plus rien n'était lisible. La transparence est un
    # confort, la lisibilité est la fonction ; on ne sacrifie pas la seconde à
    # la première par défaut. Le curseur reste là pour qui la veut.
    #
    # Le plancher n'est pas 0 : une fenêtre invisible qu'on ne retrouve plus est
    # un piège dont on ne sort qu'en supprimant le fichier de réglages.
    "opacity": (0.40, 1.0, 1.0),
}


def _clamp(name: str, value: float) -> float:
    """Ramène une valeur entre ses bornes, sans se plaindre.

    Un fichier de réglages est modifiable à la main, et une valeur aberrante ne
    doit pas empêcher le logiciel de démarrer : elle est corrigée en silence
    vers la borne la plus proche. Refuser de se lancer sur un curseur mal réglé
    coûterait une session de jeu pour un caractère de trop.
    """
    bas, haut, _ = LIMITS[name]
    return max(bas, min(haut, value))


@dataclass(frozen=True)
class ZoneEntry:
    """Une zone tracée, **et la taille de fenêtre où elle l'a été**.

    Les deux ne se séparent pas. Un rectangle sans sa taille de fenêtre n'est
    pas une zone à moitié connue, c'est une zone qu'on ne sait pas placer : la
    même suite de quatre nombres désigne le bandeau en 2560 x 1440 et du décor
    en 1920 x 1080.
    """

    #: L'un de `ZONE_NAMES`.
    name: str
    #: La taille de la fenêtre du jeu au moment du tracé.
    size: WindowSize
    rect: Rect


def _valid_entries(entries: Iterable[ZoneEntry]) -> tuple[ZoneEntry, ...]:
    """Ne garde que les entrées utilisables, et une seule par (zone, taille).

    Mêmes refus que pour une zone seule, pour les mêmes raisons : un rectangle
    plat capture une image vide que la reconnaissance traite comme un écran sans
    bandeau, et une taille de fenêtre nulle ou négative ne désigne aucun écran
    réel. Une zone dont le nom est inconnu ne sert personne : elle serait
    réécrite à chaque enregistrement sans que rien ne la lise jamais.

    En cas de doublon, la dernière écrite gagne : c'est le tracé le plus récent
    du joueur pour cette taille-là.
    """
    dernières: dict[tuple[str, WindowSize], ZoneEntry] = {}
    for entrée in entries:
        largeur, hauteur = entrée.size
        if entrée.name not in ZONE_NAMES or largeur <= 0 or hauteur <= 0:
            continue
        if entrée.rect.width <= 0 or entrée.rect.height <= 0:
            continue
        dernières[(entrée.name, entrée.size)] = entrée
    return tuple(sorted(dernières.values(), key=lambda entrée: (entrée.name, entrée.size)))


@dataclass(frozen=True)
class Settings:
    """Ce que le joueur a réglé, ou les valeurs mesurées à défaut.

    Les trois zones valent `None` tant qu'elles n'ont pas été choisies à la
    main : c'est alors le calcul d'origine qui s'applique, celui qui suit la
    fenêtre. `None` veut dire « calcule-la », jamais « pas de zone ».

    ⚠️ La troisième, `choice`, mérite un tracé à la main plus que les deux
    autres : son calcul d'origine est **estimé et non mesuré**. Voir
    `capture.region.choice_region`.

    ⚠️ Ces trois champs sont les zones **sans taille de fenêtre connue** : les
    seules qui puissent en arriver sont celles des fichiers écrits avant que la
    table `zones` existe. Elles sont conservées et réécrites, mais `zone_for` ne
    les rend pour aucune taille. L'en-tête du module dit pourquoi.
    """

    #: Langue du **client de jeu**, pas celle de l'interface. Un joueur
    #: francophone peut très bien jouer sur le client anglais : la langue du jeu
    #: ne se déduit pas de celle de l'utilisateur. C'est elle qui décide sur
    #: quels noms le catalogue compare ce qui est lu à l'écran, donc s'y tromper
    #: ne rate pas une quête sur deux, il les rate toutes.
    language: str = "fr"
    ui_scale: float = 1.0
    presence_threshold: float = 0.70
    poll_interval: float = 0.125
    upcoming_count: int = 5
    opacity: float = 1.0
    banner: Rect | None = None
    tracker: Rect | None = None
    choice: Rect | None = None
    #: Les zones tracées, rangées par taille de fenêtre. Vide au départ.
    zones: tuple[ZoneEntry, ...] = ()

    def normalised(self) -> Settings:
        """Une copie dont tous les nombres tiennent dans leurs bornes."""
        return replace(
            self,
            language=self.language if self.language in LANGUAGES else "fr",
            ui_scale=_clamp("ui_scale", self.ui_scale),
            presence_threshold=_clamp("presence_threshold", self.presence_threshold),
            poll_interval=_clamp("poll_interval", self.poll_interval),
            upcoming_count=int(_clamp("upcoming_count", self.upcoming_count)),
            opacity=_clamp("opacity", self.opacity),
            zones=_valid_entries(self.zones),
        )

    # -------------------------------------------------------------- les zones

    def zone_for(self, name: str, size: WindowSize) -> Rect | None:
        """La zone tracée pour **cette** taille de fenêtre, ou `None`.

        La correspondance est exacte, et rien n'est mis à l'échelle depuis une
        autre taille. `None` veut dire « calcule-la depuis la fenêtre », donc le
        joueur qui change de résolution retombe sur le calcul d'origine, qui
        suit la fenêtre, au lieu de garder un rectangle devenu faux.

        Une zone traînant sans taille connue, venue d'un fichier ancien, n'est
        **pas** rendue ici : voir `adopted_for`.
        """
        for entrée in self.zones:
            if entrée.name == name and entrée.size == size:
                return entrée.rect
        return None

    def with_zone(self, name: str, size: WindowSize, rect: Rect | None) -> Settings:
        """Retient une zone pour une taille de fenêtre, ou l'oublie si `rect` vaut `None`.

        Les zones tracées pour les **autres** tailles sont gardées intactes :
        c'est tout l'intérêt de la table. Un joueur qui alterne entre le plein
        écran et le fenêtré retrouve chaque fois le tracé qui convient, sans
        avoir à le refaire.

        La zone sans taille connue du même nom, s'il en restait une d'un ancien
        fichier, est effacée par la même occasion : le joueur vient de dire où
        est cette zone, et pour quelle taille. Garder à côté un rectangle dont
        on ignore la résolution ne pourrait plus qu'égarer.
        """
        restantes = [
            entrée for entrée in self.zones if not (entrée.name == name and entrée.size == size)
        ]
        if rect is not None:
            restantes.append(ZoneEntry(name=name, size=size, rect=rect))
        return replace(
            self,
            zones=_valid_entries(restantes),
            banner=None if name == "banner" else self.banner,
            tracker=None if name == "tracker" else self.tracker,
            choice=None if name == "choice" else self.choice,
        )

    def unkeyed(self, name: str) -> Rect | None:
        """La zone d'un ancien fichier, tracée à une taille de fenêtre inconnue.

        Elle n'est appliquée nulle part. Elle existe pour que l'interface puisse
        la **proposer** au joueur, qui sait, lui, sur quel écran il l'a tracée.
        """
        return {"banner": self.banner, "tracker": self.tracker, "choice": self.choice}.get(name)

    def adopted_for(self, size: WindowSize) -> Settings:
        """Attribue les zones sans taille connue à `size`, et vide les anciens champs.

        C'est le seul chemin par lequel une zone d'un ancien fichier redevient
        active, et il demande une taille de fenêtre que seul l'appelant connaît.
        Le tracé du joueur n'est donc jamais perdu, mais il n'est jamais non
        plus appliqué à une résolution qu'il ne visait peut-être pas.

        Une zone déjà retenue pour cette taille l'emporte : elle a été tracée en
        sachant sur quel écran, l'autre non.
        """
        adoptées = [
            ZoneEntry(name=nom, size=size, rect=rect)
            for nom in ZONE_NAMES
            if (rect := self.unkeyed(nom)) is not None and self.zone_for(nom, size) is None
        ]
        return replace(
            self,
            zones=_valid_entries([*self.zones, *adoptées]),
            banner=None,
            tracker=None,
            choice=None,
        )

    def to_dict(self) -> dict[str, Any]:
        données: dict[str, Any] = {
            "langue_du_jeu": self.language,
            "echelle_interface": self.ui_scale,
            "seuil_presence": self.presence_threshold,
            "cadence": self.poll_interval,
            "quetes_affichees": self.upcoming_count,
            "opacite": self.opacity,
        }
        # Les zones ne sont écrites que si elles ont été choisies. Écrire les
        # zones calculées les figerait : elles cesseraient de suivre la fenêtre,
        # et un joueur qui change de résolution ne comprendrait pas pourquoi.
        if self.banner is not None:
            données["zone_bandeau"] = _rect_to_dict(self.banner)
        if self.tracker is not None:
            données["zone_suivi"] = _rect_to_dict(self.tracker)
        if self.choice is not None:
            données["zone_choix"] = _rect_to_dict(self.choice)
        # Les zones tracées, rangées sous la taille de fenêtre où elles l'ont
        # été. La clé se lit « 2560x1440 » : quelqu'un qui ouvre ce fichier au
        # bloc-notes doit voir du premier coup d'œil à quel écran chaque
        # rectangle se rapporte, sinon la table serait aussi muette que
        # l'unique rectangle qu'elle remplace.
        par_taille: dict[str, dict[str, dict[str, int]]] = {}
        for entrée in _valid_entries(self.zones):
            clé = _size_to_key(entrée.size)
            par_taille.setdefault(clé, {})[ZONE_FILE_KEYS[entrée.name]] = _rect_to_dict(entrée.rect)
        if par_taille:
            données[ZONES_KEY] = par_taille
        return données

    @classmethod
    def from_dict(cls, données: dict[str, Any]) -> Settings:
        """Relit des réglages, en ignorant tout ce qui est illisible.

        Une clé absente reprend son défaut, une valeur d'un type inattendu
        aussi. Le fichier est modifiable à la main : il vaut mieux repartir sur
        une valeur mesurée que s'arrêter sur une faute de frappe.
        """
        langue = données.get("langue_du_jeu", "fr")
        return cls(
            language=langue if isinstance(langue, str) else "fr",
            ui_scale=_float(données, "echelle_interface", 1.0),
            presence_threshold=_float(données, "seuil_presence", 0.70),
            poll_interval=_float(données, "cadence", 0.125),
            upcoming_count=int(_float(données, "quetes_affichees", 5)),
            opacity=_float(données, "opacite", 1.0),
            banner=_rect_from_dict(données.get("zone_bandeau")),
            tracker=_rect_from_dict(données.get("zone_suivi")),
            choice=_rect_from_dict(données.get("zone_choix")),
            zones=_zones_from_dict(données.get(ZONES_KEY)),
        ).normalised()


def _float(données: dict[str, Any], clé: str, défaut: float) -> float:
    valeur = données.get(clé, défaut)
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return défaut


def _rect_to_dict(rect: Rect) -> dict[str, int]:
    return {"x": rect.left, "y": rect.top, "largeur": rect.width, "hauteur": rect.height}


def _rect_from_dict(brut: Any) -> Rect | None:
    """Relit une zone, ou rend `None` si elle est inutilisable.

    Une zone de largeur ou de hauteur nulle capturerait une image vide, que la
    reconnaissance traiterait comme un écran sans bandeau. Le symptôme serait
    « aucune quête mesurée » sans autre indice, donc on préfère revenir au
    calcul d'origine.
    """
    if not isinstance(brut, dict):
        return None
    try:
        rect = Rect(
            left=int(brut["x"]),
            top=int(brut["y"]),
            width=int(brut["largeur"]),
            height=int(brut["hauteur"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    return rect if rect.width > 0 and rect.height > 0 else None


def _size_to_key(size: WindowSize) -> str:
    return f"{size[0]}x{size[1]}"


def _size_from_key(brut: Any) -> WindowSize | None:
    """Relit « 2560x1440 », ou rend `None` si la clé ne dit pas une taille.

    Une clé qu'on ne sait pas lire fait sauter ses zones, elle n'en promeut
    aucune : appliquer un rectangle à une taille de fenêtre devinée est la seule
    façon, ici, de fabriquer un réglage faux au lieu d'un réglage manquant.
    """
    if not isinstance(brut, str):
        return None
    morceaux = brut.lower().split("x")
    if len(morceaux) != 2:
        return None
    try:
        largeur, hauteur = int(morceaux[0]), int(morceaux[1])
    except ValueError:
        return None
    return (largeur, hauteur) if largeur > 0 and hauteur > 0 else None


def _zones_from_dict(brut: Any) -> tuple[ZoneEntry, ...]:
    """Relit la table des zones, en écartant tout ce qui est illisible.

    Le fichier se corrige au bloc-notes, donc tout y est possible : une taille
    mal écrite, un nom de zone inconnu, un rectangle plat. Chaque cas coûte la
    zone concernée et rien d'autre, jamais le démarrage ni les zones voisines.
    """
    if not isinstance(brut, dict):
        return ()
    entrées: list[ZoneEntry] = []
    noms = {clé_fichier: nom for nom, clé_fichier in ZONE_FILE_KEYS.items()}
    for clé_taille, zones in brut.items():
        taille = _size_from_key(clé_taille)
        if taille is None or not isinstance(zones, dict):
            continue
        for clé_zone, rect_brut in zones.items():
            nom = noms.get(clé_zone)
            rect = _rect_from_dict(rect_brut)
            if nom is None or rect is None:
                continue
            entrées.append(ZoneEntry(name=nom, size=taille, rect=rect))
    return _valid_entries(entrées)


def load(directory: Path) -> Settings:
    """Relit les réglages, ou rend les valeurs mesurées.

    Ne lève jamais. Un fichier absent est le cas normal du premier lancement ;
    un fichier illisible ne doit pas être plus grave, parce qu'il se répare en
    le supprimant et que personne ne devine cela devant une trace d'erreur.
    """
    chemin = directory / FILE_NAME
    try:
        données = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(données, dict):
        return Settings()
    return Settings.from_dict(données)


def save(settings: Settings, directory: Path) -> Path:
    """Écrit les réglages, et rend le chemin du fichier."""
    directory.mkdir(parents=True, exist_ok=True)
    chemin = directory / FILE_NAME
    chemin.write_text(
        json.dumps(settings.normalised().to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return chemin
