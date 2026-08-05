"""Envoi des mesures au serveur, et journal de session écrit au fil de l'eau.

L'envoi n'a jamais lieu tout seul. Il faut l'adresse d'un serveur pour qu'un lot
parte, et sans elle le logiciel se contente de mesurer et d'écrire ses résultats
en local. Transmettre les données de quelqu'un sans qu'il l'ait demandé serait
une décision prise à sa place, et le fait qu'elles soient anonymes n'y change
rien.

## Pourquoi un journal en ajout, et pas un bloc écrit à la fin

Ce module a longtemps affirmé que tout partait « en fin de session ». Ça avait
une conséquence qu'on ne voyait qu'en la subissant : **une session de deux
heures disparaissait entièrement** si le processus était tué, si Windows
redémarrait ou si le logiciel plantait. La fermeture par la croix, elle, est
couverte, mais les trois autres cas n'envoient aucun événement.

⚠️ **Le remède n'est pas d'attraper plus d'événements de fermeture.** On n'en
attrape jamais tout, un `kill` ne se négocie pas, et chaque piège ajouté donne
une fausse impression de sûreté, ce qui est pire que de savoir qu'on n'est pas
couvert.

Le remède est d'**écrire chaque mesure dès qu'elle existe**, en ajout, une ligne
par mesure. On ne perd alors que ce qui n'a pas encore été mesuré, c'est-à-dire
rien. Un journal resté orphelin est relu au démarrage suivant.

## Pourquoi un envoi incrémental, et le piège qu'il évite

⚠️ **LE PIÈGE, et c'est le seul risque réel de ce chantier : le double
comptage.** Renvoyer toute la session à chaque quête ferait recevoir au serveur
les mêmes mesures plusieurs fois. Elles gonfleraient `samples` et entreraient
dans les médianes. C'est exactement le chiffre faux qui n'en ressort jamais, et
il serait **invisible** : rien ne distingue une mesure reçue deux fois de deux
mesures réelles.

`IncrementalSender` ne présente donc au serveur que les mesures qu'il ne lui a
jamais présentées, et le journal garde trace du curseur pour qu'une relecture
après plantage ne renvoie pas ce qui était déjà parti.

## Ce qu'on fait d'un envoi dont on ignore le sort

`UploadResult.answered` dit si le serveur a répondu quelque chose, quel que soit
le statut. C'est ce qui décide d'un réessai :

- **le serveur a répondu une erreur** : il n'a rien enregistré, donc réessayer
  ne peut pas fabriquer de doublon. Les mesures restent en attente ;
- **le serveur n'a rien répondu** : la requête a pu aboutir avant que la réponse
  se perde. Réessayer fabriquerait peut-être un doublon, donc on ne réessaie
  pas. La copie disque, elle, garde tout.

C'est le principe du projet appliqué tel quel : rater une mesure donne un
chiffre incomplet, en inventer une donne un chiffre faux.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

import requests

from .protocol import PROTOCOL_VERSION, MeasurePayload, SessionPayload

_TIMEOUT: Final = 30
_USER_AGENT: Final = "rubin-bdo"

#: Extension du journal écrit au fil de l'eau. Une extension distincte du lot
#: final évite qu'un journal interrompu passe pour un lot complet.
JOURNAL_SUFFIX: Final = ".jsonl"

_SESSION_LINE: Final = "session"
_MEASURE_LINE: Final = "measure"
_SENT_LINE: Final = "sent"


@dataclass(frozen=True)
class UploadResult:
    """Ce que le serveur a répondu, ou pourquoi il n'a rien répondu.

    `answered` ne dit pas que l'envoi a réussi : il dit que le serveur a rendu
    un statut, donc qu'on **sait** ce qu'il a fait du lot. C'est cette
    distinction, et pas `ok`, qui autorise un réessai sans risque de doublon.
    """

    ok: bool
    detail: str
    stored: int = 0
    refused: int = 0
    answered: bool = False


def save_session(payload: SessionPayload, path: Path) -> Path:
    """Écrit le lot complet sur le disque, en un bloc.

    Toujours, y compris quand l'envoi réussit. Une session mesurée puis perdue
    parce que le réseau a hoqueté serait irrattrapable : la partie, elle, ne se
    rejoue pas.

    Ce bloc reste le format de référence d'une session terminée. Il n'est plus
    la seule protection : `SessionJournal` écrit chaque mesure dès qu'elle
    existe, pour les fins de session qui n'arrivent jamais.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.to_json(), encoding="utf-8")
    return path


