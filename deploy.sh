#!/usr/bin/env bash
#
# Script de deploiement — a lancer SUR LE SERVEUR apres chaque push.
#
#   cd /chemin/vers/backend
#   ./deploy.sh
#
# Il enchaine, dans l'ordre, tout ce qu'un push de code peut exiger :
#   1. sauvegarde du .env (jamais ecrase, jamais commite)
#   2. recuperation du code (git pull)
#   3. installation des dependances
#   4. application des migrations de base de donnees  <-- l'etape oubliee
#   5. collecte des fichiers statiques (admin en DEBUG=False)
#   6. redemarrage du service
#
# Adapter les 2 variables ci-dessous a ton infra.

set -euo pipefail

# --- Configuration -------------------------------------------------------
# Module de settings utilise en production.
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
# Nom du service systemd qui lance daphne (mettre "" si tu redemarres a la main).
SERVICE_NAME="${SERVICE_NAME:-dunamis-backend}"
# Fichier de requirements a installer.
REQ_FILE="requirements/production.txt"
# -------------------------------------------------------------------------

echo "==> [1/6] Sauvegarde du .env"
[ -f .env ] && cp .env ".env.bak" && echo "    .env -> .env.bak"

echo "==> [2/6] git pull"
git pull --ff-only

echo "==> [3/6] Installation des dependances ($REQ_FILE)"
pip install -r "$REQ_FILE"

echo "==> [4/6] Migrations de la base de donnees"
python manage.py migrate --noinput

echo "==> [5/6] Collecte des fichiers statiques"
python manage.py collectstatic --noinput

echo "==> [6/6] Redemarrage du service"
if [ -n "$SERVICE_NAME" ]; then
  sudo systemctl restart "$SERVICE_NAME"
  echo "    service '$SERVICE_NAME' redemarre"
else
  echo "    (SERVICE_NAME vide : redemarre daphne manuellement)"
fi

echo "==> Deploiement termine avec succes."
