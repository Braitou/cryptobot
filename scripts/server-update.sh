#!/usr/bin/env bash
# ============================================================
# server-update.sh — Mise a jour du serveur depuis GitHub
# Usage : bash /opt/cryptobot/scripts/server-update.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/cryptobot"
cd "$APP_DIR"

echo "=== CryptoBot — Mise a jour ==="

# 0. Sauvegarder le .env (pas dans git)
cp "$APP_DIR/.env" /tmp/cryptobot_env_backup

# 1. Pull depuis GitHub
echo "[1/5] Pull depuis GitHub..."
git fetch origin main
git reset --hard origin/main
echo "  OK"

# 1b. Restaurer le .env
cp /tmp/cryptobot_env_backup "$APP_DIR/.env"
echo "[2/5] .env restaure"

# 3. Dependances Python
echo "[3/5] Dependances Python..."
"$APP_DIR/venv/bin/pip" install -r requirements.txt -q 2>&1 | tail -1
echo "  OK"

# 4. Rebuild dashboard
echo "[4/5] Rebuild dashboard..."
cd "$APP_DIR/dashboard"
npm ci --production=false --loglevel=error 2>&1 | tail -1 || true
npm run build 2>&1 | tail -3
cd "$APP_DIR"
echo "  OK"

# 5. Permissions + restart
echo "[5/5] Restart service..."
chown -R cryptobot:cryptobot "$APP_DIR"
systemctl restart cryptobot
sleep 4

if systemctl is-active --quiet cryptobot; then
    echo ""
    echo "=== MISE A JOUR REUSSIE ==="
    systemctl status cryptobot --no-pager | head -5
else
    echo ""
    echo "=== ERREUR ==="
    journalctl -u cryptobot -n 20 --no-pager
fi
