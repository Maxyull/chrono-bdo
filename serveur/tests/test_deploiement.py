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

#: Parmi les obligatoires, celles qui viennent du **fichier de secrets local**
#: et doivent donc traverser l'appel `ssh` pour exister sur le VPS.
#:
#: Les autres n'en ont pas besoin, et il faut savoir pourquoi plutôt que de
#: l'exiger de tout le monde : `RUBIN_DB` est reconstruite à distance depuis
#: les identifiants Postgres, qui traversent ; `RUBIN_LATEST` est dérivée des
#: sources déjà déployées sur le VPS ; `RUBIN_MIN_CLIENT` est écrite en dur
#: dans l'unité.
VENANT_DES_SECRETS = {
    "RUBIN_DISCORD_ID",
    "RUBIN_DISCORD_SECRET",
    "RUBIN_DISCORD_ETAT",
    "RUBIN_RAPPORT_WEBHOOK",
    "BUTIN_RAPPORT_WEBHOOK",
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

    @pytest.mark.parametrize("nom", sorted(VENANT_DES_SECRETS))
    def test_chaque_secret_local_traverse_le_ssh(self, nom: str) -> None:
        """⚠️ **Le chemin a DEUX moitiés, et la première version de ce fichier
        n'en vérifiait qu'une.**

        `deployer.sh` s'exécute sur deux machines : un préambule local qui lit
        le fichier de secrets, puis un `bash -s` distant qui écrit l'unité
        systemd. Une variable posée dans l'unité mais non passée à `ssh`
        n'existe pas sur le VPS.

        Constaté le 07/08/2026, sur ce correctif lui-même : les onze tests
        passaient, et le déploiement s'est arrêté net sur
        `RUBIN_RAPPORT_WEBHOOK: unbound variable`. Un test vert pendant que la
        chose ne marche pas, pour la deuxième fois dans la même heure.

        ⚠️ **Et la première version de CE test-ci mentait aussi.** Elle
        cherchait le nom dans tout le préambule local, où il figure déjà, à la
        ligne qui lui donne sa valeur par défaut :
        `RUBIN_RAPPORT_WEBHOOK="${RUBIN_RAPPORT_WEBHOOK:-}"`. Piégé en
        retirant la ligne de l'appel `ssh`, il restait vert. Trois bancs
        menteurs dans la même journée, tous démasqués par le même geste :
        casser exprès ce qu'ils sont censés garder.

        La fenêtre regardée est donc **l'appel `ssh` seul**, de la commande
        jusqu'au `'bash -s'` qui ouvre le script distant.
        """
        script = DEPLOYEUR.read_text(encoding="utf-8")
        debut = script.index("ssh -i")
        appel_ssh = script[debut : script.index("'bash -s'", debut)]
        assert f'{nom}="$' in appel_ssh, (
            f"{nom} n'est pas passée au shell distant par l'appel ssh : elle "
            f"sera vide sur le VPS, ou fera échouer le déploiement sous "
            f"`set -u`. {OBLIGATOIRES[nom]}."
        )

    def test_les_secrets_locaux_sont_tous_obligatoires(self) -> None:
        """Garde-fou du test précédent : une variable citée là et oubliée
        dans `OBLIGATOIRES` ne serait vérifiée qu'à moitié."""
        assert set(OBLIGATOIRES) >= VENANT_DES_SECRETS

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
