"""Récupération du référentiel des quêtes depuis bdocodex.

Il n'existe pas d'API publique. Les données viennent de l'URL qui alimente le
tableau du site, qui renvoie l'intégralité du catalogue en une requête, environ
vingt méga-octets par langue.

Deux conséquences sur la façon de s'en servir :

- **On met en cache.** Le catalogue bouge à chaque mise à jour du jeu, pas à
  chaque lancement du logiciel. Retélécharger vingt méga-octets pour lire des
  données identiques serait un manque d'égards envers un site qui rend ce
  service gratuitement.
- **On ne redistribue pas.** Ce sont des données de jeu appartenant à Pearl
  Abyss. Le logiciel les télécharge chez l'utilisateur au premier lancement,
  il ne les embarque pas.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Final

import requests
from platformdirs import user_cache_dir

#: Le site désigne l'anglais par `us`. On expose `en` vers l'extérieur, qui est
#: le code de langue attendu partout ailleurs, et on traduit ici.
LANGUAGE_CODES: Final[dict[str, str]] = {"fr": "fr", "en": "us"}

_URL: Final = "https://bdocodex.com/query.php"
_USER_AGENT: Final = "chrono-bdo/0.1 (+https://github.com/Maxyull/chrono-bdo)"
_TIMEOUT: Final = 180
#: Une semaine. Le catalogue ne change qu'aux mises à jour du jeu, et une
#: quête ajoutée hier n'a de toute façon aucun temps de référence.
_MAX_AGE_SECONDS: Final = 7 * 24 * 3600


def default_cache_dir() -> Path:
    """Emplacement du cache, hors du dépôt et hors du dossier du jeu."""
    return Path(user_cache_dir("chrono-bdo", "maxyull"))


def cache_path(language: str, cache_dir: Path | None = None) -> Path:
    return (cache_dir or default_cache_dir()) / f"quests_{language}.json"


def _is_fresh(path: Path, max_age: float) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) < max_age
    except OSError:
        return False


def download(language: str) -> dict[str, Any]:
    """Télécharge le catalogue d'une langue, sans passer par le cache.

    La réponse est servie avec un BOM UTF-8 que `json` refuse : il est retiré
    avant l'analyse. C'est le genre de détail qui ne se voit pas en lisant la
    documentation, seulement en regardant les octets.
    """
    code = LANGUAGE_CODES.get(language)
    if code is None:
        raise ValueError(f"langue inconnue : {language!r}, attendu {sorted(LANGUAGE_CODES)}")

    response = requests.get(
        _URL,
        params={"a": "quests", "l": code},
        headers={"User-Agent": _USER_AGENT},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload: dict[str, Any] = json.loads(response.text.lstrip("﻿"))
    return payload


def load(
    language: str,
    cache_dir: Path | None = None,
    max_age: float = _MAX_AGE_SECONDS,
    refresh: bool = False,
) -> dict[str, Any]:
    """Renvoie le catalogue d'une langue, depuis le cache s'il est récent.

    Un cache périmé n'est pas supprimé avant le téléchargement : s'il n'y a pas
    de réseau, mieux vaut un catalogue d'il y a un mois que pas de catalogue du
    tout. Il n'est remplacé qu'une fois la nouvelle version reçue et analysée.
    """
    path = cache_path(language, cache_dir)

    if not refresh and _is_fresh(path, max_age):
        try:
            cached: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return cached
        except (OSError, json.JSONDecodeError):
            pass  # Cache illisible : on retombe sur le téléchargement.

    try:
        payload = download(language)
    except (requests.RequestException, json.JSONDecodeError):
        if path.exists():
            stale: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return stale
        raise

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def catalog_date(language: str, cache_dir: Path | None = None) -> str:
    """Date du catalogue en cache, au format AAAA-MM-JJ.

    Elle voyage avec chaque lot de mesures. Le catalogue suit le jeu et non le
    logiciel : sans cette date, une quête renommée par une mise à jour donnerait
    deux séries de temps sous deux noms différents, sans qu'aucun moyen n'existe
    de savoir qu'il s'agit de la même.

    La date de dernière écriture du fichier fait foi, faute de mieux : la source
    n'annonce pas la version du jeu à laquelle elle correspond. C'est une
    approximation, mais elle est monotone et suffit à ordonner deux catalogues.
    """
    path = cache_path(language, cache_dir)
    try:
        stamp = path.stat().st_mtime
    except OSError:
        stamp = time.time()
    return time.strftime("%Y-%m-%d", time.gmtime(stamp))
