"""Le moteur de mesure, derrière le bouton Démarrer.

La fenêtre sans ce fichier était un tableau de bord sans moteur : elle savait
tout afficher et ne mesurait rien, parce que rien ne lançait jamais la boucle.
Constaté à l'usage, une quête terminée ne produisait ni temps ni liste.

## Pourquoi un bouton, et pas un démarrage automatique

Parce que **capturer l'écran de quelqu'un doit être un geste qu'il fait**. Un
logiciel qui se met à photographier l'écran dès son ouverture décide à la place
de son utilisateur, et le fait qu'il n'en garde presque rien n'y change rien.

Le bouton dit aussi quelque chose d'utile au logiciel : « je commence les
quêtes ». Une session ouverte pendant qu'on est au marché mesurerait des
attentes, pas des quêtes.

## Les sous-chronos ne quittent jamais ce poste

Un bandeau « Objectif de quête accompli » ne borne aucune durée de quête, mais
il borne bien quelque chose : le temps passé sur un objectif. Une quête de cinq
minutes dont quatre sont du trajet n'est pas une quête de cinq minutes de
combat, et seul ce découpage le dit.

⚠️ **Ces temps ne sont PAS envoyés au serveur**, et c'est délibéré. Un bandeau
d'objectif raté ne produit pas un trou : il **fusionne deux segments en un**, et
donne un temps trop long qui a toutes les apparences d'une vraie mesure. Là où
une quête ratée donne un chiffre incomplet, un objectif raté donne un chiffre
faux, qui entrerait dans les médianes et n'en ressortirait jamais.

Ils sont donc affichés au joueur, qui voit sa propre partie et peut juger, et
ils s'arrêtent là. Ils vivent entièrement dans cette couche : ni le journal
d'événements, ni le lot envoyé ne les connaissent, ce qui rend la fuite
impossible par construction plutôt que par vigilance.

Le jour où l'on saura détecter un objectif manqué, ils pourront monter.

## Le fil ne touche jamais à l'affichage

Il dépose dans une file que la boucle de Tk vide depuis le bon fil. Un appel
direct à un composant depuis ici produirait des blocages qui n'arrivent qu'une
fois sur cent, donc jamais pendant qu'on regarde.

## Une session ne peut plus être perdue

Chaque mesure est écrite sur le disque **dès qu'elle existe**, dans un journal
en ajout, et envoyée dans la foulée si un serveur a été demandé. La fermeture
par la croix était déjà couverte ; le processus tué, Windows qui redémarre et le
logiciel qui plante ne le seront jamais par un événement de fermeture, parce
qu'aucun n'en envoie. Voir l'en-tête de `upload.py`.

⚠️ **L'envoi ne bloque jamais la mesure.** Il part dans un fil à part, un seul à
la fois, et n'emporte que les mesures jamais transmises. Le fil de mesure ne
l'attend pas, et un serveur lent ne fait donc rater aucun bandeau.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..capture import ScreenCapture, banner_region, find_game_window
from ..deferred import DeferredWatcher
from ..failures import BLIND, FailureStore
from ..protocol import MeasurePayload, PlayerIdentity, SessionPayload, build_session
from ..reading import BannerKind, RapidOcrReader
from ..reference import Catalog
from ..reference.source import catalog_date
from ..references import ReferenceClient
from ..settings import Settings
from ..timing import Quality, Timeline
from ..upload import (
    JOURNAL_SUFFIX,
    IncrementalSender,
    SessionJournal,
    orphan_journals,
    read_journal,
    save_session,
    send_session,
)
from ..watching import BannerWatcher
from .presentation import Watching

#: Âge minimal d'un journal pour être tenu pour orphelin, en secondes.
#: Voir `orphan_journals` : un journal écrit à l'instant est peut-être celui
#: d'un autre Rubin en train de mesurer, et le reprendre ferait partir deux fois
#: les mêmes mesures.
_ORPHAN_MIN_AGE: Final = 60.0

#: Silence au-delà duquel on garde une image de ce que la capture contient.
#:
#: Deux minutes : au-delà, un joueur qui enchaîne des quêtes a forcément vu
#: passer un bandeau, donc le silence cesse d'être ordinaire. En dessous, on
#: garderait des images pendant un trajet ou un combat, qui ne prouvent rien.
BLIND_AFTER: Final = 120.0

#: Et pas plus d'une image par cette durée, tant que le silence dure.
#:
#: Sans ce délai, une session aveugle écrirait huit images par seconde. Cinq
#: minutes suffisent : ce qu'on cherche est ce que la capture contient, pas son
#: évolution image par image.
BLIND_EVERY: Final = 300.0


@dataclass(frozen=True)
class Progress:
    """Ce que le moteur sait dire de la session en cours."""

    measured: int = 0
    exact: int = 0
    failed: int = 0
    elapsed: float = 0.0

    @property
    def deduced(self) -> int:
        return self.measured - self.exact


class MeasuringSession:
    """Mesure dans un fil séparé, et rend compte par une file de messages.

    `publish` est appelée depuis le fil de mesure : elle doit se contenter de
    déposer, jamais de dessiner.
    """

    def __init__(
        self,
        home: Path,
        catalog: Catalog,
        settings: Settings,
        publish: Callable[[str, Any], None],
        server: str | None = None,
    ) -> None:
        self._home = home
        self._catalog = catalog
        self._settings = settings
        self._publish = publish
        self._server = server
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sending: threading.Thread | None = None
        self.timeline: Timeline | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Lance la mesure. Rend `False` si le jeu est introuvable.

        Le jeu est cherché **au démarrage et non à l'ouverture de la fenêtre** :
        on ouvre souvent le logiciel avant de lancer le jeu, et refuser à ce
        moment-là obligerait à tout relancer dans le bon ordre.
        """
        if self.running:
            return True
        if find_game_window() is None:
            self._publish("etat", "jeu introuvable. Lancez Black Desert, puis réessayez.")
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout: float = 4.0) -> None:
        """Demande l'arrêt et attend que le fil ait fini son bilan."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ------------------------------------------------------------------ le fil

    def _run(self) -> None:
        window = find_game_window()
        if window is None:  # pragma: pas de couverture
            return
        langue = self._settings.language
        timeline = Timeline(catalog=self._catalog, language=langue)
        self.timeline = timeline
        references = ReferenceClient(self._server)
        failures = FailureStore(self._home / "echecs")
        failures.purge()
        # La purge a lieu au démarrage et non à l'arrêt : une session se termine
        # souvent par une fermeture brutale, et un ménage placé à la fin ne
        # serait jamais fait.

        # Même raisonnement, et c'est ce qui referme la boucle : les journaux
        # d'une session que rien n'a close sont repris ICI, avant que le nôtre
        # existe, donc jamais confondus avec lui.
        self._replay_orphans()
        journal, sender = self._open_journal()
        envoyables: list[MeasurePayload] = []
        écartées = 0

        # `zone_for` : voir l'en-tête de `RubinApp.zones`, même défaut. Une
        # session lancée en ligne de commande passait par le même vieux champ
        # sans condition de taille que la fenêtre graphique.
        zone = self._settings.zone_for(
            "banner", (window.width, window.height)
        ) or banner_region(window, ui_scale=self._settings.ui_scale)
        self._publish("etat", f"mesure en cours, zone {zone.width}x{zone.height}")
        self._publish("demarre", True)
        début = time.monotonic()
        dernière: tuple[int | None, int | None] = (None, None)
        # Sous-chronos : instant du dernier jalon de la quête en cours, et
        # numéro de l'objectif franchi. Remis à zéro à chaque quête
        # acceptée, effacés à chaque quête accomplie.
        jalon: float | None = None
        objectif = 0
        # Surveillance : combien de bandeaux avaient été vus au tour précédent,
        # et quand le compte a bougé pour la dernière fois. `None` tant qu'aucun
        # n'a jamais été vu, ce qui ne veut pas dire « il y a zéro seconde ».
        derniers_bandeaux = 0
        dernier_bandeau: float | None = None
        #: Instant de la dernière image gardée à l'aveugle. `None` : aucune.
        garde_aveugle: float | None = None

        try:
            reader = RapidOcrReader()
            with ScreenCapture(zone) as capture:
                watcher = BannerWatcher(capture, reader)
                with DeferredWatcher(
                    watcher,
                    reader,
                    interval=self._settings.poll_interval,
                    failures=failures,
                ) as deferred:
                    while not self._stop.is_set():
                        for reading, at in deferred.readings(timeout=0.5):
                            # L'instant retenu est celui de la capture, jamais
                            # celui de la lecture : sinon chaque mesure serait
                            # allongée de la durée de sa propre reconnaissance.
                            mesure = timeline.record(reading, at=at)
                            # Tout bandeau vu est annoncé, même ceux qui ne
                            # bornent aucune durée. Un bandeau d'objectif ne
                            # produit pas de mesure, et c'est voulu : il se
                            # passe PENDANT une quête. Mais se taire dessus
                            # laissait croire que rien n'était vu, alors que la
                            # lecture marchait parfaitement. Le silence ne
                            # distingue pas « je ne vois rien » de « je vois,
                            # ça ne se mesure pas ».
                            self._publish("vu", (reading, langue))

                            # Sous-chronos. Ils vivent ENTIÈREMENT ici, dans la
                            # couche d'affichage : ils n'entrent ni dans le
                            # journal d'événements, ni dans le lot envoyé. Voir
                            # l'en-tête du module pour la raison.
                            if reading.kind is BannerKind.ACCEPTED:
                                jalon, objectif = at, 0
                            elif reading.kind is BannerKind.COMPLETED:
                                jalon = None
                            elif reading.kind is BannerKind.OBJECTIVE_DONE and jalon:
                                objectif += 1
                                self._publish(
                                    "sous_chrono",
                                    (reading.quest_name, objectif, at - jalon),
                                )
                                jalon = at
                            if mesure is not None:
                                self._publish("mesure", (mesure, langue))
                                # Écrite sur le disque dès qu'elle existe, et
                                # avant tout ce qui pourrait échouer : un arrêt
                                # brutal peut tomber ici, et une partie ne se
                                # rejoue pas.
                                lot_mesure = MeasurePayload.from_measure(mesure)
                                if lot_mesure.is_plausible:
                                    envoyables.append(lot_mesure)
                                else:
                                    écartées += 1
                                perdues = timeline.dropped + écartées
                                if journal is not None and lot_mesure.is_plausible:
                                    journal.record(lot_mesure, dropped=perdues)
                                if sender is not None:
                                    # Après chaque quête terminée, jamais toutes
                                    # les X minutes : une quête finie est un
                                    # événement naturel et la mesure y est
                                    # complète, alors qu'un minuteur enverrait au
                                    # milieu d'une quête un lot à rattraper.
                                    self._send_apart(sender, envoyables, perdues)
                            ici = (timeline.current_chain, timeline.current_position)
                            if ici[0] is None:
                                # Le nom a été lu mais ne s'est résolu en aucune
                                # quête connue, donc la chaîne est inconnue et
                                # il n'y a pas de suite à montrer. Le DIRE :
                                # une liste vide et muette se lit comme « il n'y
                                # a rien après », alors que la vraie réponse est
                                # « je ne sais pas où tu es ».
                                self._publish("sans_chaine", reading.quest_name)
                            elif ici != dernière:
                                self._publish("position", (ici[0], ici[1], references))
                                dernière = ici
                            self._publish(
                                "progres",
                                Progress(
                                    measured=len(timeline.measures),
                                    exact=sum(
                                        1
                                        for m in timeline.measures
                                        if m.quality is Quality.EXACT
                                    ),
                                    failed=deferred.failed,
                                    elapsed=time.monotonic() - début,
                                ),
                            )
                        # Ce que la surveillance voit, à chaque tour de boucle,
                        # qu'il se soit passé quelque chose ou non. **Surtout
                        # quand il ne s'est rien passé** : c'est le silence qui
                        # a besoin d'être décrit, pas l'activité, qui se voit
                        # déjà dans la liste des quêtes faites.
                        vus = watcher.stats.banners_seen
                        if vus != derniers_bandeaux:
                            dernier_bandeau = time.monotonic()
                            derniers_bandeaux = vus
                        garde_aveugle = self._keep_if_blind(
                            watcher, failures, dernier_bandeau, début, garde_aveugle
                        )
                        self._publish(
                            "surveillance",
                            Watching(
                                frames=watcher.stats.frames,
                                banners_seen=vus,
                                reads=watcher.stats.reads,
                                failed=deferred.failed,
                                overflowed=deferred.overflowed,
                                repeated=watcher.stats.repeats,
                                elapsed=time.monotonic() - début,
                                since_banner=(
                                    None
                                    if dernier_bandeau is None
                                    else time.monotonic() - dernier_bandeau
                                ),
                            ),
                        )
                        if self._stop.is_set():
                            break
        except Exception as erreur:  # pragma: pas de couverture
            # Une panne ne doit pas emporter la fenêtre avec elle, ni faire
            # perdre ce qui a déjà été mesuré.
            self._publish("etat", f"mesure interrompue : {erreur}")
        finally:
            self._finish(timeline, time.monotonic() - début, journal, sender)
            self._publish("demarre", False)

    def _keep_if_blind(
        self,
        watcher: BannerWatcher,
        failures: FailureStore,
        last_banner: float | None,
        started: float,
        last_kept: float | None,
    ) -> float | None:
        """Garde une image quand la surveillance ne voit RIEN depuis longtemps.

        C'est la seule image que ce projet retient sans qu'elle ait franchi le
        seuil de présence, et c'est exactement pour cela qu'elle sert : toutes
        les autres disent pourquoi une lecture a échoué, celle-ci dit **ce que
        la capture contient** quand il n'y a même pas de lecture à échouer.

        Née de la séance du 5 août 2026. Une session a compté 4 832 images et
        zéro bandeau pendant qu'un témoin extérieur en voyait huit sur le même
        rectangle, à la même minute. Rien n'était gardé, donc rien ne permettait
        de savoir si la capture montrait le jeu, un écran figé, une autre
        fenêtre, ou le bon endroit sans bandeau. Cinq programmes de diagnostic
        écrits hors du logiciel n'ont pas suffi à trancher, et une seule image
        aurait suffi.

        ⚠️ Espacé, et c'est indispensable : sans le délai, une session qui ne
        voit rien écrirait huit images par seconde et remplirait le dossier de
        la même image en quelques minutes. L'empreinte évite le doublon sur le
        disque, pas la ligne de journal.

        Rend l'instant de la dernière image gardée, à repasser au tour suivant.
        """
        now = time.monotonic()
        silence = now - (last_banner if last_banner is not None else started)
        if silence < BLIND_AFTER:
            return last_kept
        if last_kept is not None and now - last_kept < BLIND_EVERY:
            return last_kept
        image = watcher.last_frame
        if image is None:  # pragma: pas de couverture
            return last_kept
        # Sans lignes : rien n'a été lu, et fabriquer une ligne vide ferait
        # passer ce cas pour une reconnaissance qui n'a rien trouvé, alors
        # qu'aucune reconnaissance n'a eu lieu.
        failures.keep(image, (), reason=BLIND)
        self._publish(
            "etat",
            f"aucun bandeau depuis {int(silence)} s : une image a été gardée dans echecs/",
        )
        return now

    # ------------------------------------------------------- le fil de l'eau

    def _open_journal(self) -> tuple[SessionJournal | None, IncrementalSender | None]:
        """Ouvre le journal de cette session, et l'envoyeur qui va avec.

        L'identité et la date du référentiel sont lues ici, une fois, plutôt
        qu'à l'arrêt : elles doivent figurer dans l'en-tête du journal, sans
        quoi une session interrompue serait relue sans savoir de qui ni de
        quand elle vient, donc inutilisable.

        Rend `(None, None)` si rien ne peut être ouvert. La mesure continue :
        perdre le filet de sécurité est un moindre mal devant perdre la session.
        """
        try:
            identity = PlayerIdentity.load_or_create(self._home / "identite")
            base = SessionPayload(
                player=identity.value,
                language=self._settings.language,
                catalog_date=catalog_date(self._settings.language),
            )
        except Exception as erreur:  # pragma: pas de couverture
            self._publish("etat", f"journal de session indisponible : {erreur}")
            return None, None
        journal = SessionJournal(
            self._home / "sessions" / f"session-{int(time.time())}{JOURNAL_SUFFIX}", base
        )
        if not self._server:
            # Rien n'est envoyé sans que le joueur l'ait demandé. Le journal,
            # lui, est purement local et n'a rien à demander à personne.
            return journal, None
        return journal, IncrementalSender(self._server, base, journal=journal)

    def _send_apart(
        self, sender: IncrementalSender, measures: Sequence[MeasurePayload], dropped: int
    ) -> None:
        """Envoie les mesures neuves depuis un fil à part.

        ⚠️ **Jamais depuis le fil de mesure.** Un serveur lent le bloquerait
        jusqu'à trente secondes, pendant lesquelles l'écran cesserait d'être
        regardé et un bandeau apparu dans l'intervalle serait perdu en silence.
        C'est exactement le défaut que la capture différée a corrigé, et le
        réintroduire par l'envoi serait un comble.

        Un seul envoi à la fois. Si le précédent court encore, celui-ci est
        abandonné sans regret : le suivant emportera de toute façon tout ce qui
        n'est pas encore parti, puisque l'envoyeur ne raisonne que sur son
        curseur.
        """
        if self._sending is not None and self._sending.is_alive():
            return
        instantané = tuple(measures)
        self._sending = threading.Thread(
            target=self._send_now, args=(sender, instantané, dropped), daemon=True
        )
        self._sending.start()

    def _send_now(
        self, sender: IncrementalSender, measures: Sequence[MeasurePayload], dropped: int
    ) -> None:
        résultat = sender.flush(measures, dropped)
        if résultat is not None and not résultat.ok:
            # Le dire, mais sans dramatiser : tout est sur le disque, et la
            # session continue de mesurer.
            self._publish("etat", f"envoi en cours de session impossible : {résultat.detail}")

    def _replay_orphans(self) -> None:
        """Reprend les journaux qu'aucun arrêt n'a fermés.

        La liste est relevée **tout de suite**, avant que le journal de cette
        session existe, pour qu'il ne s'y retrouve jamais. Le travail, lui, part
        dans un fil à part : un serveur injoignable retarderait sinon le début
        de la mesure de trente secondes, pendant que le joueur joue.
        """
        chemins = orphan_journals(self._home / "sessions", min_age=_ORPHAN_MIN_AGE)
        if not chemins:
            return
        threading.Thread(target=self._replay_now, args=(chemins,), daemon=True).start()

    def _replay_now(self, chemins: Sequence[Path]) -> None:
        """Relit chaque journal orphelin, le remet au format normal, et l'envoie.

        ⚠️ **Seules les mesures jamais transmises repartent.** Le journal porte
        le curseur de ce qui était déjà parti avant le plantage ; l'ignorer
        ferait recevoir deux fois les mêmes mesures, qui gonfleraient `samples`
        et entreraient dans les médianes sans que rien ne le signale.
        """
        for chemin in chemins:
            contenu = read_journal(chemin)
            if contenu is None:
                # Illisible jusque dans son en-tête. Le mettre de côté plutôt
                # que de le relire à chaque démarrage sans jamais rien en tirer,
                # et le garder plutôt que l'effacer : c'est une pièce à
                # conviction, pas un déchet.
                with contextlib.suppress(OSError):
                    chemin.rename(chemin.with_name(chemin.name + ".illisible"))
                continue

            if contenu.payload.measures:
                # La session interrompue existe désormais comme les autres, au
                # même format et dans le même dossier.
                with contextlib.suppress(OSError):
                    save_session(contenu.payload, chemin.with_suffix(".json"))

            reste = contenu.unsent
            if not reste.measures:
                self._forget(chemin)
                continue
            if not self._server:
                nombre = len(reste.measures)
                accord = "mesure" if nombre == 1 else "mesures"
                self._publish(
                    "etat",
                    f"{nombre} {accord} d'une session interrompue attendent, "
                    "elles partiront quand un serveur sera indiqué",
                )
                continue

            résultat = send_session(reste, self._server)
            if not résultat.ok and résultat.answered:
                # Le serveur a répondu et n'a rien enregistré : réessayer plus
                # tard ne peut fabriquer aucun doublon, donc le journal reste.
                self._publish(
                    "etat", f"session interrompue non envoyée, elle reste : {résultat.detail}"
                )
                continue
            self._forget(chemin)
            if résultat.ok:
                self._publish(
                    "etat",
                    f"session interrompue rattrapée : {résultat.stored} mesures envoyées",
                )

    def _forget(self, chemin: Path) -> None:
        with contextlib.suppress(OSError):
            chemin.unlink()

    # ------------------------------------------------------------- le bilan

    def _finish(
        self,
        timeline: Timeline,
        elapsed: float,
        journal: SessionJournal | None = None,
        sender: IncrementalSender | None = None,
    ) -> None:
        """Écrit le lot sur le disque, et envoie ce qui n'est pas encore parti.

        L'écriture a toujours lieu, l'envoi jamais tout seul. Une session
        mesurée puis perdue parce que le réseau a hoqueté serait irrattrapable :
        la partie, elle, ne se rejoue pas.

        ⚠️ **Ce n'est plus le lot entier qui part ici.** Les mesures envoyées au
        fil de l'eau ne repartent pas : les renvoyer les compterait deux fois,
        et un `samples` gonflé ne se distingue jamais de vraies mesures.
        """
        if self._sending is not None:
            # Laisser un envoi en cours se terminer, pour que le curseur soit à
            # jour avant le dernier tour.
            self._sending.join(timeout=5.0)
            self._sending = None
        if not timeline.measures:
            self._publish("etat", f"arrêtée, aucune quête mesurée en {int(elapsed)} s")
            if journal is not None:
                journal.discard()
            return
        try:
            identity = PlayerIdentity.load_or_create(self._home / "identite")
            lot = build_session(
                timeline,
                player=identity.value,
                catalog_date=catalog_date(self._settings.language),
                language=self._settings.language,
            )
            écrit = save_session(
                lot, self._home / "sessions" / f"session-{int(time.time())}.json"
            )
        except Exception as erreur:  # pragma: pas de couverture
            self._publish("etat", f"mesures gardées en mémoire, écriture impossible : {erreur}")
            return

        message = f"arrêtée, {len(timeline.measures)} quêtes mesurées, lot écrit dans {écrit}"
        if sender is not None:
            résultat = sender.flush(lot.measures, lot.dropped)
            if résultat is None:
                message += " — tout était déjà envoyé au fil de l'eau"
            elif résultat.ok:
                message += f" — envoyé, {résultat.stored} enregistrées"
            else:
                message += f" — envoi impossible, le lot est conservé ({résultat.detail})"
        elif self._server:
            # Pas de journal, donc rien n'est parti pendant la session : le lot
            # entier peut partir sans risque de doublon.
            résultat = send_session(lot, self._server)
            message += (
                f" — envoyé, {résultat.stored} enregistrées"
                if résultat.ok
                else f" — envoi impossible, le lot est conservé ({résultat.detail})"
            )
        if journal is not None:
            # Le bloc complet est sur le disque : le journal n'a plus rien à
            # protéger.
            journal.discard()
        self._publish("etat", message)
