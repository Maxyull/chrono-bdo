"""Ce que `deployer.sh` doit transporter jusqu'au service.

⚠️ **Ce fichier existe à cause d'un défaut trouvé en production**, le
07/08/2026, quelques minutes après avoir déployé la v0.6.0.
`RUBIN_RAPPORT_WEBHOOK` et `BUTIN_RAPPORT_WEBHOOK` étaient posés dans le
fichier de secrets depuis la veille, et `deployer.sh` n'avait aucune ligne
pour les porter dans l'unité systemd. `POST /v1/rapport` rendait donc encore
503, « envoi de rapport non configuré », pour les deux applications.

Le bouton « Envoyer le rapport » était la fonctionnalité phare de cette
version. Il était complet, testé, empaqueté, publié, et **il ne pouvait rien
envoyer**.

Rien ne le disait, et c'est le pire de l'affaire : un rapport qui ne part pas
ne se voit ni côté joueur, où il n'y a rien à voir, ni côté salon Discord, où
il n'arrive simplement rien. C'est le même motif que partout ailleurs dans ce
projet, une pièce construite et jamais branchée, que seule une mesure en vraie
grandeur révèle.

Ces tests lisent le script, ils ne l'exécutent pas : il touche à un VPS.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
SOURCES = RACINE / "src" / "rubin_serveur"
DEPLOYEUR = RACINE / "deploiement" / "deployer.sh"

#: Les variables qui DOIVENT arriver jusqu'au service, et ce qui casse sans
#: chacune. Une variable absente ne fait jamais tomber le serveur : elle
#: change son comportement en silence, ce qui est bien pire.
OBLIGATOIRES = {
    "RUBIN_DB": "sans elle, le serveur repart sur une base SQLite en mémoire, "
    "donc vide à chaque redémarrage, et rend des classements vides sans erreur",
    "RUBIN_LATEST": "sans elle, /v1/version annonce une vieille version et "
    "aucun joueur n'apprend qu'une mise à jour existe",
    "RUBIN_MIN_CLIENT": "sans elle, le seuil de refus des vieux clients bouge",
    "RUBIN_DISCORD_ID": "sans elle, le rattachement Discord rend 503",
    "RUBIN_DISCORD_SECRET": "idem",
    "RUBIN_DISCORD_ETAT": "sans elle, la clé qui signe l'état est retirée au "
    "sort à chaque démarrage, et aucun rattachement commencé n'aboutit",
    "RUBIN_RAPPORT_WEBHOOK": "le défaut du 07/08/2026 : sans elle, le bouton "
    "« Envoyer le rapport » rend 503 et aucun rapport n'arrive nulle part",
    "BUTIN_RAPPORT_WEBHOOK": "sans elle, les rapports de Butin retombent dans "
    "le salon de Rubin, ce que la session butin-bdo a accepté en dépannage "
    "mais qui n'est pas l'état visé",
}

#: Les variables qu'on choisit **délibérément** de ne pas transporter, parce
#: que leur valeur par défaut dans le code est la bonne en production. Toute
#: variable doit être dans cette liste ou dans `OBLIGATOIRES` : c'est ce qui
#: force à trancher au moment d'en ajouter une, plutôt que des mois plus tard
#: en interrogeant le serveur.
DEFAUT_ACCEPTABLE = {
    "RUBIN_DOWNLOAD": "le défaut pointe déjà sur la dernière release GitHub",
    "RUBIN_DISCORD_RETOUR": "le script la dérive lui-même du domaine",
}


def variables_lues() -> set[str]:
    """Toutes les variables d'environnement que le serveur lit.

    La recherche porte sur le texte entier et non ligne par ligne : un appel
    coupé en deux lignes par le formateur passerait sinon inaperçu, et c'est
    exactement la forme qu'a `RUBIN_DOWNLOAD`.
    """
    motif = re.compile(r"os\.environ\.get\(\s*[\"']([A-Z_]+)[\"']")
    noms: set[str] = set()
    for fichier in SOURCES.rglob("*.py"):
        noms |= set(motif.findall(fichier.read_text(encoding="utf-8")))
    return noms


class TestVariablesTransportees:
    def test_le_serveur_lit_bien_des_variables(self) -> None:
        # Garde-fou : une recherche qui ne trouve rien ferait passer tout ce
        # fichier pour vert sans avoir rien vérifié.
        assert variables_lues()

    @pytest.mark.parametrize("nom", sorted(OBLIGATOIRES))
    def test_chaque_variable_obligatoire_est_dans_lunite(self, nom: str) -> None:
        """Régression du 07/08/2026 pour les deux webhooks, et garde pour les
        autres : une variable que le script ne pose pas ne fait jamais tomber
        le serveur, elle change son comportement en silence."""
        script = DEPLOYEUR.read_text(encoding="utf-8")
        assert f"Environment={nom}=" in script, (
            f"{nom} n'est pas posée dans l'unité systemd par deployer.sh. "
            f"{OBLIGATOIRES[nom]}."
        )

    def test_aucune_variable_nest_laissee_sans_decision(self) -> None:
        """Toute variable lue par le serveur doit être soit transportée, soit
        explicitement reconnue comme ayant un bon défaut.

        C'est ce test qui aurait attrapé le défaut : les deux webhooks ont été
        ajoutés au code le 06/08, et personne n'a eu à décider s'ils devaient
        être déployés. Ajouter une variable oblige désormais à trancher tout
        de suite, dans ce fichier."""
        connues = set(OBLIGATOIRES) | set(DEFAUT_ACCEPTABLE)
        orphelines = variables_lues() - connues
        assert not orphelines, (
            f"variables lues par le serveur et rangées nulle part : "
            f"{sorted(orphelines)}. Il faut décider : transportée par "
            f"deployer.sh (OBLIGATOIRES) ou bon défaut (DEFAUT_ACCEPTABLE) ?"
        )

    def test_le_script_dit_a_voix_haute_si_les_rapports_sont_eteints(self) -> None:
        """Le déploiement doit annoncer l'état des webhooks, comme il annonce
        déjà celui du rattachement Discord. Le défaut du 07/08 est passé
        inaperçu parce que le script se déployait en silence là-dessus : rien
        dans sa sortie ne distinguait « branché » de « pas branché »."""
        script = DEPLOYEUR.read_text(encoding="utf-8")
        assert "rapports Rubin" in script
        assert "rapports Butin" in script
