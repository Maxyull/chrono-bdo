#!/usr/bin/env bash
# Déploie le serveur de classement sur le VPS.
#
# Se lance depuis le poste Windows, sous Git Bash. Tout le travail a lieu sur
# le VPS : le poste n'a besoin que de `ssh`. Même principe que les scripts de
# bdi-infra, dont ce fichier reprend les conventions.
#
# Le script est **rejouable** : le relancer sur un serveur déjà déployé met à
# jour le code et redémarre le service, sans rien détruire. C'est ce qui permet
# de s'en servir comme d'un script de mise à jour et pas seulement
# d'installation.
#
# Ce qu'il ne fait PAS, et ne peut pas faire :
#   - créer l'enregistrement DNS `rubin.maxyull.fr`, qui vit chez le
#     registrar. Tant qu'il manque, Caddy ne peut obtenir aucun certificat et
#     le service reste inaccessible depuis l'extérieur.

set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SECRETS="$(cd "$RACINE/../.." && pwd)/secrets"

# Les accès VPS sont ceux de bdi-infra : même machine, même clé. Les dupliquer
# dans un second fichier créerait deux vérités pour un seul serveur.
# shellcheck disable=SC1091
set -a; source "$SECRETS/bdi-infra.env"; set +a

# Le mot de passe de la base du chronomètre, lui, est propre au projet.
CONF_RUBIN="$SECRETS/rubin-bdo.env"
if [[ ! -f "$CONF_RUBIN" ]]; then
  echo "-> premier déploiement : génération du mot de passe de la base"
  # Sans passer par `tr | head` : sous `pipefail`, `head` ferme le tube, `tr`
  # meurt d'un SIGPIPE, et le script s'arrête sur ce qui n'est pas une erreur.
  # Le mot de passe reste alphanumérique, car il traverse une ligne de commande
  # ssh où un caractère spécial demanderait un échappement de plus.
  MDP="$(python -c 'import secrets,string; print("".join(secrets.choice(string.ascii_letters+string.digits) for _ in range(40)))')"
  cat >"$CONF_RUBIN" <<EOF
# Serveur de classement de Rubin. Généré le $(date +%F).
# Hors de tout dépôt git, comme tous les secrets.
RUBIN_PG_USER=rubin
RUBIN_PG_PASSWORD=$MDP
RUBIN_PG_DATABASE=rubin
RUBIN_PORT=8010
RUBIN_DOMAINE=rubin.maxyull.fr
EOF
fi
# shellcheck disable=SC1090
set -a; source "$CONF_RUBIN"; set +a

# Le rattachement Discord est **éteint par défaut**, et doit le rester tant que
# la politique de confidentialité publiée ne mentionne pas le pseudonyme
# Discord : l'activer stocke une donnée personnelle que le texte actuel promet
# de ne pas transmettre. Tant que ces deux variables sont absentes du fichier de
# secrets, le serveur tourne exactement comme aujourd'hui et les deux adresses
# du rattachement répondent « non configuré ».
RUBIN_DISCORD_ID="${RUBIN_DISCORD_ID:-}"
RUBIN_DISCORD_SECRET="${RUBIN_DISCORD_SECRET:-}"
RUBIN_DISCORD_RETOUR="${RUBIN_DISCORD_RETOUR:-https://${RUBIN_DOMAINE}/v1/discord/retour}"

# Les deux webhooks du bouton « Envoyer le rapport », un par application. Ils
# sont posés dans le fichier de secrets par la session `discord-bdo` depuis le
# 06/08/2026, et ce script ne les transportait pas : mesuré en production le
# 07/08 après le déploiement de la v0.6.0, `POST /v1/rapport` rendait encore
# 503 pour les deux, c'est-à-dire « envoi de rapport non configuré ».
#
# Le défaut se voyait d'autant moins que la fonctionnalité entière était neuve
# et que rien ne distinguait « pas encore branché » de « branché mais muet ».
RUBIN_RAPPORT_WEBHOOK="${RUBIN_RAPPORT_WEBHOOK:-}"
BUTIN_RAPPORT_WEBHOOK="${BUTIN_RAPPORT_WEBHOOK:-}"
if [[ -n "$RUBIN_DISCORD_ID" && -z "${RUBIN_DISCORD_ETAT:-}" ]]; then
  # La clé qui signe l'état est tirée au sort par le serveur quand elle manque,
  # mais elle change alors à chaque redémarrage : toute connexion en cours à ce
  # moment-là échoue sans raison visible. On la fige une fois, dans le fichier
  # de secrets, hors de tout dépôt git.
  echo "-> génération de la clé de signature de l'état Discord"
  RUBIN_DISCORD_ETAT="$(python -c 'import secrets; print(secrets.token_hex(32))')"
  echo "RUBIN_DISCORD_ETAT=$RUBIN_DISCORD_ETAT" >>"$CONF_RUBIN"
fi

