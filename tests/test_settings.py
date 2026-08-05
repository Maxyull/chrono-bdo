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
from rubin.settings import LANGUAGES, LIMITS, ZONE_NAMES, Settings, ZoneEntry, load, save

#: Les deux tailles de fenêtre de Maxime : son plein écran, et son fenêtré.
PLEIN_ECRAN = (2560, 1440)
FENETRE = (1920, 1080)

#: La zone du bandeau telle qu'elle est tracée en plein écran.
BANDEAU = Rect(2210, 1186, 349, 115)


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
        assert reglages.choice is None
        assert reglages.zones == ()


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

    def test_la_fenetre_est_opaque_par_defaut(self) -> None:
        """Régression : la fenêtre était livrée translucide, donc illisible.

        À 0,92 d'opacité, le jeu traversait le texte. Sur un décor clair,
        mouvant et texturé, on ne distinguait plus les lettres. La transparence
        est un confort, la lisibilité est la fonction : on ne sacrifie pas la
        seconde à la première par défaut.

        Le curseur reste là pour qui la veut, mais son plancher n'est pas zéro :
        une fenêtre invisible qu'on ne retrouve plus est un piège dont on ne
        sort qu'en supprimant le fichier de réglages.
        """
        assert Settings().opacity == 1.0
        assert LIMITS["opacity"][2] == 1.0
        assert LIMITS["opacity"][0] > 0

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
            choice=Rect(639, 359, 1280, 720),
        )

        save(origine, tmp_path)

        assert load(tmp_path) == origine

    def test_la_zone_de_choix_tracee_survit_a_l_ecriture(self, tmp_path: Path) -> None:
        """Régression attendue : c'est la zone qu'il FAUT tracer à la main.

        Son calcul d'origine est une estimation, pas une mesure : aucune
        capture du panneau de choix n'existe. Le tracé du joueur est donc, pour
        cette zone-là, la seule source fiable, et le perdre au redémarrage
        reviendrait à lui redemander à chaque session la mesure que le projet
        n'a pas.
        """
        save(Settings(choice=Rect(700, 400, 1200, 640)), tmp_path)

        assert load(tmp_path).choice == Rect(700, 400, 1200, 640)

    def test_les_zones_non_choisies_ne_sont_pas_ecrites(self, tmp_path: Path) -> None:
        # Écrire les zones calculées les figerait, et un joueur qui change de
        # résolution ne comprendrait pas pourquoi elles ne suivent plus.
        save(Settings(), tmp_path)

        données = json.loads((tmp_path / "reglages.json").read_text(encoding="utf-8"))

        assert "zone_bandeau" not in données
        assert "zone_suivi" not in données
        assert "zone_choix" not in données

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

    def test_une_zone_de_choix_plate_est_ignoree(self, tmp_path: Path) -> None:
        # Même traitement que les deux autres : on revient au calcul d'origine,
        # même s'il n'est ici qu'une estimation, plutôt que de garder un
        # rectangle qui capture une image vide à chaque lecture.
        (tmp_path / "reglages.json").write_text(
            json.dumps({"zone_choix": {"x": 10, "y": 20, "largeur": 0, "hauteur": 720}}),
            encoding="utf-8",
        )

        assert load(tmp_path).choice is None

    def test_un_contenu_qui_n_est_pas_un_objet_rend_les_defauts(self, tmp_path: Path) -> None:
        (tmp_path / "reglages.json").write_text("[1, 2, 3]", encoding="utf-8")

        assert load(tmp_path) == Settings()


