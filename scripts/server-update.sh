#!/usr/bin/env bash
# ============================================================
# server-update.sh — Mise à jour du serveur depuis GitHub
# Placé sur le serveur dans /opt/cryptobot/scripts/
# Usage : sudo /opt/cryptobot/scripts/server-update.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/cryptobot"
cd "$APP_DIR"

echo "=== CryptoBot — Mise à jour ==="

# 1. Pull depuis GitHub
echo "[1/4] Pull depuis GitHub..."
git fetch origin main
git reset --hard origin/main
echo "  → Code mis à jour"

# 2. Dépendances Python (si requirements.txt a changé)
echo "[2/4] Dépendances Python..."
"$APP_DIR/venv/bin/pip" install -r requirements.txt -q 2>&1 | tail -1
echo "  → OK"

# 3. Rebuild dashboard (si frontend a changé)
echo "[3/4] Rebuild dashboard..."
cd "$APP_DIR/dashboard"
npm ci --production=false --loglevel=error 2>&1 | tail -1 || true
npm run build 2>&1 | tail -3
cd "$APP_DIR"
echo "  → Dashboard rebuilt"

# 4. Permissions + restart
echo "[4/4] Restart service..."
chown -R cryptobot:cryptobot "$APP_DIR"
systemctl restart cryptobot
sleep 3

if systemctl is-active --quiet cryptobot; then
    echo ""
    echo "=== MISE A JOUR REUSSIE ==="
    systemctl status cryptobot --no-pager | head -5
else
    echo ""
    echo "=== ERREUR — Le service n'a pas démarré ==="
    journalctl -u cryptobot -n 20 --no-pager
fi
