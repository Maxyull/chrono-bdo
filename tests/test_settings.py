"""Les réglages du joueur, et ce qu'ils ne doivent jamais permettre.

Le point qui commande tout ce fichier : un réglage faux doit produire une mesure
**manquante**, jamais une mesure fausse. C'est la seule raison pour laquelle ces
boutons peuvent être donnés au joueur.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rubin.capture import Rect
from rubin.settings import LANGUAGES, LIMITS, Settings, load, save


class TestValeursParDefaut:
    def test_reprennent_les_constantes_mesurees(self) -> None:
        # Les défauts ne sont pas choisis, ils sont relevés : ce sont les
        # valeurs qui tournent aujourd'hui en jeu.
        reglages = Settings()
        assert reglages.presence_threshold == 0.70
        assert reglages.poll_interval == 0.125
        assert reglages.upcoming_count == 5
        assert reglages.ui_scale == 1.0

    def test_les_zones_ne_sont_pas_figees_au_depart(self) -> None:
        # `None` veut dire « calcule-la depuis la fenêtre », jamais « pas de
        # zone ». Figer les zones calculées les empêcherait de suivre une
        # fenêtre qui change de taille.
        reglages = Settings()
        assert reglages.banner is None
        assert reglages.tracker is None


class TestLangueDuJeu:
    def test_le_francais_par_defaut(self) -> None:
        assert Settings().language == "fr"

    @pytest.mark.parametrize("langue", LANGUAGES)
    def test_les_deux_langues_survivent_a_l_ecriture(self, tmp_path: Path, langue: str) -> None:
        save(Settings(language=langue), tmp_path)
        assert load(tmp_path).language == langue

    def test_une_langue_inconnue_revient_au_francais(self) -> None:
        """Régression : une langue non prise en charge ratait TOUTES les quêtes.

        C'est la langue du **client de jeu**, pas celle de l'interface : un
        joueur francophone peut très bien jouer sur le client anglais. Elle
        décide sur quels noms le catalogue compare ce qui est lu à l'écran.

        S'y tromper ne rate donc pas une quête sur deux, il les rate toutes :
        aucun nom lu ne correspond à rien, et le bilan annonce « aucune quête
        mesurée » comme si le jeu n'avait rien montré.
        """
        assert Settings(language="de").normalised().language == "fr"

    def test_une_langue_du_mauvais_type_revient_au_francais(self, tmp_path: Path) -> None:
        (tmp_path / "reglages.json").write_text(
            json.dumps({"langue_du_jeu": 42}), encoding="utf-8"
        )
        assert load(tmp_path).language == "fr"


class TestBornes:
    @pytest.mark.parametrize("nom", list(LIMITS))
    def test_chaque_defaut_tient_dans_ses_bornes(self, nom: str) -> None:
        bas, haut, defaut = LIMITS[nom]
        assert bas <= defaut <= haut

    def test_ramene_une_valeur_trop_haute(self) -> None:
        borne = LIMITS["presence_threshold"][1]
        assert Settings(presence_threshold=5.0).normalised().presence_threshold == borne

    def test_ramene_une_valeur_trop_basse(self) -> None:
        """Régression : un seuil à zéro fait analyser tout le décor.

        Le seuil de présence décide si une image mérite une reconnaissance. À
        zéro, chaque capture la déclenche, huit fois par seconde, sur du décor
        de jeu. La file de lecture déborde, le fil ne suit plus, et les vrais
        bandeaux se perdent dans le flot.

        Le symptôme serait « aucune quête mesurée » avec le processeur à fond,
        et personne ne relierait cela à un curseur poussé au bout.
        """
        bas = LIMITS["presence_threshold"][0]
        assert Settings(presence_threshold=0.0).normalised().presence_threshold == bas

    def test_le_nombre_de_quetes_reste_entier(self) -> None:
        assert Settings(upcoming_count=7.9).normalised().upcoming_count == 7

    def test_zero_quete_affichee_est_permis(self) -> None:
        # C'est un choix légitime, pas une valeur aberrante : certains veulent
        # mesurer sans rien lire à l'écran.
        assert Settings(upcoming_count=0).normalised().upcoming_count == 0


class TestAllerRetour:
    def test_un_reglage_ecrit_puis_relu_est_identique(self, tmp_path: Path) -> None:
        origine = Settings(
            language="en",
            ui_scale=1.25,
            presence_threshold=0.65,
            poll_interval=0.2,
            upcoming_count=8,
            opacity=0.5,
            banner=Rect(2210, 1186, 349, 115),
            tracker=Rect(2090, 440, 340, 380),
        )

        save(origine, tmp_path)

        assert load(tmp_path) == origine

    def test_les_zones_non_choisies_ne_sont_pas_ecrites(self, tmp_path: Path) -> None:
        # Écrire les zones calculées les figerait, et un joueur qui change de
        # résolution ne comprendrait pas pourquoi elles ne suivent plus.
        save(Settings(), tmp_path)

        données = json.loads((tmp_path / "reglages.json").read_text(encoding="utf-8"))

        assert "zone_bandeau" not in données
        assert "zone_suivi" not in données

    def test_le_fichier_est_lisible_a_la_main(self, tmp_path: Path) -> None:
        # Les clés sont en français, comme tout ce qu'un humain lit dans ce
        # projet. Quelqu'un doit pouvoir corriger une valeur au bloc-notes.
        save(Settings(banner=Rect(10, 20, 30, 40)), tmp_path)

        texte = (tmp_path / "reglages.json").read_text(encoding="utf-8")

        assert "seuil_presence" in texte
        assert "zone_bandeau" in texte
        assert "largeur" in texte


class TestFichierAbime:
    def test_un_fichier_absent_rend_les_defauts(self, tmp_path: Path) -> None:
        # Cas normal du premier lancement, pas une anomalie.
        assert load(tmp_path) == Settings()

    def test_un_fichier_illisible_rend_les_defauts(self, tmp_path: Path) -> None:
        """Régression : un fichier abîmé ne doit pas empêcher de jouer.

        Ce fichier est modifiable au bloc-notes, et c'est voulu. Une virgule en
        trop suffit alors à le rendre illisible. S'arrêter là-dessus coûterait
        une session de jeu pour un caractère, alors que repartir des valeurs
        mesurées ne coûte que les réglages de ce joueur.
        """
        (tmp_path / "reglages.json").write_text("{ceci n'est pas du json", encoding="utf-8")

        assert load(tmp_path) == Settings()

    def test_une_valeur_du_mauvais_type_reprend_son_defaut(self, tmp_path: Path) -> None:
        (tmp_path / "reglages.json").write_text(
            json.dumps({"seuil_presence": "beaucoup", "cadence": 0.2}), encoding="utf-8"
        )

        relu = load(tmp_path)

        assert relu.presence_threshold == 0.70  # défaut repris
        assert relu.poll_interval == 0.2  # la clé valide est conservée

    def test_une_zone_plate_est_ignoree(self, tmp_path: Path) -> None:
        """Régression : une zone de hauteur nulle rendait le logiciel muet.

        Une zone de largeur ou de hauteur nulle capture une image vide, que la
        reconnaissance traite exactement comme un écran sans bandeau. Le
        symptôme est « aucune quête mesurée », sans le moindre indice, et il
        survit à un redémarrage puisque le réglage est enregistré.

        On revient donc au calcul d'origine, qui lui donne toujours une zone
        utilisable.
        """
        (tmp_path / "reglages.json").write_text(
            json.dumps({"zone_bandeau": {"x": 10, "y": 20, "largeur": 349, "hauteur": 0}}),
            encoding="utf-8",
        )

        assert load(tmp_path).banner is None

    def test_une_zone_sans_toutes_ses_clefs_est_ignoree(self, tmp_path: Path) -> None:
        (tmp_path / "reglages.json").write_text(
            json.dumps({"zone_suivi": {"x": 10, "y": 20}}), encoding="utf-8"
        )

        assert load(tmp_path).tracker is None

    def test_un_contenu_qui_n_est_pas_un_objet_rend_les_defauts(self, tmp_path: Path) -> None:
        (tmp_path / "reglages.json").write_text("[1, 2, 3]", encoding="utf-8")

        assert load(tmp_path) == Settings()


class TestPourquoiCEstSansDanger:
    def test_les_bornes_n_autorisent_aucun_seuil_certain(self) -> None:
        """Le seuil ne peut jamais atteindre 1, et c'est délibéré.

        Un seuil de 1,0 exigerait une corrélation parfaite. Mesuré en jeu, elle
        plafonne à 0,90 parce que le bandeau est semi-transparent et que le
        décor bouge derrière. Un curseur poussé au bout ne mesurerait donc plus
        jamais rien, sans que rien ne l'annonce.
        """
        assert LIMITS["presence_threshold"][1] < 1.0

    def test_la_cadence_ne_peut_pas_tomber_sous_une_seconde(self) -> None:
        # Le bandeau reste affiché plusieurs secondes. Une cadence plus lente
        # commencerait à en laisser passer entre deux captures.
        assert LIMITS["poll_interval"][1] <= 1.0
