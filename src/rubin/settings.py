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
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from .capture import Rect

#: Nom du fichier, dans le dossier de données du joueur.
FILE_NAME: Final = "reglages.json"

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
class Settings:
    """Ce que le joueur a réglé, ou les valeurs mesurées à défaut.

    Les trois zones valent `None` tant qu'elles n'ont pas été choisies à la
    main : c'est alors le calcul d'origine qui s'applique, celui qui suit la
    fenêtre. `None` veut dire « calcule-la », jamais « pas de zone ».

    ⚠️ La troisième, `choice`, mérite un tracé à la main plus que les deux
    autres : son calcul d'origine est **estimé et non mesuré**. Voir
    `capture.region.choice_region`.
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