class TestZonesParTailleDeFenetre:
    """Une zone n'a de sens qu'avec la taille de fenêtre où elle a été tracée.

    C'est le point qui commande tout ce bloc, et il découle du principe du
    projet : une zone appliquée à la mauvaise résolution ne mesure rien, mais
    elle le fait en silence **et** de façon persistante, puisqu'elle est
    enregistrée. C'est le seul réglage capable de rester faux d'une session à
    l'autre sans que rien ne l'annonce.
    """

    def test_la_zone_tracee_vaut_pour_sa_taille_de_fenetre(self) -> None:
        reglages = Settings().with_zone("banner", PLEIN_ECRAN, BANDEAU)

        assert reglages.zone_for("banner", PLEIN_ECRAN) == BANDEAU

    def test_la_zone_ne_vaut_pas_pour_une_autre_taille(self) -> None:
        """Régression : passer en fenêtré gardait une zone devenue fausse.

        Le cas réel est celui de n'importe quel joueur qui alterne : le bandeau
        de quête est ancré au coin bas-droit de la fenêtre du jeu, donc le
        rectangle tracé en 2560 x 1440 tombe en plein décor dès que la fenêtre
        fait 1920 x 1080. Rubin capture bien une image, elle ne contient
        simplement plus de titre de quête, et le bilan annonce « aucune quête
        mesurée » sans pouvoir dire pourquoi.

        Le pire n'était pas la session perdue, c'était qu'elle se répète :
        le réglage était enregistré, donc il survivait au redémarrage.

        `None` remet le calcul d'origine dans la boucle, et lui suit la fenêtre.
        """
        reglages = Settings().with_zone("banner", PLEIN_ECRAN, BANDEAU)

        assert reglages.zone_for("banner", FENETRE) is None

    def test_rien_n_est_mis_a_l_echelle_d_une_taille_a_l_autre(self) -> None:
        # Un rectangle multiplié par le rapport des résolutions serait une zone
        # inventée : l'interface du jeu garde sa taille en pixels quand la
        # résolution change, donc la mise à l'échelle serait fausse en plus
        # d'être devinée. On préfère la mesure manquante.
        reglages = Settings().with_zone("tracker", PLEIN_ECRAN, Rect(2090, 440, 340, 380))

        assert reglages.zone_for("tracker", (1280, 720)) is None
        assert reglages.zone_for("tracker", (2559, 1439)) is None

    def test_les_trois_zones_ont_chacune_leur_table(self) -> None:
        reglages = Settings()
        for nom in ZONE_NAMES:
            reglages = reglages.with_zone(nom, PLEIN_ECRAN, Rect(10, 20, 30, 40))

        assert [reglages.zone_for(nom, PLEIN_ECRAN) for nom in ZONE_NAMES] == [
            Rect(10, 20, 30, 40)
        ] * 3

    def test_deux_tailles_cohabitent_sans_se_chasser(self) -> None:
        # C'est tout l'intérêt de la table : le joueur qui alterne entre plein
        # écran et fenêtré retrouve chaque fois son tracé, sans le refaire.
        reglages = (
            Settings()
            .with_zone("banner", PLEIN_ECRAN, BANDEAU)
            .with_zone("banner", FENETRE, Rect(1570, 890, 349, 115))
        )

        assert reglages.zone_for("banner", PLEIN_ECRAN) == BANDEAU
        assert reglages.zone_for("banner", FENETRE) == Rect(1570, 890, 349, 115)

    def test_retracer_a_la_meme_taille_remplace(self) -> None:
        reglages = (
            Settings()
            .with_zone("banner", PLEIN_ECRAN, BANDEAU)
            .with_zone("banner", PLEIN_ECRAN, Rect(2200, 1180, 360, 120))
        )

        assert reglages.zone_for("banner", PLEIN_ECRAN) == Rect(2200, 1180, 360, 120)
        assert len(reglages.zones) == 1

    def test_une_zone_s_oublie_sans_toucher_aux_autres_tailles(self) -> None:
        reglages = (
            Settings()
            .with_zone("banner", PLEIN_ECRAN, BANDEAU)
            .with_zone("banner", FENETRE, Rect(1570, 890, 349, 115))
            .with_zone("banner", FENETRE, None)
        )

        assert reglages.zone_for("banner", FENETRE) is None
        assert reglages.zone_for("banner", PLEIN_ECRAN) == BANDEAU

    def test_une_zone_plate_n_entre_pas_dans_la_table(self) -> None:
        # Même refus que pour la zone sans clé, et pour la même raison : elle
        # capturerait une image vide, que la reconnaissance traite comme un
        # écran sans bandeau.
        reglages = Settings().with_zone("banner", PLEIN_ECRAN, Rect(10, 20, 349, 0))

        assert reglages.zone_for("banner", PLEIN_ECRAN) is None

    def test_une_taille_de_fenetre_absurde_n_entre_pas_dans_la_table(self) -> None:
        reglages = Settings(zones=(ZoneEntry("banner", (0, 1440), BANDEAU),)).normalised()

        assert reglages.zones == ()