def send_session(payload: SessionPayload, url: str, timeout: int = _TIMEOUT) -> UploadResult:
    """Envoie un lot au serveur.

    Ne lève jamais. Un serveur injoignable ne doit pas faire disparaître le
    bilan d'une session sous une trace d'erreur : le joueur veut voir ses temps,
    que l'envoi ait abouti ou non. Le lot est de toute façon conservé sur le
    disque et pourra être renvoyé.
    """
    endpoint = url.rstrip("/") + "/v1/sessions"
    try:
        response = requests.post(
            endpoint,
            data=payload.to_json().encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
            timeout=timeout,
        )
    except requests.RequestException as error:
        # Aucune réponse : on ignore si le serveur a reçu le lot. Voir l'en-tête
        # du module, c'est ce qui interdit le réessai.
        return UploadResult(ok=False, detail=f"serveur injoignable : {error}", answered=False)

    if response.status_code >= 400:
        detail = response.text[:300]
        # Le serveur explique son refus dans un champ « detail ». S'il répond
        # autre chose, le texte brut fera l'affaire : un message approximatif
        # vaut mieux qu'une erreur d'analyse par-dessus une erreur d'envoi.
        with contextlib.suppress(ValueError, AttributeError):
            detail = str(response.json().get("detail", detail))
        return UploadResult(
            ok=False,
            detail=f"refusé ({response.status_code}) : {detail}",
            answered=True,
        )

    try:
        body = response.json()
    except ValueError:
        return UploadResult(ok=True, detail="accepté, réponse illisible", answered=True)
    return UploadResult(
        ok=True,
        detail="accepté",
        stored=int(body.get("enregistrees", 0)),
        refused=int(body.get("refusees", 0)),
        answered=True,
    )


# ------------------------------------------------------------------ le journal


class SessionJournal:
    """Le journal d'une session, écrit ligne par ligne, en ajout.

    Une ligne d'en-tête décrit la session, puis une ligne par mesure, puis des
    marques disant jusqu'où le serveur a été servi. Rien n'est jamais réécrit :
    une ligne posée reste, et un processus tué au milieu d'une écriture ne peut
    abîmer que la dernière ligne, que la relecture jette.

    Le fichier est rouvert à chaque ligne plutôt que gardé ouvert. À raison
    d'une ligne par quête, le coût est nul, et il n'y a plus de tampon à vider
    au moment précis où plus personne ne vide rien.

    ⚠️ **Le journal ne fait jamais échouer une mesure.** Un disque plein ou un
    dossier en lecture seule le met hors service, `broken` passe à vrai, et la
    session continue de mesurer. Perdre le filet de sécurité est un moindre mal
    devant perdre la session elle-même.
    """

    def __init__(self, path: Path, header: SessionPayload) -> None:
        self.path = path
        self.broken = False
        self._lock = threading.Lock()
        self._write(
            {
                "kind": _SESSION_LINE,
                "player": header.player,
                "language": header.language,
                "catalog_date": header.catalog_date,
                "protocol": header.protocol,
                "client": header.client,
            }
        )

    def record(self, measure: MeasurePayload, dropped: int = 0) -> None:
        """Écrit une mesure dès qu'elle existe.

        `dropped` est le total courant des mesures perdues, réécrit à chaque
        ligne. La relecture en garde le plus grand : un journal en ajout ne peut
        pas corriger une ligne déjà posée, mais il peut la répéter.
        """
        self._write(
            {
                "kind": _MEASURE_LINE,
                "quest": measure.quest,
                "seconds": measure.seconds,
                "quality": measure.quality,
                "confidence": measure.confidence,
                "dropped": dropped,
            }
        )

    def mark_sent(self, count: int, dropped: int = 0) -> None:
        """Note que les `count` premières mesures ont été présentées au serveur.

        C'est cette marque qui empêche le **double comptage** après un plantage :
        sans elle, relire le journal au démarrage suivant renverrait des mesures
        déjà reçues, qui gonfleraient les médianes sans que rien ne le signale.
        """
        self._write({"kind": _SENT_LINE, "count": count, "dropped": dropped})

    def discard(self) -> None:
        """Efface le journal, la session ayant été close proprement.

        Appelé après que le lot complet a été écrit en un bloc : le journal
        n'a plus rien à protéger. Un effacement impossible n'est pas grave, la
        marque `sent` empêche de toute façon de renvoyer deux fois.
        """
        with contextlib.suppress(OSError):
            self.path.unlink()

    def _write(self, record: dict[str, Any]) -> None:
        if self.broken:
            return
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fichier:
                    fichier.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            self.broken = True


