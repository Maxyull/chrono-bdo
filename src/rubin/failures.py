"""Garder les lectures ratées, au lieu de les jeter en silence.

Jusqu'ici, une image dont la lecture n'aboutissait à aucun bandeau était
abandonnée sur place. Il ne restait rien : ni l'image, ni ce que la
reconnaissance avait cru y lire. Une session qui ne mesurait rien ne disait donc
pas pourquoi, et les cinq pièges connus du projet ont tous dû être trouvés à la
main, en jouant, écran sous les yeux.

Ce module retient ce qui a raté. C'est un journal de diagnostic, pas une
collecte : **rien ne part sur le réseau**. Le joueur qui veut aider fabrique
lui-même une archive et l'envoie où il veut, ce qui rend la question du
consentement sans objet. Transmettre les données de quelqu'un sans qu'il l'ait
demandé serait une décision prise à sa place.

Ce que contient une archive, pour que celui qui l'envoie le sache :

- des vignettes en niveaux de gris de **349 x 115 pixels** pour le bandeau et
  **340 x 380** pour le panneau de suivi, c'est-à-dire le texte de la quête et
  rien d'autre. Pas la fenêtre du jeu, pas le chat, pas le nom du personnage,
  pas la carte ;
- les lignes que la reconnaissance a rendues, telles quelles.

Ces deux éléments répondent à deux questions différentes, et c'est pour cela
qu'ils sont gardés tous les deux. Les lignes disent si c'est l'analyse qui a
échoué sur un texte pourtant bien lu ; l'image dit si c'est la lecture qui n'a
rien vu de correct. Sans l'image, un échec de reconnaissance ressemble à un
écran vide ; sans les lignes, une analyse trop stricte ressemble à un défaut
d'image.

Quatre garde-fous pour que le dossier ne grossisse pas sans fin : seuls les
échecs sont gardés, une image déjà vue n'est pas réécrite, le format est du gris
en WebP, et tout ce qui dépasse quatre-vingt-dix jours ou la taille maximale
disparaît.

Le WebP est **sans perte**, et c'est délibéré malgré le coût. Ces images servent
à rejouer la reconnaissance quand elle s'améliore : sur une image altérée par la
compression, elle ne lirait pas tout à fait ce qu'elle aurait lu sur la vraie
capture, et le résultat ne prouverait rien. Une comparaison qui ne prouve rien
mais qu'on croit probante est pire qu'une comparaison manquante.
"""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .capture import GrayFrame
from .reading import TextLine

#: Au-delà de quoi une image retenue est effacée. Trois mois couvrent largement
#: le délai entre une session qui rate et le moment où quelqu'un s'en occupe,
#: sans garder indéfiniment des traces dont plus personne n'a l'usage.
RETENTION_DAYS: Final = 90

#: Plafond du dossier. Une vignette de bandeau en gris pèse 20 kilo-octets,
#: mesuré sur trois captures réelles en 2559x1439 : 17,1, 17,8 et 22,8. Ce
#: plafond représente donc environ cinq mille échecs, quand une session qui rate
#: tout en produit quelques centaines. Il existe pour qu'une reconnaissance qui
#: s'effondre ne remplisse pas le disque de quelqu'un, pas pour rationner.
MAX_BYTES: Final = 100 * 1024 * 1024

#: Nom du journal, à côté des images.
JOURNAL_NAME: Final = "journal.jsonl"

@dataclass(frozen=True)
class Destination:
    """Un endroit où déposer une archive, et ce qu'il accepte.

    Le plafond est celui de la destination, pas une préférence du logiciel :
    fabriquer une archive que l'hébergeur visé refusera serait un piège, et le
    joueur ne le découvrirait qu'au moment du dépôt, une fois le fichier prêt.
    """

    key: str
    label: str
    url: str
    max_bytes: int
    #: Vrai si déposer exige de créer un compte, ce qui est le vrai coût pour
    #: celui qui rend service et n'a rien demandé.
    account: bool
    detail: str

    @property
    def kilobytes(self) -> int:
        return self.max_bytes // 1024