class TestZonesEcritesEtRelues:
    def test_une_table_ecrite_puis_relue_est_identique(self, tmp_path: Path) -> None:
        origine = (
            Settings(language="en")
            .with_zone("banner", PLEIN_ECRAN, BANDEAU)
            .with_zone("tracker", PLEIN_ECRAN, Rect(2090, 440, 340, 380))
            .with_zone("choice", FENETRE, Rect(480, 270, 960, 540))
        )

        save(origine, tmp_path)

        assert load(tmp_path) == origine

    def test_le_fichier_dit_a_quel_ecran_chaque_zone_se_rapporte(self, tmp_path: Path) -> None:
        # Le fichier se corrige au bloc-notes, donc la clé doit se lire. Une
        # table dont les clés seraient opaques serait aussi muette que l'unique
        # rectangle qu'elle remplace.
        save(Settings().with_zone("banner", PLEIN_ECRAN, BANDEAU), tmp_path)

        données = json.loads((tmp_path / "reglages.json").read_text(encoding="utf-8"))

        assert données["zones_par_taille"]["2560x1440"]["zone_bandeau"] == {
            "x": 2210,
            "y": 1186,
            "largeur": 349,
            "hauteur": 115,
        }

    def test_aucune_table_n_est_ecrite_tant_qu_aucune_zone_n_est_tracee(
        self, tmp_path: Path
    ) -> None:
        save(Settings(), tmp_path)

        texte = (tmp_path / "reglages.json").read_text(encoding="utf-8")

        assert "zones_par_taille" not in texte


