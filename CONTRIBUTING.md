# Contribuer à Chrono

Merci de vouloir aider. Ce fichier dit comment le projet fonctionne pour que
vous n'ayez pas à le deviner. Les conventions sont celles de
[butin-bdo](https://github.com/Maxyull/butin-bdo), qui partage son noyau de
reconnaissance avec ce projet.

## Langue du projet

Chrono s'adresse d'abord aux joueurs francophones, donc **tout ce qui est lu par
un humain est en français** : ce README, la documentation, les commentaires, les
messages de commit, les issues et les pull requests.

**Le code lui-même est en anglais** : noms de modules, de fonctions, de
variables. Les bibliothèques utilisées le sont, l'écosystème Python aussi, et
mélanger les deux dans une même ligne se lit mal.

```python
def resolve(self, name: str, language: str = "fr") -> QuestId | None:
    """Renvoie l'identifiant de la quête, ou None si rien de sûr n'est trouvé."""
```

Les messages de commit sont à l'impératif présent : « Ajoute le référentiel »,
pas « Ajout du référentiel » ni « J'ai ajouté ».

## Mise en place

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Le référentiel des quêtes n'a besoin ni d'écran ni de moteur de reconnaissance :
ses dépendances sont dans l'extra `capture`, installé seulement quand on
travaille sur la capture d'écran.

## Avant d'ouvrir une pull request

```bash
ruff check .
mypy
pytest
```

L'intégration continue lance exactement ces trois commandes, sur Python 3.10,
3.11 et 3.12.

Une branche par changement, jamais de poussée directe sur `main`.

## Politique de tests

Chaque correction de bogue et chaque fonctionnalité arrive avec **deux** tests,
pas un :

1. **Un test unitaire**, qui vérifie que la logique fait ce qu'elle doit faire.
2. **Un test de régression**, qui empêche le bogue de revenir par un autre
   chemin, et dont la docstring raconte le cas réel rencontré.

Un test de régression sans explication ne sert qu'une fois. Écrivez ce qui
serait cassé sans lui, concrètement :

```python
def test_un_nom_lu_a_l_ecran_retombe_sur_la_bonne_quete(self) -> None:
    """Régression : « [Calpheon] Jeron, la tacticienne » vaut 21136/1.

    C'est le seul test qui relie les deux moitiés du projet, ce que l'œil
    voit et ce que le référentiel contient. S'il casse, le logiciel mesure
    des temps qu'il attribue à la mauvaise quête, ce qui est pire que de ne
    rien mesurer.
    """
```

## Données de test réelles

Les tests utilisent de **vraies** quêtes avec leurs **vrais** identifiants,
jamais des valeurs inventées. Les échantillons de `tests/data/` sont des extraits
authentiques du référentiel.

Un jeu de test inventé passe à côté de ce qui casse réellement : un identifiant
servi comme objet et non comme chaîne, une apostrophe encodée en entité HTML
dans « O&#39;dyllita », une colonne qui change de type d'une ligne à l'autre.

## Le principe qui tranche les arbitrages

> **Rater une mesure donne un chiffre incomplet. En inventer une donne un
> chiffre faux.**

Un chiffre incomplet reste exploitable et se corrige avec plus de données. Un
chiffre faux entre dans les médianes et n'en ressort jamais, et rien dans
l'interface ne signale qu'il est faux.

Les deux erreurs ne coûtent pas la même chose, donc les réglages ne sont pas
symétriques. Dans le doute, Chrono renonce.

## Versionnage

Voir [docs/versionnage.md](docs/versionnage.md). Trois choses versionnent
séparément : le logiciel, le protocole d'envoi au serveur, et le référentiel des
quêtes, qui suit le jeu et non nous.

## Ce que Chrono ne fera jamais

Aucune interaction avec le jeu : pas de lecture mémoire, pas d'injection, pas de
surcouche graphique, pas de touche simulée. Chrono lit une capture d'écran,
comme un logiciel d'enregistrement vidéo.

C'est une limite de conception, pas une étape à franchir plus tard. Une
proposition qui la franchit sera refusée, quel que soit son intérêt par ailleurs.
