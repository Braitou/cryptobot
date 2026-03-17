# ============================================================
# deploy.ps1 — Push local + déploiement serveur en une commande
# Usage depuis PowerShell : .\scripts\deploy.ps1
# ============================================================

$SERVER = "146.190.31.71"
$SERVER_USER = "root"

Write-Host "=== CryptoBot — Push & Deploy ===" -ForegroundColor Cyan

# 1. Push vers GitHub
Write-Host "[1/2] Push vers GitHub..." -ForegroundColor Yellow
git add -A
$hasChanges = git diff --cached --quiet; $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    $msg = Read-Host "Message de commit"
    if ([string]::IsNullOrWhiteSpace($msg)) { $msg = "update" }
    git commit -m "$msg`n`nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
}
git push origin main
Write-Host "  -> Code pousse sur GitHub" -ForegroundColor Green

# 2. Deployer sur le serveur
Write-Host "[2/2] Deploiement sur le serveur..." -ForegroundColor Yellow
ssh "${SERVER_USER}@${SERVER}" "sudo /opt/cryptobot/scripts/server-update.sh"

Write-Host ""
Write-Host "=== DEPLOIEMENT TERMINE ===" -ForegroundColor Green
Write-Host "Dashboard : http://${SERVER}:8000" -ForegroundColor Cyan
