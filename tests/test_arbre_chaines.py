"""L'arbre des chaînes : sa police et la largeur de sa colonne, sans écran.

⚠️ **Ce fichier existe à cause d'un défaut que 722 tests verts ont laissé
passer.** Le 07/08/2026, `_fit_chain_column` appelait
`tkfont.nametofont(ttk.Style().lookup("Treeview", "font"))`. Or `lookup` rend
une **description** de police, `{Segoe UI} 10`, pas un nom, et `nametofont`
la refuse :

    _tkinter.TclError: named font {Segoe UI} 10 does not already exist

`ruff`, `mypy` strict et la suite entière passaient. La colonne restait à sa
largeur par défaut de 200 pixels et les noms longs restaient coupés :
`_show_chains` tourne dans un rappel Tk, qui imprime la trace et poursuit,
donc rien ne s'arrêtait et rien ne remontait. Le défaut n'est apparu qu'en
faisant tourner la vraie fenêtre.

Les tests ci-dessous n'ont besoin d'**aucune fenêtre**, comme
`test_interface_app_threading.py` : les deux méthodes visées ne touchent
qu'à des objets qu'on peut remplacer par des porteurs minimaux. C'est ce qui
les rend exécutables en intégration continue, où il n'y a pas d'écran et où
`tk.Tk()` plante.
"""

from __future__ import annotations

from typing import Any

import pytest

from rubin.interface import app as module_app
from rubin.interface.app import TREE_INDENT, RubinApp
from rubin.interface.presentation import COLUMN_PADDING


class _PoliceFactice:
    """Une police dont on peut mesurer les appels, et le texte."""

    def __init__(self, font: Any = None) -> None:
        self.description = font

    def measure(self, texte: str) -> int:
        # Dix pixels par caractère : un chiffre rond rend les attentes des
        # tests lisibles, et la vraie police n'a rien à prouver ici.
        return 10 * len(texte)


class _StyleFactice:
    """Un `ttk.Style` qui rend ce que le vrai rend : une DESCRIPTION."""

    def __init__(self, valeur: str) -> None:
        self._valeur = valeur

    def lookup(self, _classe: str, _option: str) -> str:
        return self._valeur


class _PorteurPolice:
    """Le strict nécessaire que `_tree_font` lit et écrit sur `self`."""

    def __init__(self) -> None:
        self._police_arbre: Any = None