@dataclass(frozen=True)
class JournalContents:
    """Ce qu'un journal relu contient, et ce qui reste à en envoyer."""

    #: Toutes les mesures du journal, celles déjà transmises comprises.
    payload: SessionPayload
    #: Combien de mesures ont déjà été présentées au serveur.
    sent: int = 0
    #: Le `dropped` déjà transmis, pour ne pas le compter deux fois.
    sent_dropped: int = 0

    @property
    def unsent(self) -> SessionPayload:
        """Le lot réduit à ce que le serveur n'a jamais vu."""
        return replace(
            self.payload,
            measures=self.payload.measures[self.sent :],
            dropped=max(0, self.payload.dropped - self.sent_dropped),
        )


def read_journal(path: Path) -> JournalContents | None:
    """Relit un journal, et rend `None` s'il n'a même pas son en-tête.

    Tolérante par construction : une ligne illisible est jetée, jamais le
    fichier entier. Un processus tué en pleine écriture laisse une dernière
    ligne tronquée, et refuser tout le journal pour elle reviendrait à perdre la
    session que ce journal existe précisément pour sauver.
    """
    try:
        brut = path.read_text(encoding="utf-8")
    except OSError:
        return None

    header: dict[str, Any] | None = None
    measures: list[MeasurePayload] = []
    dropped = 0
    sent = 0
    sent_dropped = 0
    for ligne in brut.splitlines():
        if not ligne.strip():
            continue
        try:
            record = json.loads(ligne)
        except ValueError:
            continue  # ligne tronquée par un arrêt brutal
        if not isinstance(record, dict):
            continue
        kind = record.get("kind")
        if kind == _SESSION_LINE and header is None:
            header = record
        elif kind == _MEASURE_LINE:
            try:
                measures.append(
                    MeasurePayload(
                        quest=str(record["quest"]),
                        seconds=float(record["seconds"]),
                        quality=str(record["quality"]),
                        confidence=float(record["confidence"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
            dropped = max(dropped, int(record.get("dropped", 0) or 0))
        elif kind == _SENT_LINE:
            with contextlib.suppress(TypeError, ValueError):
                sent = max(sent, int(record.get("count", 0) or 0))
                sent_dropped = max(sent_dropped, int(record.get("dropped", 0) or 0))

    if header is None:
        return None
    payload = SessionPayload(
        player=str(header.get("player", "")),
        language=str(header.get("language", "fr")),
        catalog_date=str(header.get("catalog_date", "")),
        measures=tuple(measures),
        protocol=int(header.get("protocol", PROTOCOL_VERSION)),
        client=str(header.get("client", "")),
        dropped=dropped,
    )
    # Un curseur plus grand que le nombre de mesures relues signalerait un
    # journal tronqué APRÈS sa marque. Le borner évite un `unsent` négatif, qui
    # se lirait comme « il reste tout à envoyer ».
    return JournalContents(
        payload=payload, sent=min(sent, len(measures)), sent_dropped=sent_dropped
    )


def orphan_journals(
    directory: Path, min_age: float = 0.0, now: float | None = None
) -> list[Path]:
    """Les journaux restés en place, donc les sessions jamais closes.

    Triés par nom, qui porte l'horodatage : la plus ancienne session repart en
    premier, ce qui donne un ordre stable et lisible dans les messages.

    ⚠️ `min_age` écarte les journaux touchés à l'instant, et ce n'est pas un
    détail de confort. Deux Rubin ouverts en même temps, ce qui n'a rien
    d'impossible, verraient chacun le journal VIVANT de l'autre comme un
    orphelin. Le second renverrait des mesures que le premier tient encore, et
    les deux curseurs s'ignorant, la même mesure partirait deux fois. Un journal
    qu'on n'a pas écrit depuis une minute, lui, n'appartient à personne.
    """
    instant = time.time() if now is None else now
    trouvés = []
    try:
        candidats = list(directory.glob(f"*{JOURNAL_SUFFIX}"))
    except OSError:
        return []
    for chemin in candidats:
        try:
            if not chemin.is_file():
                continue
            if min_age and instant - chemin.stat().st_mtime < min_age:
                continue
        except OSError:  # pragma: pas de couverture
            continue
        trouvés.append(chemin)
    return sorted(trouvés)


# ------------------------------------------------------------- envoi au fil de l'eau


class IncrementalSender:
    """N'envoie que les mesures que le serveur n'a jamais vues.

    ⚠️ **C'est la pièce qui empêche le double comptage.** Le curseur `sent`
    compte les mesures déjà présentées, et chaque envoi ne porte que la suite.
    Un lot renvoyé en entier gonflerait `samples` et fausserait les médianes
    sans laisser la moindre trace : rien ne distingue une mesure reçue deux fois
    de deux mesures réelles.

    `dropped` suit la même règle : chaque envoi ne porte que ce qui s'est perdu
    depuis le précédent, sans quoi le serveur additionnerait plusieurs fois le
    même total.
    """

    def __init__(
        self,
        url: str,
        base: SessionPayload,
        send: Callable[[SessionPayload, str], UploadResult] = send_session,
        journal: SessionJournal | None = None,
    ) -> None:
        self._url = url
        self._base = base
        self._send = send
        self._journal = journal
        self._sent = 0
        self._sent_dropped = 0
        # Le curseur est lu et avancé depuis deux fils : celui de l'envoi au fil
        # de l'eau, et celui du bilan de fin s'il n'a pas attendu le premier.
        # Sans verrou, les deux pourraient lire le même curseur et présenter deux
        # fois les mêmes mesures, ce que toute cette classe existe pour empêcher.
        self._lock = threading.Lock()

    @property
    def sent(self) -> int:
        """Combien de mesures ont déjà été présentées au serveur."""
        return self._sent

    def flush(
        self, measures: Sequence[MeasurePayload], dropped: int = 0
    ) -> UploadResult | None:
        """Envoie ce qui est nouveau, et rend `None` quand il n'y a rien de neuf.

        `measures` est la liste **complète** de la session, dans l'ordre. Le
        découpage se fait ici : l'appelant n'a pas à savoir où en est le
        curseur, et ne peut donc pas se tromper en le calculant lui-même.
        """
        with self._lock:
            fresh = tuple(measures[self._sent :])
            if not fresh:
                return None
            lot = replace(
                self._base,
                measures=fresh,
                dropped=max(0, dropped - self._sent_dropped),
            )
            result = self._send(lot, self._url)
            if result.ok or not result.answered:
                # Servi, ou sort inconnu. Dans les deux cas le curseur avance :
                # représenter un lot dont on ignore s'il est arrivé, c'est
                # risquer de fabriquer une mesure.
                self._sent += len(fresh)
                self._sent_dropped = max(self._sent_dropped, dropped)
                if self._journal is not None:
                    self._journal.mark_sent(self._sent, self._sent_dropped)
            return result


__all__ = [
    "JOURNAL_SUFFIX",
    "IncrementalSender",
    "JournalContents",
    "SessionJournal",
    "UploadResult",
    "orphan_journals",
    "read_journal",
    "save_session",
    "send_session",
]
