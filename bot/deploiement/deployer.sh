#!/usr/bin/env bash
# Déploie le robot Discord de consultation sur le VPS.
#
# Se lance depuis le poste Windows, sous Git Bash, comme
# serveur/deploiement/deployer.sh dont ce fichier reprend les conventions.
# Tout le travail a lieu sur le VPS : le poste n'a besoin que de `ssh`.
#
# Le script est **rejouable** : le relancer met à jour le code et redémarre
# le service, sans rien détruire.
#
# ⚠️ **N'active jamais l'unité sans jeton.** Un robot lancé sans
# `RUBIN_BOT_JETON` rend le code 1 (voir `rubin_bot/__main__.py`), et
# `Restart=always` le relancerait en boucle indéfiniment. Voir `bot/README.md`,
# partie « Ce qui reste à faire à la main ».

set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SECRETS="$(cd "$RACINE/../.." && pwd)/secrets"

# Les accès VPS sont ceux de bdi-infra : même machine, même clé.
# shellcheck disable=SC1091
set -a; source "$SECRETS/bdi-infra.env"; set +a

CONF_BOT="$SECRETS/rubin-bot.env"
if [[ ! -f "$CONF_BOT" ]]; then
  echo "ERREUR : $CONF_BOT introuvable." >&2
  echo "  Créez-le avec RUBIN_BOT_JETON=... (portail développeur Discord," >&2
  echo "  onglet Bot, Reset Token). Voir bot/README.md." >&2
  exit 1
fi
# shellcheck disable=SC1090
set -a; source "$CONF_BOT"; set +a

if [[ -z "${RUBIN_BOT_JETON:-}" ]]; then
  echo "ERREUR : RUBIN_BOT_JETON est vide dans $CONF_BOT." >&2
  echo "  Sans jeton, le robot ne doit pas être installé : voir bot/README.md." >&2
  exit 1
fi

RUBIN_BOT_SERVEUR="${RUBIN_BOT_SERVEUR:-https://rubin.maxyull.fr}"

DEPOT="https://github.com/Maxyull/rubin-bdo.git"
CIBLE="/opt/rubin-bot"

echo "==> déploiement du robot sur ${VPS_HOST}, serveur interrogé ${RUBIN_BOT_SERVEUR}"

ssh -i "$VPS_SSH_KEY" -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" \
  RUBIN_BOT_JETON="$RUBIN_BOT_JETON" \
  RUBIN_BOT_SERVEUR="$RUBIN_BOT_SERVEUR" \
  DEPOT="$DEPOT" CIBLE="$CIBLE" 'bash -s' <<'DISTANT'
set -euo pipefail

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
sudo "${CIBLE}/.venv/bin/pip" install --quiet --upgrade pip
sudo "${CIBLE}/.venv/bin/pip" install --quiet -e "${CIBLE}/bot"

# Le jeton vit dans un fichier séparé, lisible du seul superutilisateur, et
# jamais dans l'unité elle-même : `systemctl show` ou `systemctl cat` sur une
# unité lisible par tous afficherait sinon le jeton en clair à qui a un accès
# shell quelconque sur la machine.
echo "--- jeton"
sudo install -d -m 700 /etc/rubin-bot
sudo tee /etc/rubin-bot/env >/dev/null <<ENV
RUBIN_BOT_JETON=${RUBIN_BOT_JETON}
RUBIN_BOT_SERVEUR=${RUBIN_BOT_SERVEUR}
ENV
sudo chmod 600 /etc/rubin-bot/env

echo "--- service"
sudo tee /etc/systemd/system/rubin-bot.service >/dev/null <<UNIT
[Unit]
Description=Rubin, robot Discord de consultation
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
EnvironmentFile=/etc/rubin-bot/env
ExecStart=${CIBLE}/.venv/bin/rubin-bot
WorkingDirectory=${CIBLE}/bot
# La passerelle Discord coupe régulièrement les connexions longues : un
# redémarrage rapide et systématique est le comportement normal, pas un
# signe de panne.
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --quiet rubin-bot
sudo systemctl restart rubin-bot

echo "--- vérification"
sleep 3
systemctl is-active rubin-bot
DISTANT

echo
echo "==> robot déployé. Les commandes /rapides /chaine /quete apparaissent"
echo "    sur le serveur Discord où il a été invité, quelques instants après"
echo "    ce premier démarrage. Voir bot/README.md si ce n'est pas encore fait."