#: Les destinations proposées, du plus contraint au plus large. L'ordre compte :
#: quand une archive déborde, la suivante est celle qu'on suggère.
#:
#: ⚠️ Les plafonds de catbox et pixeldrain sont ceux annoncés par ces services,
#: et ils peuvent changer sans prévenir. Celui de GitHub est documenté et stable
#: depuis des années. Aucun n'est vérifié à l'exécution : l'archive est bornée,
#: le dépôt reste manuel, donc une limite devenue fausse coûte au pire un
#: deuxième essai.
DESTINATIONS: Final = (
    Destination(
        key="github",
        label="issue GitHub",
        url="https://github.com/Maxyull/rubin-bdo/issues",
        max_bytes=25 * 1024 * 1024,
        account=True,
        detail="glissez le fichier dans le commentaire ; c'est là qu'il servira",
    ),
    Destination(
        key="catbox",
        label="catbox.moe",
        url="https://catbox.moe",
        max_bytes=200 * 1024 * 1024,
        account=False,
        detail="sans compte, rend un lien à coller dans l'issue",
    ),
    Destination(
        key="pixeldrain",
        label="pixeldrain",
        url="https://pixeldrain.com",
        max_bytes=20 * 1024 * 1024 * 1024,
        account=False,
        detail="sans compte, pour les très gros envois",
    ),
)

#: Taille maximale par défaut : celle de la destination la plus contrainte, qui
#: est aussi celle où l'archive est la plus utile. À 20 kilo-octets la vignette,
#: ce plafond tient environ mille deux cents échecs, soit bien plus qu'une
#: session entière n'en produit.
ARCHIVE_MAX_BYTES: Final = DESTINATIONS[0].max_bytes


def find_destination(key: str) -> Destination:
    """La destination portant cette clé."""
    for candidate in DESTINATIONS:
        if candidate.key == key:
            return candidate
    raise KeyError(key)  # pragma: pas de couverture


def larger_than(size: int) -> Destination | None:
    """La première destination qui accepterait une archive de cette taille.

    Sert à proposer une porte de sortie quand l'archive déborde, plutôt que de
    laisser quelqu'un devant une troncature sans solution.
    """
    for candidate in DESTINATIONS:
        if candidate.max_bytes >= size:
            return candidate
    return None  # pragma: pas de couverture


#: Une image jugée digne d'être lue, dont aucun bandeau n'est sorti.
READING_FAILED: Final = "lecture-ratee"

#: Une image gardée alors que la surveillance ne voit RIEN depuis longtemps.
#:
#: Elle n'a rien raté : elle n'a rien vu. C'est le seul cas où l'on garde une
#: image que le seuil de présence a refusée, et c'est justement parce que ce
#: refus est le symptôme qu'on cherche à comprendre.
BLIND: Final = "aveugle"


def fingerprint(image: GrayFrame) -> str:
    """Empreinte d'une image, pour ne pas garder deux fois la même.

    Sur les octets bruts, pas sur le fichier encodé : deux encodages du même
    tableau peuvent différer d'une version de bibliothèque à l'autre, et
    l'égalité qui nous intéresse est celle des pixels.
    """
    digest = hashlib.sha256()
    digest.update(str(image.shape).encode("ascii"))
    digest.update(image.tobytes())
    return digest.hexdigest()[:16]


def _encode_webp(image: GrayFrame, path: Path) -> bool:
    """Écrit l'image en WebP sans perte, et dit si elle a pu l'être.

    L'import est différé, comme dans `capture.banner` : Pillow arrive avec
    l'extra `capture`, et `rubin referentiel` doit continuer de tourner sans lui.
    Une écriture impossible n'est pas une erreur fatale ; retenir un échec est
    utile, pas indispensable, et faire tomber une session de jeu pour cela serait
    hors de proportion.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: pas de couverture
        return False
    try:
        Image.fromarray(image, mode="L").save(path, format="WEBP", lossless=True)
    except (OSError, ValueError):
        return False
    return True


def _journal_line(line: TextLine | tuple[str, float]) -> dict[str, object]:
    """Une ligne du journal des échecs, avec sa boîte quand on l'a.

    La boîte est écrite parce que son absence a coûté cher. Le journal du 5 août
    2026 ne portait que le texte et le score : il montrait bien que le chat était
    mélangé au bandeau, mais pas **où** chaque ligne se trouvait, donc pas de
    quoi mesurer la séparation. Il a fallu rejouer la reconnaissance sur les neuf
    vignettes gardées pour retrouver une information que le moteur avait rendue
    et qu'on avait jetée deux fois de suite.

    Les coordonnées ne disent rien de plus sur le joueur que la vignette
    elle-même, qui est déjà dans le dossier : ce sont des positions à
    l'intérieur d'un rectangle de 349 pixels de large, pas sur son écran.
    """
    if isinstance(line, tuple):
        text, score = line
        return {"texte": text, "score": round(score, 3)}
    return {
        "texte": line.text,
        "score": round(line.score, 3),
        "gauche": round(line.left, 1),
        "droite": round(line.right, 1),
        "haut": round(line.top, 1),
        "bas": round(line.bottom, 1),
    }


@dataclass(frozen=True)
class FailureStats:
    """Ce que le dossier contient, pour le dire en fin de session."""

    images: int = 0
    entries: int = 0
    bytes: int = 0

    @property
    def kilobytes(self) -> int:
        return self.bytes // 1024


@dataclass(frozen=True)
class ArchiveResult:
    """Une archive fabriquée, et ce qui n'a pas tenu dedans."""

    path: Path
    images: int
    left_out: int
    bytes: int
    #: Ce qu'il aurait fallu pour tout emporter. Permet de désigner une
    #: destination plus large au lieu de constater la troncature sans suite.
    needed: int

    @property
    def kilobytes(self) -> int:
        return self.bytes // 1024