DEPOT="https://github.com/Maxyull/rubin-bdo.git"
CIBLE="/opt/rubin"

echo "==> déploiement sur ${VPS_HOST}, port ${RUBIN_PORT}, domaine ${RUBIN_DOMAINE}"

ssh -i "$VPS_SSH_KEY" -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" \
  RUBIN_PG_USER="$RUBIN_PG_USER" \
  RUBIN_PG_PASSWORD="$RUBIN_PG_PASSWORD" \
  RUBIN_PG_DATABASE="$RUBIN_PG_DATABASE" \
  RUBIN_PORT="$RUBIN_PORT" \
  RUBIN_DOMAINE="$RUBIN_DOMAINE" \
  RUBIN_DISCORD_ID="$RUBIN_DISCORD_ID" \
  RUBIN_DISCORD_SECRET="$RUBIN_DISCORD_SECRET" \
  RUBIN_DISCORD_RETOUR="$RUBIN_DISCORD_RETOUR" \
  RUBIN_DISCORD_ETAT="${RUBIN_DISCORD_ETAT:-}" \
  RUBIN_RAPPORT_WEBHOOK="$RUBIN_RAPPORT_WEBHOOK" \
  BUTIN_RAPPORT_WEBHOOK="$BUTIN_RAPPORT_WEBHOOK" \
  DEPOT="$DEPOT" CIBLE="$CIBLE" 'bash -s' <<'DISTANT'
set -euo pipefail

echo "--- base de données"
# Postgres système, celui de bdi-infra. Une base séparée plutôt qu'un schéma
# dans la base existante : les deux services n'ont aucune donnée commune, et
# une sauvegarde ou une restauration de l'un ne doit pas toucher l'autre.
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${RUBIN_PG_USER}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE ROLE ${RUBIN_PG_USER} LOGIN PASSWORD '${RUBIN_PG_PASSWORD}';"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${RUBIN_PG_DATABASE}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE ${RUBIN_PG_DATABASE} OWNER ${RUBIN_PG_USER};"
# Le mot de passe est réappliqué à chaque passage : il peut avoir été changé
# côté poste sans que la base le sache, et l'écart ne se verrait qu'au
# redémarrage suivant.
sudo -u postgres psql -c "ALTER ROLE ${RUBIN_PG_USER} PASSWORD '${RUBIN_PG_PASSWORD}';" >/dev/null

echo "--- code"
sudo apt-get install -y -qq git python3-venv >/dev/null
if [[ -d "${CIBLE}/.git" ]]; then
  sudo git -C "${CIBLE}" fetch --quiet origin
  sudo git -C "${CIBLE}" reset --hard --quiet origin/main
else
  sudo rm -rf "${CIBLE}"
  sudo git clone --quiet --depth 1 "${DEPOT}" "${CIBLE}"
fi

echo "--- environnement"
sudo python3 -m venv "${CIBLE}/.venv" 2>/dev/null || true
# Le client est installé sans son extra `capture` : le serveur n'a besoin ni
# de numpy ni d'un moteur de reconnaissance d'images pour relire du JSON.
sudo "${CIBLE}/.venv/bin/pip" install --quiet --upgrade pip
sudo "${CIBLE}/.venv/bin/pip" install --quiet -e "${CIBLE}" -e "${CIBLE}/serveur[postgres]"

# La version annoncée aux clients est celle du code qu'on vient de déployer :
# la déduire évite qu'elle reste figée sur une valeur écrite ailleurs, ce qui
# ferait annoncer au serveur une version périmée de son propre logiciel.
# Extraction sans expression régulière à échappements : ceux-ci ne survivent
# pas au passage dans un document en ligne, et rendaient ici un caractère de
# contrôle au lieu du numéro de version.
VERSION="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' "${CIBLE}/src/rubin/__init__.py" | head -1)"

# Le bloc Discord n'est écrit que si les identifiants existent. Poser les
# variables à vide reviendrait au même pour le serveur, qui les traite comme
# absentes, mais laisserait croire en lisant l'unité que le rattachement est
# gréé alors qu'il ne l'est pas.
DISCORD_ENV=""
if [[ -n "${RUBIN_DISCORD_ID}" && -n "${RUBIN_DISCORD_SECRET}" ]]; then
  DISCORD_ENV="Environment=RUBIN_DISCORD_ID=${RUBIN_DISCORD_ID}
Environment=RUBIN_DISCORD_SECRET=${RUBIN_DISCORD_SECRET}
Environment=RUBIN_DISCORD_RETOUR=${RUBIN_DISCORD_RETOUR}
Environment=RUBIN_DISCORD_ETAT=${RUBIN_DISCORD_ETAT}"
  echo "--- rattachement Discord : activé"
else
  echo "--- rattachement Discord : éteint (aucun identifiant fourni)"
fi

