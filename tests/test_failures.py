"""Ce qui rate doit laisser une trace.

Jusqu'ici une image dont la lecture ne donnait aucun bandeau était abandonnée
dans la boucle, sans rien laisser derrière elle. Une session qui ne mesurait
rien ne disait donc pas pourquoi, et les cinq défauts connus du projet ont tous
dû être trouvés à la main, en jouant.

Les images de ces tests sont de **vraies** captures du bandeau de quête, et les
lignes sont de vraies sorties de reconnaissance, défauts compris.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rubin.capture import GrayFrame
from rubin.deferred import DeferredWatcher
from rubin.failures import (
    ARCHIVE_MAX_BYTES,
    DESTINATIONS,
    JOURNAL_NAME,
    FailureStore,
    find_destination,
    fingerprint,
    larger_than,
)
from rubin.watching import BannerWatcher

DATA = Path(__file__).parent / "data"

#: Sortie réelle de la reconnaissance sur un bandeau de nuit : rien du tout.
#: Ce n'est pas un cas limite inventé, c'est le cas mesuré.
RIEN_LU: list[tuple[str, float]] = []

#: Sortie réelle sur un bandeau lisible, avec ses défauts : accents perdus,
#: ponctuation recollée au mot suivant.
LU_MAIS_REFUSE: list[tuple[str, float]] = [
    ("Objectif", 0.91),
    ("Parlez a Jeron,la tacticienne", 0.88),
]


@pytest.fixture(scope="session")
def banner() -> GrayFrame:
    with Image.open(DATA / "banner_present.png") as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


@pytest.fixture()
def store(tmp_path: Path) -> FailureStore:
    return FailureStore(tmp_path / "echecs")


class TestEmpreinte:
    def test_la_meme_image_donne_la_meme_empreinte(self, banner: GrayFrame) -> None:
        assert fingerprint(banner) == fingerprint(banner.copy())

    def test_deux_images_differentes_donnent_deux_empreintes(self, banner: GrayFrame) -> None:
        autre = banner.copy()
        autre[0, 0] = 255 - int(autre[0, 0])
        assert fingerprint(banner) != fingerprint(autre)

    def test_une_image_recadree_ne_passe_pas_pour_l_originale(self, banner: GrayFrame) -> None:
        # La forme entre dans l'empreinte : deux tableaux de tailles
        # différentes peuvent porter les mêmes octets une fois aplatis.
        assert fingerprint(banner) != fingerprint(banner[:50])


class TestRetention:
    def test_garde_l_image_et_les_lignes_lues(self, store: FailureStore, banner: GrayFrame) -> None:
        chemin = store.keep(banner, LU_MAIS_REFUSE)

        assert chemin is not None
        assert chemin.is_file()
        entrees = _journal(store)
        assert len(entrees) == 1
        # Les deux moitiés du diagnostic : ce qui a été vu, et ce qui en a été
        # lu. Sans les lignes, un refus d'analyse ressemble à un défaut d'image.
        assert entrees[0]["lignes"] == [
            {"texte": "Objectif", "score": 0.91},
            {"texte": "Parlez a Jeron,la tacticienne", "score": 0.88},
        ]
        assert entrees[0]["hauteur"] == banner.shape[0]
        assert entrees[0]["largeur"] == banner.shape[1]

    def test_garde_aussi_ce_qui_n_a_produit_aucune_ligne(
        self, store: FailureStore, banner: GrayFrame
    ) -> None:
        """Régression : le panneau de nuit ne laissait aucune trace.

        Sans fond opaque, le panneau de suivi tombe à une luminance de 19 sur
        255 la nuit, et la reconnaissance n'y trouve **aucune** ligne. C'est
        justement le cas où il n'y a rien à consigner sauf l'image, et c'est
        celui qui disparaissait le plus complètement : pas de mesure, pas de
        texte, pas de fichier, donc rien à regarder le lendemain.

        Une liste de lignes vide doit produire une entrée, pas un silence.
        """
        nuit = (banner.astype(np.float32) * (19.0 / float(banner.mean()))).astype(np.uint8)
        assert round(float(nuit.mean())) == 19  # la luminance mesurée en jeu

        chemin = store.keep(nuit, RIEN_LU)

        assert chemin is not None
        entrees = _journal(store)
        assert len(entrees) == 1
        assert entrees[0]["lignes"] == []

    def test_n_ecrit_pas_deux_fois_la_meme_image_mais_compte_les_deux_echecs(
        self, store: FailureStore, banner: GrayFrame
    ) -> None:
        # Le dédoublonnage porte sur l'image, pas sur l'échec : c'est la
        # fréquence d'un défaut qui dit s'il est isolé ou s'il plombe la
        # session, et une ligne de journal coûte quelques dizaines d'octets.
        premier = store.keep(banner, RIEN_LU)
        second = store.keep(banner, RIEN_LU)

        assert premier == second
        assert len(list(store.directory.glob("*.webp"))) == 1
        assert len(_journal(store)) == 2
        assert store.stats().images == 1
        assert store.stats().entries == 2

    def test_l_image_gardee_se_relit_a_l_identique(
        self, store: FailureStore, banner: GrayFrame
    ) -> None:
        # Le WebP est sans perte exprès : ces images servent à rejouer la
        # reconnaissance quand elle s'améliore, et une comparaison faite sur des
        # pixels altérés ne prouverait rien sur la vraie capture.
        chemin = store.keep(banner, RIEN_LU)
        assert chemin is not None
        with Image.open(chemin) as relue:
            assert np.array_equal(np.asarray(relue.convert("L"), dtype=np.uint8), banner)


class TestPurge:
    def test_efface_ce_qui_a_depasse_la_retention(
        self, tmp_path: Path, banner: GrayFrame
    ) -> None:
        store = FailureStore(tmp_path / "echecs", retention_days=90)
        chemin = store.keep(banner, RIEN_LU)
        assert chemin is not None
        _vieillir(chemin, jours=91)

        assert store.purge() == 1
        assert not chemin.exists()

    def test_garde_ce_qui_est_encore_dans_la_retention(
        self, tmp_path: Path, banner: GrayFrame
    ) -> None:
        store = FailureStore(tmp_path / "echecs", retention_days=90)
        chemin = store.keep(banner, RIEN_LU)
        assert chemin is not None
        _vieillir(chemin, jours=89)

        assert store.purge() == 0
        assert chemin.exists()

    def test_efface_les_plus_anciennes_quand_le_plafond_est_atteint(
        self, tmp_path: Path, banner: GrayFrame
    ) -> None:
        store = FailureStore(tmp_path / "echecs", max_bytes=10**9)
        vieille = store.keep(banner, RIEN_LU)
        recente = store.keep(_variante(banner, 7), RIEN_LU)
        assert vieille is not None and recente is not None
        _vieillir(vieille, jours=10)
        # Un plafond qui laisse passer une image mais pas deux, calé sur la
        # taille réellement écrite plutôt que sur une estimation.
        store = FailureStore(tmp_path / "echecs", max_bytes=recente.stat().st_size + 1)

        store.purge()

        # Un échec d'aujourd'hui décrit la version qui tourne ; un échec de
        # l'an dernier décrit une reconnaissance qui n'existe plus.
        assert not vieille.exists()
        assert recente.exists()

    def test_ne_supprime_jamais_le_dernier_echec(self, tmp_path: Path, banner: GrayFrame) -> None:
        """Régression : un plafond trop bas vidait le dossier entièrement.

        La purge effaçait du plus ancien au plus récent tant que le total
        dépassait le plafond. Avec un plafond plus petit qu'un seul fichier, la
        boucle allait jusqu'au bout et ne laissait rien.

        Le résultat était un dossier vide, indiscernable d'une session sans
        aucun échec. C'est précisément la confusion que ce module existe pour
        supprimer, et elle serait revenue par la porte du ménage.
        """
        store = FailureStore(tmp_path / "echecs", max_bytes=1)
        seul = store.keep(banner, RIEN_LU)
        assert seul is not None

        store.purge()

        assert seul.exists()

    def test_ne_se_plaint_pas_d_un_dossier_qui_n_existe_pas(self, tmp_path: Path) -> None:
        store = FailureStore(tmp_path / "jamais-cree")
        assert store.purge() == 0
        assert store.stats().images == 0


class TestArchive:
    def test_rassemble_les_images_et_le_journal(
        self, store: FailureStore, banner: GrayFrame, tmp_path: Path
    ) -> None:
        store.keep(banner, LU_MAIS_REFUSE)
        store.keep(_variante(banner, 3), RIEN_LU)

        result = store.package(tmp_path / "envoi.zip")

        assert result is not None
        assert result.images == 2
        assert result.left_out == 0
        with zipfile.ZipFile(result.path) as archive:
            noms = archive.namelist()
        assert JOURNAL_NAME in noms
        assert sum(1 for nom in noms if nom.endswith(".webp")) == 2

    def test_ne_fabrique_rien_quand_il_n_y_a_rien(
        self, store: FailureStore, tmp_path: Path
    ) -> None:
        # Proposer d'envoyer un fichier vide ferait perdre son temps à celui
        # qui l'envoie comme à celui qui le reçoit.
        assert store.package(tmp_path / "envoi.zip") is None
        assert not (tmp_path / "envoi.zip").exists()

    def test_tient_dans_la_limite_et_compte_ce_qu_elle_laisse_dehors(
        self, store: FailureStore, banner: GrayFrame, tmp_path: Path
    ) -> None:
        """Régression : une archive trop lourde est refusée à l'envoi.

        La destination proposée en premier est une issue GitHub, dont la limite
        est de 25 Mo pour une pièce jointe qui n'est ni une image ni une vidéo.
        Une vignette de bandeau pèse 20 Ko, mesuré sur trois captures réelles en
        2559x1439 : 17,1, 17,8 et 22,8. Le plafond tient donc environ mille deux
        cents échecs, mais une reconnaissance qui s'effondre peut en produire
        davantage, et l'archive serait alors fabriquée pour rien.

        Elle se borne, et elle **dit** ce qu'elle laisse dehors : une troncature
        qui se tait se lit comme un inventaire complet.
        """
        for décalage in range(4):
            store.keep(_variante(banner, décalage), RIEN_LU)

        # Un plafond volontairement minuscule : deux images n'y tiennent pas.
        result = store.package(tmp_path / "envoi.zip", max_bytes=30_000)

        assert result is not None
        assert result.images + result.left_out == 4
        assert result.left_out > 0
        assert result.bytes <= 30_000

    def test_la_limite_par_defaut_est_celle_de_github(self) -> None:
        assert ARCHIVE_MAX_BYTES == 25 * 1024 * 1024

    def test_dit_ce_qu_il_aurait_fallu_pour_tout_emporter(
        self, store: FailureStore, banner: GrayFrame, tmp_path: Path
    ) -> None:
        for décalage in range(4):
            store.keep(_variante(banner, décalage), RIEN_LU)

        result = store.package(tmp_path / "envoi.zip", max_bytes=30_000)

        assert result is not None
        # Le chiffre sert à désigner une destination plus large, au lieu de
        # laisser quelqu'un devant une troncature sans porte de sortie.
        assert result.needed > 30_000
        assert larger_than(result.needed) is not None


class TestDestinations:
    def test_vont_du_plus_contraint_au_plus_large(self) -> None:
        plafonds = [candidate.max_bytes for candidate in DESTINATIONS]
        assert plafonds == sorted(plafonds)

    def test_la_plus_contrainte_est_celle_ou_l_archive_sert(self) -> None:
        # GitHub d'abord : c'est le seul endroit où le fichier se retrouve
        # attaché au rapport qui le décrit, au lieu d'être un lien qui expire.
        assert DESTINATIONS[0].key == "github"
        assert DESTINATIONS[0].max_bytes == ARCHIVE_MAX_BYTES

    @pytest.mark.parametrize("key", [candidate.key for candidate in DESTINATIONS])
    def test_chaque_cle_se_retrouve(self, key: str) -> None:
        assert find_destination(key).key == key

    def test_designe_la_premiere_destination_assez_large(self) -> None:
        github, catbox, pixeldrain = DESTINATIONS
        assert larger_than(1024) is github
        assert larger_than(github.max_bytes + 1) is catbox
        assert larger_than(catbox.max_bytes + 1) is pixeldrain

    def test_seul_github_demande_un_compte(self) -> None:
        # Le vrai coût pour quelqu'un qui rend service et n'a rien demandé.
        sans_compte = [c.key for c in DESTINATIONS if not c.account]
        assert sans_compte == ["catbox", "pixeldrain"]


class TestFilDiffere:
    def test_une_lecture_ratee_laisse_une_trace(self, banner: GrayFrame, tmp_path: Path) -> None:
        """Régression : la lecture ratée était jetée sur place, en silence.

        Dans `DeferredWatcher.readings`, un `parse_banner` qui rendait `None`
        faisait simplement passer à l'image suivante. L'image partait avec, et
        avec elle la seule preuve de ce que le logiciel avait vu.

        Le cas reproduit ici est celui de la nuit : le bandeau est bien présent
        à l'écran, la boucle juge donc l'image digne d'être lue, mais la
        reconnaissance n'en tire aucune ligne. Deux pannes très différentes
        donnaient jusqu'ici le même écran vide en fin de session, « aucune quête
        mesurée », sans moyen de les distinguer.
        """
        store = FailureStore(tmp_path / "echecs")
        source = _SourceFixe(banner)
        reader = _LecteurAveugle()
        deferred = DeferredWatcher(
            BannerWatcher(source, reader),
            reader,
            interval=0.01,
            failures=store,
        )

        with deferred:
            for _ in deferred.readings(timeout=0.5):  # pragma: pas de couverture
                pytest.fail("aucun bandeau ne devait sortir d'une lecture vide")

        assert deferred.failed >= 1
        assert store.stats().images == 1
        assert _journal(store)[0]["lignes"] == []

    def test_compte_les_echecs_meme_sans_dossier(self, banner: GrayFrame) -> None:
        # Le compte seul répond déjà à « pourquoi cette session n'a rien
        # mesuré », et il ne coûte rien quand la rétention est absente.
        source = _SourceFixe(banner)
        reader = _LecteurAveugle()
        deferred = DeferredWatcher(BannerWatcher(source, reader), reader, interval=0.01)

        with deferred:
            for _ in deferred.readings(timeout=0.5):  # pragma: pas de couverture
                pytest.fail("aucun bandeau ne devait sortir d'une lecture vide")

        assert deferred.failed >= 1


class _SourceFixe:
    """Rend toujours la même image."""

    def __init__(self, frame: GrayFrame) -> None:
        self._frame = frame

    def grab_gray(self) -> GrayFrame:
        return self._frame


class _LecteurAveugle:
    """Ne lit rien, comme la reconnaissance sur un panneau de nuit."""

    def read(self, image: GrayFrame) -> list[tuple[str, float]]:
        return []


def _journal(store: FailureStore) -> list[dict[str, object]]:
    lignes = (store.directory / JOURNAL_NAME).read_text(encoding="utf-8").splitlines()
    return [json.loads(ligne) for ligne in lignes if ligne.strip()]


def _variante(frame: GrayFrame, décalage: int) -> GrayFrame:
    """Une image différente de l'originale, donc d'empreinte différente."""
    copie = frame.copy()
    copie[décalage, décalage] = 255 - int(copie[décalage, décalage])
    return copie


def _vieillir(path: Path, jours: int) -> None:
    """Recule la date du fichier, pour éprouver la purge sans attendre."""
    import os

    ancien = path.stat().st_mtime - jours * 86400
    os.utime(path, (ancien, ancien))