class TestPoliceDeLArbre:
    def test_une_description_de_style_nest_jamais_passee_a_nametofont(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Régression, le défaut du 07/08/2026 en une ligne.

        `nametofont` exige un NOM de police déjà déclaré ; `lookup` rend une
        description. Les confondre lève `TclError` au premier remplissage de
        l'arbre, dans un rappel Tk qui avale l'erreur.

        Le faux `nametofont` ci-dessous lève, exactement comme le vrai le
        ferait sur cette valeur : si le code y revient un jour, ce test tombe
        au lieu de laisser la colonne à sa largeur par défaut.
        """

        def interdit(nom: str) -> Any:
            raise AssertionError(
                f"nametofont appelé avec la description {nom!r} : c'est le "
                "défaut du 07/08/2026, il faut tkfont.Font(font=...)"
            )

        monkeypatch.setattr(module_app.tkfont, "nametofont", interdit)
        monkeypatch.setattr(module_app.tkfont, "Font", _PoliceFactice)
        monkeypatch.setattr(module_app.ttk, "Style", lambda: _StyleFactice("{Segoe UI} 10"))

        police = RubinApp._tree_font(_PorteurPolice())  # type: ignore[arg-type]

        assert police.description == "{Segoe UI} 10"  # type: ignore[attr-defined]

    def test_la_police_nest_construite_quune_fois(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L'arbre se remplit à chaque ouverture de chaîne. Une police par
        remplissage laisserait derrière elle un objet Tk par dépliage, pour
        une valeur qui ne change jamais."""
        constructions = []

        def compter(font: Any = None) -> _PoliceFactice:
            constructions.append(font)
            return _PoliceFactice(font)

        monkeypatch.setattr(module_app.tkfont, "Font", compter)
        monkeypatch.setattr(module_app.ttk, "Style", lambda: _StyleFactice("{Segoe UI} 10"))
        porteur = _PorteurPolice()

        première = RubinApp._tree_font(porteur)  # type: ignore[arg-type]
        seconde = RubinApp._tree_font(porteur)  # type: ignore[arg-type]

        assert première is seconde
        assert len(constructions) == 1

    def test_un_style_sans_police_retombe_sur_celle_du_systeme(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `lookup` rend une chaîne vide quand l'option n'est pas posée, ce qui
        # est le cas sur un thème qui ne règle pas la police du Treeview.
        monkeypatch.setattr(module_app.tkfont, "Font", _PoliceFactice)
        monkeypatch.setattr(module_app.ttk, "Style", lambda: _StyleFactice(""))

        police = RubinApp._tree_font(_PorteurPolice())  # type: ignore[arg-type]

        assert police.description == "TkDefaultFont"  # type: ignore[attr-defined]


class _ArbreFactice:
    """Un `ttk.Treeview` réduit à ce que `_fit_chain_column` lui demande."""

    def __init__(self, noeuds: dict[str, list[str]], textes: dict[str, str], largeur: int):
        self._noeuds = noeuds
        self._textes = textes
        self._largeur = largeur
        self.colonnes: list[tuple[str, int]] = []

    def get_children(self, parent: str = "") -> list[str]:
        return self._noeuds.get(parent, [])

    def item(self, iid: str, option: str) -> str:
        assert option == "text"
        return self._textes.get(iid, "")

    def winfo_width(self) -> int:
        return self._largeur

    def column(self, colonne: str, width: int) -> None:
        self.colonnes.append((colonne, width))


class _PorteurArbre:
    def __init__(self, arbre: _ArbreFactice) -> None:
        self._chains = arbre

    def _tree_font(self) -> _PoliceFactice:
        return _PoliceFactice()


class TestLargeurDeLaColonne:
    def test_compte_lindentation_des_quetes_dune_chaine(self) -> None:
        """Une quête dépliée est indentée d'un niveau sous sa chaîne : mesurer
        son texte seul la croirait plus étroite qu'elle ne s'affiche, et la
        recouperait exactement de la largeur de l'indentation."""
        arbre = _ArbreFactice(
            noeuds={"": ["chaine"], "chaine": ["quete"]},
            textes={"chaine": "abcde", "quete": "abcde"},
            largeur=10,
        )

        RubinApp._fit_chain_column(_PorteurArbre(arbre))  # type: ignore[arg-type]

        colonne, largeur = arbre.colonnes[-1]
        assert colonne == "#0"
        # 5 caractères à 10 px, plus un niveau d'indentation, plus la marge.
        assert largeur == 50 + TREE_INDENT + COLUMN_PADDING

    def test_ignore_les_enfants_vides_du_depliage(self) -> None:
        """Régression : chaque chaîne repliée porte un enfant au texte vide,
        le seul rôle duquel est de faire apparaître la flèche de dépliage
        (voir `_insert_chain_node`). Le compter donnerait une largeur tirée
        d'une ligne qui ne s'affiche jamais.

        ⚠️ **Le nom de la chaîne est délibérément plus court que
        l'indentation d'un niveau.** Le premier jet de ce test employait
        « abc », soit 30 pixels, contre 20 pixels d'indentation pour l'enfant
        vide : les deux calculs rendaient alors le même maximum et le test
        passait dans les deux cas. Piégé, il n'avait rien attrapé. Avec un
        nom d'un seul caractère, compter l'enfant vide donne 20 au lieu de
        10, et l'écart se voit."""
        arbre = _ArbreFactice(
            noeuds={"": ["chaine"], "chaine": ["vide"]},
            textes={"chaine": "a", "vide": ""},
            largeur=1,
        )

        RubinApp._fit_chain_column(_PorteurArbre(arbre))  # type: ignore[arg-type]

        _colonne, largeur = arbre.colonnes[-1]
        assert largeur == 10 + COLUMN_PADDING

    def test_un_arbre_vide_garde_la_place_disponible(self) -> None:
        # Avant la première réponse du serveur : rien à mesurer, et surtout
        # pas de colonne rétrécie à zéro.
        arbre = _ArbreFactice(noeuds={}, textes={}, largeur=394)

        RubinApp._fit_chain_column(_PorteurArbre(arbre))  # type: ignore[arg-type]

        assert arbre.colonnes[-1] == ("#0", 394)