# Même règle que le bloc Discord : une variable posée à vide se lirait dans
# l'unité comme un envoi gréé, alors que le serveur la traite comme absente et
# rend 503. Chacune est donc écrite seulement si elle existe, et l'état de
# chacune est dit à voix haute, parce que le silence est précisément ce qui a
# laissé passer le défaut : un rapport qui ne part pas ne se voit ni côté
# joueur, où il n'y a rien à voir, ni côté salon Discord, où il n'arrive rien.
RAPPORT_ENV=""
if [[ -n "${RUBIN_RAPPORT_WEBHOOK}" ]]; then
  RAPPORT_ENV="Environment=RUBIN_RAPPORT_WEBHOOK=${RUBIN_RAPPORT_WEBHOOK}"
  echo "--- rapports Rubin : activés"
else
  echo "--- rapports Rubin : ÉTEINTS (aucun webhook), le bouton rendra 503"
fi
if [[ -n "${BUTIN_RAPPORT_WEBHOOK}" ]]; then
  RAPPORT_ENV="${RAPPORT_ENV}
Environment=BUTIN_RAPPORT_WEBHOOK=${BUTIN_RAPPORT_WEBHOOK}"
  echo "--- rapports Butin : activés"
else
  echo "--- rapports Butin : éteints, ils retomberont dans le salon de Rubin"
fi

echo "--- service (version annoncée : ${VERSION})"
sudo tee /etc/systemd/system/rubin.service >/dev/null <<UNIT
[Unit]
Description=Rubin, serveur de classement
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=exec
# Pas de conteneur : le VPS n'a que 2 Go de mémoire disponible, et un service
# Python en systemd en consomme dix fois moins qu'une pile Docker.
Environment=RUBIN_DB=postgresql+psycopg://${RUBIN_PG_USER}:${RUBIN_PG_PASSWORD}@127.0.0.1/${RUBIN_PG_DATABASE}
Environment=RUBIN_LATEST=${VERSION}
# La version minimale reste en arrière : n'exiger une mise à jour que lorsque
# c'est indispensable, sinon chaque publication couperait les joueurs qui
# n'ont pas encore retéléchargé.
Environment=RUBIN_MIN_CLIENT=0.1.0
${DISCORD_ENV}
${RAPPORT_ENV}
ExecStart=${CIBLE}/.venv/bin/uvicorn rubin_serveur.main:app --host 127.0.0.1 --port ${RUBIN_PORT}
WorkingDirectory=${CIBLE}/serveur
Restart=always
RestartSec=5
# Le service n'écoute que sur la boucle locale : Caddy est la seule porte
# d'entrée depuis l'extérieur.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --quiet rubin
sudo systemctl restart rubin

echo "--- reverse proxy"
sudo tee /etc/caddy/rubin.caddyfile >/dev/null <<CADDY
# Rubin — classement des temps de quêtes.
# HTTPS automatique par Let's Encrypt, dès que le DNS pointe ici.
${RUBIN_DOMAINE} {
	encode zstd gzip

	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options    "nosniff"
		Referrer-Policy           "strict-origin-when-cross-origin"
		-Server
	}

	# Un lot de session dépasse rarement quelques dizaines de kilo-octets.
	# Cette borne écarte les envois démesurés avant qu'ils n'atteignent
	# l'application, qui les refuserait de toute façon.
	request_body {
		max_size 2MB
	}

	reverse_proxy 127.0.0.1:${RUBIN_PORT}
}
CADDY
grep -q "rubin.caddyfile" /etc/caddy/Caddyfile || \
  echo "import /etc/caddy/rubin.caddyfile" | sudo tee -a /etc/caddy/Caddyfile >/dev/null

# La configuration est validée avant d'être appliquée : une erreur de syntaxe
# rechargée telle quelle couperait *tous* les sites du serveur, pas seulement
# celui qu'on ajoute.
if sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  sudo systemctl reload caddy
  echo "caddy rechargé"
else
  echo "ERREUR : configuration Caddy invalide, rien n'a été rechargé" >&2
  sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1 | tail -5 >&2
  exit 1
fi

echo "--- vérification"
sleep 2
systemctl is-active rubin
curl -fsS "http://127.0.0.1:${RUBIN_PORT}/sante" && echo
DISTANT

echo
# Le message n'est affiché que si le DNS manque réellement : le laisser en
# toutes circonstances finirait par être ignoré, y compris le jour où il
# compte.
if getent hosts "$RUBIN_DOMAINE" >/dev/null 2>&1 || nslookup "$RUBIN_DOMAINE" >/dev/null 2>&1; then
  echo "==> déployé et joignable : https://${RUBIN_DOMAINE}"
else
  echo "==> déployé. Reste une chose que je ne peux pas faire :"
  echo "    créer l'enregistrement DNS A  ${RUBIN_DOMAINE}  ->  ${VPS_HOST}"
  echo "    Tant qu'il manque, Caddy ne peut obtenir aucun certificat."
fi
