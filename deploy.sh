#!/usr/bin/env bash
# ============================================================
# CryptoBot — Script de déploiement DigitalOcean (512 MB RAM)
# Usage : exécuter en tant que root sur le serveur
# ============================================================
set -euo pipefail

APP_USER="cryptobot"
APP_DIR="/opt/cryptobot"
VENV_DIR="$APP_DIR/venv"
NODE_MAJOR=20

echo "=========================================="
echo " CryptoBot — Déploiement serveur"
echo "=========================================="

# ─── 1. Swap (1 GB) ─────────────────────────────────────────
echo ""
echo "[1/9] Configuration swap 1 GB..."
if [ -f /swapfile ]; then
    echo "  → Swap déjà existant, skip"
else
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # Optimiser pour serveur avec peu de RAM
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    echo "  → Swap 1 GB activé"
fi
free -h

# ─── 2. Mise à jour système ─────────────────────────────────
echo ""
echo "[2/9] Mise à jour système + dépendances..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    build-essential git curl wget \
    sqlite3 libsqlite3-dev \
    ca-certificates gnupg

echo "  → Python : $(python3 --version)"

# ─── 3. Node.js 20 ──────────────────────────────────────────
echo ""
echo "[3/9] Installation Node.js ${NODE_MAJOR}..."
if command -v node &>/dev/null && node -v | grep -q "v${NODE_MAJOR}"; then
    echo "  → Node.js $(node -v) déjà installé"
else
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list
    apt-get update -qq
    apt-get install -y -qq nodejs
    echo "  → Node.js $(node -v), npm $(npm -v)"
fi

# ─── 4. Créer utilisateur cryptobot ─────────────────────────
echo ""
echo "[4/9] Création utilisateur ${APP_USER}..."
if id "$APP_USER" &>/dev/null; then
    echo "  → Utilisateur ${APP_USER} existe déjà"
else
    useradd -r -m -s /bin/bash "$APP_USER"
    echo "  → Utilisateur ${APP_USER} créé"
fi

# ─── 5. Copier le projet ────────────────────────────────────
echo ""
echo "[5/9] Installation du projet dans ${APP_DIR}..."
if [ -d "$APP_DIR" ]; then
    echo "  → Nettoyage ancien déploiement..."
    rm -rf "$APP_DIR"
fi

# On copie depuis le répertoire courant (le projet uploadé)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$APP_DIR"
# Copier tout sauf node_modules, venv, __pycache__, .git, data/*.db*
rsync -a \
    --exclude='node_modules' \
    --exclude='venv' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.db' \
    --exclude='*.db-wal' \
    --exclude='*.db-shm' \
    --exclude='*.db-journal' \
    --exclude='dashboard/dist' \
    --exclude='logs/' \
    "$SCRIPT_DIR/" "$APP_DIR/"

# Créer les répertoires nécessaires
mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/logs"

echo "  → Projet copié"

# ─── 6. Venv Python + dépendances ───────────────────────────
echo ""
echo "[6/9] Création venv Python + installation dépendances..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip wheel setuptools -q
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" -q
echo "  → $(${VENV_DIR}/bin/pip list 2>/dev/null | wc -l) packages installés"

# ─── 7. Build dashboard React ───────────────────────────────
echo ""
echo "[7/9] Build dashboard React (production)..."
cd "$APP_DIR/dashboard"
npm ci --production=false --loglevel=warn 2>&1 | tail -3
npm run build 2>&1 | tail -5
echo "  → Dashboard build dans dashboard/dist/"
ls -lh "$APP_DIR/dashboard/dist/" 2>/dev/null || echo "  ⚠ dist/ non trouvé"
cd "$APP_DIR"

# ─── 8. Permissions ─────────────────────────────────────────
echo ""
echo "[8/9] Configuration permissions..."
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
echo "  → ${APP_DIR} appartient à ${APP_USER}"

# ─── 9. Service systemd ─────────────────────────────────────
echo ""
echo "[9/9] Création service systemd..."

cat > /etc/systemd/system/cryptobot.service << 'UNIT'
[Unit]
Description=CryptoBot — AI Trading Bot + Dashboard
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=cryptobot
Group=cryptobot
WorkingDirectory=/opt/cryptobot
Environment=PATH=/opt/cryptobot/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/opt/cryptobot/.env
ExecStart=/opt/cryptobot/venv/bin/python -m uvicorn backend.api.server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=5

# Sécurité
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/cryptobot/data /opt/cryptobot/logs /opt/cryptobot/backend/memory

# Logs
StandardOutput=append:/opt/cryptobot/logs/cryptobot.log
StandardError=append:/opt/cryptobot/logs/cryptobot.log

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable cryptobot.service
echo "  → Service cryptobot créé et activé"

# ─── 10. Ouvrir le port 8000 (ufw si présent) ───────────────
if command -v ufw &>/dev/null; then
    echo ""
    echo "Configuration firewall..."
    ufw allow 22/tcp >/dev/null 2>&1 || true
    ufw allow 8000/tcp >/dev/null 2>&1 || true
    ufw --force enable >/dev/null 2>&1 || true
    echo "  → Ports 22 et 8000 ouverts"
fi

# ─── 11. Démarrage ──────────────────────────────────────────
echo ""
echo "=========================================="
echo " Démarrage du bot..."
echo "=========================================="
systemctl start cryptobot.service
sleep 3

if systemctl is-active --quiet cryptobot.service; then
    echo ""
    echo "=========================================="
    echo " DÉPLOIEMENT RÉUSSI"
    echo "=========================================="
    echo ""
    echo " Dashboard : http://$(curl -s ifconfig.me 2>/dev/null || echo '<IP>'):8000"
    echo " API       : http://$(curl -s ifconfig.me 2>/dev/null || echo '<IP>'):8000/api/portfolio"
    echo " WebSocket : ws://$(curl -s ifconfig.me 2>/dev/null || echo '<IP>'):8000/ws/live"
    echo ""
    echo " Commandes utiles :"
    echo "   systemctl status cryptobot     # Statut"
    echo "   systemctl restart cryptobot    # Redémarrer"
    echo "   systemctl stop cryptobot       # Arrêter"
    echo "   journalctl -u cryptobot -f     # Logs live"
    echo "   tail -f /opt/cryptobot/logs/cryptobot.log"
    echo ""
else
    echo ""
    echo "⚠ Le service n'a pas démarré correctement."
    echo "Vérifier les logs :"
    echo "  journalctl -u cryptobot -n 50 --no-pager"
    echo "  cat /opt/cryptobot/logs/cryptobot.log"
    systemctl status cryptobot.service --no-pager || true
fi