class FailureStore:
    """Le dossier des lectures ratées, et ce qu'on peut en faire.

    Toutes les écritures sont tolérantes à l'échec. Ce dossier sert à
    diagnostiquer une session ; il ne doit jamais être la raison pour laquelle
    une session s'arrête.
    """

    def __init__(
        self,
        directory: Path,
        retention_days: int = RETENTION_DAYS,
        max_bytes: int = MAX_BYTES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._directory = directory
        self._retention = retention_days * 86400
        self._max_bytes = max_bytes
        self._clock = clock
        #: Échecs qu'on n'a pas su retenir, faute de Pillow ou de disque. Compté
        #: plutôt que tu, pour qu'un dossier vide ne se lise pas comme
        #: « aucun échec ».
        self.unwritable = 0

    @property
    def directory(self) -> Path:
        return self._directory

    def _images(self) -> list[Path]:
        if not self._directory.is_dir():
            return []
        return sorted(self._directory.glob("*.webp"))

    def keep(
        self,
        image: GrayFrame,
        lines: Sequence[TextLine] | Sequence[tuple[str, float]],
        at: float | None = None,
        reason: str = READING_FAILED,
    ) -> Path | None:
        """Retient une image et ce qu'on en a tiré, et renvoie le fichier écrit.

        L'image n'est écrite qu'une fois par empreinte, mais le journal reçoit
        une ligne à chaque occurrence : c'est la fréquence d'un échec qui dit
        s'il s'agit d'un cas isolé ou du défaut qui plombe toute une session, et
        elle ne coûte que quelques dizaines d'octets.

        `reason` distingue deux cas qu'il ne faut surtout pas confondre en les
        relisant. `READING_FAILED` est le cas d'origine : une image jugée digne
        d'être lue dont aucun bandeau n'est sorti. `BLIND` est l'autre, ajouté
        après la séance du 5 août 2026 : la surveillance ne voit **rien du
        tout**, aucun bandeau depuis longtemps, et l'image est gardée pour
        qu'on sache enfin CE QUE LA CAPTURE CONTIENT.

        Ce jour-là, une session a compté 4 832 images et zéro bandeau pendant
        qu'un témoin extérieur en voyait huit sur le même rectangle. Aucune
        image n'avait été gardée, puisque aucune n'avait franchi le seuil de
        présence, donc rien ne permettait de savoir si la capture montrait le
        jeu, un écran figé, ou autre chose. Cinq programmes de diagnostic
        écrits hors du logiciel n'ont pas suffi à trancher.
        """
        moment = self._clock() if at is None else at
        mark = fingerprint(image)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.unwritable += 1
            return None

        path = self._directory / f"{mark}.webp"
        if not path.exists() and not _encode_webp(image, path):
            self.unwritable += 1
            return None

        # Le score de chaque ligne est gardé avec son texte, parce qu'il départage
        # deux échecs qui n'ont rien à voir : une reconnaissance sûre d'elle que
        # l'analyse a refusée, et une reconnaissance qui n'a rien vu de net.
        entry = {
            "empreinte": mark,
            "instant": round(moment, 3),
            "hauteur": int(image.shape[0]),
            "largeur": int(image.shape[1]),
            "lignes": [_journal_line(line) for line in lines],
            "raison": reason,
        }
        try:
            with (self._directory / JOURNAL_NAME).open("a", encoding="utf-8") as journal:
                journal.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            self.unwritable += 1
        return path

    def purge(self) -> int:
        """Efface ce qui est trop vieux, puis ce qui dépasse le plafond.

        Renvoie le nombre de fichiers effacés. Les plus anciens partent en
        premier : un échec récent décrit la version en cours, un échec de l'an
        dernier décrit une reconnaissance qui n'existe plus.
        """
        removed = 0
        images = self._images()
        cutoff = self._clock() - self._retention
        remaining: list[tuple[float, int, Path]] = []
        for path in images:
            try:
                stat = path.stat()
            except OSError:  # pragma: pas de couverture
                continue
            if stat.st_mtime < cutoff:
                if self._unlink(path):
                    removed += 1
                continue
            remaining.append((stat.st_mtime, stat.st_size, path))

        total = sum(size for _, size, _ in remaining)
        # La plus récente n'est jamais effacée, même si elle dépasse à elle
        # seule le plafond. Vider le dossier pour respecter une taille laisserait
        # zéro image à regarder, c'est-à-dire exactement l'état qu'on cherchait à
        # quitter en écrivant ce module.
        for _, size, path in sorted(remaining)[:-1]:
            if total <= self._max_bytes:
                break
            if self._unlink(path):
                removed += 1
                total -= size
        return removed

    @staticmethod
    def _unlink(path: Path) -> bool:
        try:
            path.unlink()
        except OSError:  # pragma: pas de couverture
            return False
        return True

    def stats(self) -> FailureStats:
        """Compte ce qui est retenu, sans rien charger en mémoire."""
        images = self._images()
        size = 0
        for path in images:
            try:
                size += path.stat().st_size
            except OSError:  # pragma: pas de couverture
                continue
        journal = self._directory / JOURNAL_NAME
        entries = 0
        if journal.is_file():
            try:
                with journal.open(encoding="utf-8") as handle:
                    entries = sum(1 for line in handle if line.strip())
                size += journal.stat().st_size
            except OSError:  # pragma: pas de couverture
                pass
        return FailureStats(images=len(images), entries=entries, bytes=size)

    def package(
        self, destination: Path, max_bytes: int = ARCHIVE_MAX_BYTES
    ) -> ArchiveResult | None:
        """Rassemble tout dans une archive, prête à être envoyée à la main.

        Renvoie `None` quand il n'y a rien à mettre dedans, plutôt qu'une
        archive vide : proposer d'envoyer un fichier qui ne contient rien ferait
        perdre son temps à celui qui le fait comme à celui qui le reçoit.

        Les images les plus **récentes** passent en premier, et celles qui ne
        tiennent pas dans le plafond sont comptées. Un échec d'aujourd'hui décrit
        la version qui tourne ; un échec d'il y a deux mois décrit peut-être une
        reconnaissance déjà corrigée. Le compte des laissées-dehors est rendu
        avec l'archive : une troncature qui ne se dit pas se lirait comme un
        inventaire complet.
        """
        journal = self._directory / JOURNAL_NAME
        images = self._images()
        if not images and not journal.is_file():
            return None

        by_recency: list[tuple[float, int, Path]] = []
        for path in images:
            try:
                stat = path.stat()
            except OSError:  # pragma: pas de couverture
                continue
            by_recency.append((stat.st_mtime, stat.st_size, path))
        by_recency.sort(reverse=True)

        # Le journal est prioritaire sur les images : c'est lui qui dit ce qui a
        # été lu, et il pèse quelques octets par échec.
        journal_size = journal.stat().st_size if journal.is_file() else 0
        budget = max_bytes - journal_size

        kept: list[Path] = []
        left_out = 0
        for _, size, path in by_recency:
            if size <= budget:
                kept.append(path)
                budget -= size
            else:
                left_out += 1

        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in kept:
                archive.write(path, arcname=path.name)
            if journal.is_file():
                archive.write(journal, arcname=JOURNAL_NAME)
        return ArchiveResult(
            path=destination,
            images=len(kept),
            left_out=left_out,
            bytes=destination.stat().st_size,
            needed=sum(size for _, size, _ in by_recency) + journal_size,
        )