class TestTableAbimee:
    """Le fichier est traité comme hostile, la table comme le reste."""

    def test_une_table_qui_n_est_pas_un_objet_est_ignoree(self, tmp_path: Path) -> None:
        (tmp_path / "reglages.json").write_text(
            json.dumps({"zones_par_taille": [1, 2, 3], "cadence": 0.2}), encoding="utf-8"
        )

        relu = load(tmp_path)

        assert relu.zones == ()
        assert relu.poll_interval == 0.2  # le reste du fichier survit

    @pytest.mark.parametrize("clé", ["2560", "2560x", "grand", "2560x1440x1", "0x1440", "-1x1440"])
    def test_une_taille_illisible_fait_sauter_ses_zones_seules(
        self, tmp_path: Path, clé: str
    ) -> None:
        """Une clé qu'on ne sait pas lire ne promeut aucune zone.

        C'est le seul endroit de ce module où une erreur pourrait fabriquer un
        réglage FAUX plutôt que manquant : deviner la taille de fenêtre d'un
        rectangle, ou l'appliquer faute de mieux, reviendrait à le poser sur un
        écran qu'il ne visait pas.
        """
        (tmp_path / "reglages.json").write_text(
            json.dumps(
                {
                    "zones_par_taille": {
                        clé: {"zone_bandeau": {"x": 1, "y": 2, "largeur": 3, "hauteur": 4}},
                        "1920x1080": {"zone_suivi": {"x": 5, "y": 6, "largeur": 7, "hauteur": 8}},
                    }
                }
            ),
            encoding="utf-8",
        )

        relu = load(tmp_path)

        assert relu.zones == (ZoneEntry("tracker", FENETRE, Rect(5, 6, 7, 8)),)

    def test_une_zone_plate_dans_la_table_est_ignoree(self, tmp_path: Path) -> None:
        (tmp_path / "reglages.json").write_text(
            json.dumps(
                {
                    "zones_par_taille": {
                        "2560x1440": {
                            "zone_bandeau": {"x": 1, "y": 2, "largeur": 349, "hauteur": 0}
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        assert load(tmp_path).zone_for("banner", PLEIN_ECRAN) is None

    def test_un_nom_de_zone_inconnu_est_ignore(self, tmp_path: Path) -> None:
        # Rubin n'a que trois surfaces lisibles. Une quatrième inventée à la
        # main ne serait jamais lue, mais serait réécrite à chaque
        # enregistrement, ce qui la ferait passer pour un réglage vivant.
        (tmp_path / "reglages.json").write_text(
            json.dumps(
                {
                    "zones_par_taille": {
                        "2560x1440": {"zone_minimap": {"x": 1, "y": 2, "largeur": 3, "hauteur": 4}}
                    }
                }
            ),
            encoding="utf-8",
        )

        assert load(tmp_path).zones == ()

    def test_une_table_abimee_n_empeche_pas_de_demarrer(self, tmp_path: Path) -> None:
        (tmp_path / "reglages.json").write_text(
            json.dumps({"zones_par_taille": {"2560x1440": "pas un objet"}}), encoding="utf-8"
        )

        assert load(tmp_path) == Settings()


class TestAncienFichierSansResolution:
    """Ce qu'il advient d'une zone tracée avant que la table existe.

    Décision : elle est **conservée mais pas appliquée**. La jeter perdrait le
    travail du joueur ; l'appliquer partout referait le défaut qu'on corrige, en
    le rendant permanent. Elle attend donc d'être attribuée à une taille de
    fenêtre, ce qui est un geste et non une supposition.
    """

    def test_un_ancien_fichier_se_relit_sans_planter_et_sans_rien_perdre(
        self, tmp_path: Path
    ) -> None:
        """Régression : le fichier que Maxime a déjà sur son poste.

        Son `reglages.json` porte trois zones tracées à la main, écrites avant
        que la taille de fenêtre serve de clé. La zone de choix est celle qui
        coûterait le plus cher : son calcul d'origine est une **estimation**,
        aucune capture du panneau n'existe, donc le tracé du joueur en est la
        seule source fiable.

        Une mise à jour qui aurait effacé ce fichier lui aurait redemandé, sans
        prévenir, la mesure que le projet n'a pas.
        """
        (tmp_path / "reglages.json").write_text(
            json.dumps(
                {
                    "seuil_presence": 0.65,
                    "zone_bandeau": {"x": 2210, "y": 1186, "largeur": 349, "hauteur": 115},
                    "zone_suivi": {"x": 2090, "y": 440, "largeur": 340, "hauteur": 380},
                    "zone_choix": {"x": 639, "y": 359, "largeur": 1280, "hauteur": 720},
                }
            ),
            encoding="utf-8",
        )

        relu = load(tmp_path)

        assert relu.presence_threshold == 0.65
        assert relu.banner == BANDEAU
        assert relu.tracker == Rect(2090, 440, 340, 380)
        assert relu.choice == Rect(639, 359, 1280, 720)

    def test_une_zone_sans_resolution_ne_s_applique_a_aucune_taille(self) -> None:
        # C'est la décision : conservée, jamais appliquée d'office. On ne sait
        # pas sur quel écran ce rectangle a été tracé, et le deviner est
        # précisément ce qui produirait un réglage faux et durable.
        reglages = Settings(banner=BANDEAU)

        assert reglages.zone_for("banner", PLEIN_ECRAN) is None
        assert reglages.zone_for("banner", FENETRE) is None
        assert reglages.unkeyed("banner") == BANDEAU

    def test_une_zone_sans_resolution_survit_a_une_reecriture(self, tmp_path: Path) -> None:
        # Conservée veut dire conservée dans le fichier aussi : un
        # enregistrement fait pour changer un curseur ne doit pas emporter le
        # tracé au passage.
        save(Settings(choice=Rect(700, 400, 1200, 640), opacity=0.8), tmp_path)

        assert load(tmp_path).choice == Rect(700, 400, 1200, 640)

    def test_l_adoption_attribue_les_anciennes_zones_a_une_taille(self) -> None:
        reglages = Settings(banner=BANDEAU, choice=Rect(639, 359, 1280, 720))

        adoptées = reglages.adopted_for(PLEIN_ECRAN)

        assert adoptées.zone_for("banner", PLEIN_ECRAN) == BANDEAU
        assert adoptées.zone_for("choice", PLEIN_ECRAN) == Rect(639, 359, 1280, 720)
        assert adoptées.zone_for("tracker", PLEIN_ECRAN) is None

    def test_l_adoption_vide_les_champs_sans_resolution(self) -> None:
        # Sinon le même rectangle vivrait à deux endroits, dont l'un sans clé,
        # et la question « à quelle résolution » se reposerait au prochain
        # changement d'écran.
        adoptées = Settings(banner=BANDEAU).adopted_for(PLEIN_ECRAN)

        assert adoptées.banner is None
        assert adoptées.unkeyed("banner") is None

    def test_l_adoption_ne_chasse_pas_une_zone_deja_datee(self) -> None:
        # Une zone tracée en sachant sur quel écran l'emporte sur une zone dont
        # on l'ignore. L'inverse remplacerait du connu par du supposé.
        reglages = Settings(banner=Rect(1, 2, 3, 4)).with_zone("banner", PLEIN_ECRAN, BANDEAU)

        assert reglages.adopted_for(PLEIN_ECRAN).zone_for("banner", PLEIN_ECRAN) == BANDEAU

    def test_tracer_une_zone_efface_l_ancienne_sans_resolution(self) -> None:
        reglages = Settings(banner=Rect(1, 2, 3, 4)).with_zone("banner", FENETRE, BANDEAU)

        assert reglages.banner is None
        assert reglages.zone_for("banner", FENETRE) == BANDEAU


class TestPourquoiCEstSansDanger:
    def test_les_bornes_n_autorisent_aucun_seuil_certain(self) -> None:
        """Le seuil ne peut jamais atteindre 1, et c'est délibéré.

        Un seuil de 1,0 exigerait une corrélation parfaite. Mesuré en jeu, elle
        plafonne à 0,90 parce que le bandeau est semi-transparent et que le
        décor bouge derrière. Un curseur poussé au bout ne mesurerait donc plus
        jamais rien, sans que rien ne l'annonce.
        """
        assert LIMITS["presence_threshold"][1] < 1.0

    def test_aucune_zone_n_est_rendue_pour_une_taille_qu_elle_ne_vise_pas(self) -> None:
        """L'invariant que la mémorisation des zones ne doit jamais enfreindre.

        Tout le reste du module produit au pire un silence : une zone mal
        placée capture du décor, où l'analyse ne trouve aucun titre connu. Une
        zone appliquée à la mauvaise résolution ferait pire, parce qu'elle
        serait enregistrée : le silence se répéterait à chaque session, et rien
        ne le relierait à un changement d'écran.

        La règle est donc absolue et se vérifie ici sur toutes les tailles :
        hors de sa propre taille, une zone n'existe pas.
        """
        tailles = [PLEIN_ECRAN, FENETRE, (2559, 1439), (1280, 720), (3840, 2160)]
        reglages = Settings(banner=Rect(1, 2, 3, 4)).with_zone("banner", PLEIN_ECRAN, BANDEAU)

        rendues = {taille: reglages.zone_for("banner", taille) for taille in tailles}

        attendues = {taille: (BANDEAU if taille == PLEIN_ECRAN else None) for taille in tailles}
        assert rendues == attendues

    def test_la_cadence_ne_peut_pas_tomber_sous_une_seconde(self) -> None:
        # Le bandeau reste affiché plusieurs secondes. Une cadence plus lente
        # commencerait à en laisser passer entre deux captures.
        assert LIMITS["poll_interval"][1] <= 1.0
