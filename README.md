# CryptoBot v0.1

Bot de trading crypto **intelligent** — des agents IA (Claude) raisonnent, décident et apprennent.
Budget : 100€ de capital + ~2€/jour en tokens API.

## Architecture

```
Signal détecté (Python, gratuit)
  → Market Analyst (Claude Haiku) — analyse le contexte
    → Decision Agent (Claude Haiku) — décide buy/sell/wait avec raisonnement
      → Risk Evaluator (Claude Haiku) — challenge la décision
        → Risk Guard (Python) — filet de sécurité inviolable
          → Executor — passe l'ordre sur Binance
            → Post-Trade Learner (Claude Haiku) — apprend de chaque trade
              → Mémoire persistante — leçons accumulées au fil du temps
```

## Quick Start

```bash
# 1. Setup
cp .env.example .env          # Remplir Binance + Anthropic API keys
pip install -r requirements.txt
cd dashboard && npm install && cd ..

# 2. Télécharger l'historique
python scripts/download_history.py --days 30

# 3. Lancer le bot (paper trading)
python -m backend.main

# 4. Dashboard (autre terminal)
cd dashboard && npm run dev
```

## Documentation

- `CLAUDE.md` — Instructions pour Claude Code
- `PROJECT_SPEC.md` — Spécification technique complète
