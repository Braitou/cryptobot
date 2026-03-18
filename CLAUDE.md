# CryptoBot v4 — Bot de trading crypto IA regime-driven

## Projet

Bot de trading crypto **intelligent** sur Binance. Des agents IA (Claude API) raisonnent,
décident et apprennent de leurs erreurs. Budget trading : 500€. Budget API : ~2€/jour.
Objectif = expérimentation. La perte totale du capital est un scénario accepté.

## Architecture v4 — Regime-driven

### Principe

L'exécution des trades est **100% Python, déterministe, < 50ms**. L'IA n'est pas dans la
boucle d'exécution — elle intervient en **stratège asynchrone** (Regime Advisor) toutes les
60 min ou sur événement urgent.

### Couche Python (tourne 24/7, coût = 0€)

Mécanique pure, pas d'intelligence :

* **Data Collector** : WebSocket Binance → candles (1m/5m/15m), orderbook, prix. Candles 1H chargées via REST au démarrage pour le RegimeDetector.
* **Signal Analyzer** : indicateurs techniques → score + classification SCALP/MOMENTUM selon le preset actif
* **Regime Detector** : ADX + EMA slope sur candles 1H → 4 régimes (RANGING, TRENDING\_UP, TRENDING\_DOWN, HIGH\_VOLATILITY). Tourne toutes les 15 min.
* **Calendar Guard** : pause automatique avant/après les événements macro (FOMC, CPI, etc.). Retourne un multiplicateur de position (0.0 à 1.0).
* **Correlation Guard** : limite l'exposition corrélée totale à 15% du capital
* **Risk Guard** : filet de sécurité codé en dur (limites de risque inviolables)
* **Executor** : passe les ordres sur Binance (paper ou live)
* **News Scraper** : collecte Fear & Greed Index, news CryptoCompare, funding rates Binance toutes les 30 min

### Couche IA (Claude API, stratège asynchrone)

* **Regime Advisor** (Haiku) : seul agent IA dans la boucle v4. Appelé toutes les 60 min ou en urgence (BTC > 3% en 30 min). Peut écrire un regime\_override + ajuster position\_size\_multiplier dans config.json.
* **Post-Trade Logger** (Haiku) : analyse chaque trade fermé, écrit des tags numériques (entry\_quality, exit\_quality, régime) dans la table trade\_tags.

### Flux d'une décision de trade (v4)

```
RegimeDetector (Python, toutes les 15 min)
  → Détecte le régime via ADX sur candles 1H
    → ConfigManager charge le preset correspondant

Signal Analyzer détecte un score sur candle 5m fermée
  → Classifie le signal (SCALP_LONG / SCALP_SHORT_EXIT / MOMENTUM / NO_SIGNAL)
    → Calendar Guard : vérifie événements macro → multiplicateur
      → Correlation Guard : vérifie exposition corrélée
        → Risk Guard (Python) : vérifie limites dures (veto si violation)
          → Executor : passe l'ordre sur Binance
            → Post-Trade Logger (Haiku, à la clôture) : tags numériques

En parallèle (toutes les 60 min ou sur urgence) :
Regime Advisor (Haiku) → peut override le régime dans config.json
```

## Stack

* **Backend** : Python 3.11+ (asyncio, FastAPI)
* **Agents IA** : Claude API (Haiku 4.5 pour le quotidien, Sonnet 4.6 en réserve)
* **Dashboard** : React + lightweight-charts + recharts + Tailwind
* **DB** : SQLite (trades, candles, logs, trade\_tags, news\_cache)
* **Config** : config.json (régime actif + overrides IA) + presets.py (paramètres par régime)
* **Paires** : BTC/USDT, ETH/USDT, SOL/USDT, AVAX/USDT, LINK/USDT

## Structure

```
cryptobot/
├── CLAUDE.md
├── PROJECT_SPEC.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── data/
│   ├── config.json             # Config dynamique (régime, overrides IA, statuts paires)
│   └── cryptobot.db            # SQLite (trades, candles, logs, tags, news)
├── backend/
│   ├── main.py                 # Orchestrateur v4 (asyncio event loop, regime loop)
│   ├── config.py               # Pydantic Settings, charge .env
│   ├── config_manager.py       # Lecture/écriture atomique config.json + fallback
│   ├── presets.py              # Presets par régime (codés en dur, non modifiables par l'IA)
│   ├── economic_calendar.json  # Calendrier macro (FOMC, CPI, NFP…)
│   ├── agents/
│   │   ├── base.py             # BaseAgent + AgentMessage
│   │   ├── data_collector.py   # WebSocket Binance → candles + orderbook
│   │   ├── signal_analyzer.py  # Indicateurs techniques → score + classification
│   │   ├── regime_detector.py  # ADX + EMA slope sur 1H → régime de marché
│   │   ├── calendar_guard.py   # Pause auto avant événements macro
│   │   ├── correlation_guard.py # Limite exposition corrélée à 15%
│   │   ├── risk_guard.py       # Limites dures Python (filet de sécurité)
│   │   ├── executor.py         # Ordres Binance (paper + live)
│   │   ├── news_scraper.py     # Fear & Greed, news, funding rates
│   │   ├── ai_regime_advisor.py    # Claude Haiku — stratège régime (seul IA écrivant config.json)
│   │   ├── ai_post_trade_logger.py # Claude Haiku — tags numériques post-trade
│   │   ├── ai_market_analyst.py    # Claude Haiku — analyse contexte (legacy v3)
│   │   ├── ai_decision.py          # Claude Haiku — décision buy/sell/wait (legacy v3)
│   │   ├── ai_risk_evaluator.py    # Claude Haiku — challenge décision (legacy v3)
│   │   └── ai_post_trade.py        # Claude Haiku — learner narratif (legacy v3)
│   ├── prompts/
│   │   ├── market_analyst.py
│   │   ├── decision.py
│   │   ├── risk_evaluator.py
│   │   ├── post_trade.py
│   │   └── weekly_strategist.py
│   ├── memory/
│   │   ├── manager.py          # Lecture/écriture mémoire persistante
│   │   └── memory.md           # Fichier mémoire des agents (leçons apprises)
│   ├── api/
│   │   ├── server.py           # FastAPI REST + WebSocket
│   │   └── routes.py           # Endpoints dashboard
│   ├── storage/
│   │   ├── database.py         # SQLite wrapper (aiosqlite), DB dans data/
│   │   └── schemas.py          # Schémas des tables (candles, trades, agent_logs, trade_tags, news_cache)
│   └── utils/
│       ├── binance_client.py   # Wrapper python-binance async (spot uniquement)
│       ├── claude_client.py    # Wrapper Anthropic API (Haiku + Sonnet)
│       └── logger.py           # Loguru config
├── dashboard/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── App.jsx
│       ├── main.jsx
│       ├── index.css
│       ├── components/
│       │   ├── Header.jsx
│       │   ├── MetricCards.jsx         # Métriques principales (capital, P&L, drawdown)
│       │   ├── PriceChart.jsx          # Chart prix avec lightweight-charts
│       │   ├── RegimePanel.jsx         # Régime actif + détails ADX
│       │   ├── RegimeBar.jsx           # Barre compacte du régime
│       │   ├── GuardsPanel.jsx         # État des garde-fous (calendar, correlation)
│       │   ├── SignalStats.jsx         # Compteurs signaux filtrés/exécutés
│       │   ├── OpenPositions.jsx       # Positions ouvertes + P&L non réalisé
│       │   ├── TradeHistory.jsx        # Historique des trades
│       │   ├── EquityCurve.jsx         # Courbe d'équité
│       │   ├── PairWinRate.jsx         # Win rate par paire
│       │   ├── AtrPanel.jsx            # Valeurs ATR courantes
│       │   ├── AIFeed.jsx              # Feed décisions IA en temps réel
│       │   ├── AIMetricCards.jsx        # Coûts et stats IA
│       │   ├── AgentStatus.jsx         # Statut des agents
│       │   ├── AgentReasoning.jsx      # Raisonnement détaillé des agents
│       │   ├── LiveFeed.jsx            # Feed WebSocket temps réel
│       │   ├── LearningCurve.jsx       # Courbe d'apprentissage
│       │   ├── MemoryView.jsx          # Mémoire persistante
│       │   └── KillSwitch.jsx          # Bouton kill switch
│       └── hooks/
│           ├── useWebSocket.js
│           └── usePortfolio.js
└── scripts/
    ├── deploy.ps1              # Déploiement automatisé (git push + SSH + rebuild)
    ├── server-update.sh        # Script serveur (git pull + restart)
    └── download_history.py     # Téléchargement historique candles
```

## Conventions de code

### Python

* Async partout : tous les agents sont des coroutines async
* Type hints obligatoires sur toutes les fonctions
* Pydantic pour la validation des données et la config
* Loguru pour le logging (jamais print())
* Format : black (100 chars) + isort

### Prompts (backend/prompts/)

* Chaque agent IA a son fichier de prompt dédié
* Les prompts sont des fonctions Python qui construisent le message
* Toujours injecter la mémoire persistante dans le contexte
* Demander une réponse JSON structurée pour parser facilement

### React/JS

* Composants fonctionnels + hooks
* Tailwind pour le style
* Vite comme bundler

## Règles critiques

1. **JAMAIS de clé API dans le code** — tout dans .env
2. **JAMAIS de futures/margin/levier** — spot uniquement
3. **Le Risk Guard Python est INVIOLABLE** — même si l'IA dit "trade", Python refuse si limites dépassées
4. **Chaque trade loggé dans SQLite AVANT exécution**
5. **Stop-loss obligatoire** sur chaque position, sans exception
6. **Chaque décision IA doit être loggée** — le raisonnement complet est sauvegardé
7. **Kill switch** : perte jour > 3% OU drawdown > 15% → arrêt immédiat
8. **config.json dans data/** (writable) — jamais dans backend/ (read-only en production)

## Gestion du risque

```python
# Risk Guard — limites dures (Python, pas d'IA)
MAX_POSITION_PCT = 0.10              # 10% du capital par position
MAX_OPEN_POSITIONS = 5
MAX_POSITIONS_PER_PAIR = 1
MAX_DAILY_LOSS_PCT = 0.03            # -3% → stop journée
MAX_TOTAL_DRAWDOWN_PCT = 0.15        # -15% → arrêt complet

# Caps SL/TP par mode
SCALP_MAX_SL_PCT = 0.5%             # Cap SL scalp
SCALP_MAX_TP_PCT = 1.0%             # Cap TP scalp
MOMENTUM_MAX_SL_PCT = 2.0%          # Cap SL momentum
MOMENTUM_MAX_TP_PCT = 3.0%          # Cap TP momentum

# Trailing stop (basé sur %)
TRAILING_STOP_ACTIVATION_PCT = 0.6%  # Activation à +0.6%
TRAILING_STOP_DISTANCE_PCT = 0.3%   # Distance trailing 0.3%

# Cooldown
PAIR_COOLDOWN_AFTER_SL_MINUTES = 15  # 15 min de cooldown après un SL
```

Le Regime Advisor (IA) peut ajuster position\_size\_multiplier (cap 1.5x) et
écrire un regime\_override temporaire. Mais il ne peut JAMAIS dépasser les
limites du Risk Guard Python.

## Config dynamique (data/config.json)

Géré par ConfigManager avec écriture atomique (tmp + os.replace) et fallback.

```json
{
  "active_regime": "RANGING",
  "regime_source": "python_adx",
  "regime_override": null,
  "regime_override_expires": null,
  "global": {
    "trading_enabled": true,
    "position_size_multiplier": 1.0,
    "calendar_multiplier": 1.0,
    "pause_until": null
  },
  "pair_status": {
    "BTCUSDT": "active",
    "ETHUSDT": "active",
    "SOLUSDT": "active",
    "LINKUSDT": "momentum_only",
    "AVAXUSDT": "momentum_only"
  }
}
```

**Qui écrit dans config.json :**
* RegimeDetector (Python) → active\_regime
* Regime Advisor (IA) → regime\_override + position\_size\_multiplier
* CalendarGuard (Python) → calendar\_multiplier

## Presets par régime (backend/presets.py)

4 presets codés en dur, NON modifiables par l'IA :
* **RANGING** : scalp mean reversion, pas de momentum
* **TRENDING\_UP** : scalp réduit + momentum long activé
* **TRENDING\_DOWN** : scalp inversé + momentum short activé
* **HIGH\_VOLATILITY** : scalp désactivé, momentum prudent

Chaque preset définit : RSI thresholds, BB thresholds, volume ratio min,
ATR multiples pour SL/TP, position sizing, paires actives par mode.

## Mémoire persistante (backend/memory/)

Fichier markdown enrichi par le Post-Trade Learner après chaque trade.
Injecté dans le prompt de chaque agent IA comme contexte.
Taille limitée aux 50 dernières leçons pour contrôler les tokens.

En v4, le Post-Trade Logger ajoute aussi des tags numériques dans la table
trade\_tags (entry\_quality, exit\_quality, régime, tags JSON).

## Boucle principale (main.py)

```
Toutes les 5 min :
  → Vérifier trigger urgence BTC (> 3% en 30 min → appel Regime Advisor)

Toutes les 15 min :
  → RegimeDetector (ADX sur candles 1H BTCUSDT)
  → Mise à jour config.json si changement de régime

Toutes les 60 min :
  → Regime Advisor IA (Haiku) — analyse régime + news + portfolio

En continu :
  → DataCollector (WebSocket candles + orderbook)
  → Dispatcher (candle_closed → SignalAnalyzer → Guards → Executor)
  → Executor monitor (trailing stop, timeouts, SL/TP)
```

## Déploiement (serveur DigitalOcean)

* **Serveur** : DigitalOcean 512 MB RAM, IP `146.190.31.71`, user `root`
* **Le bot tourne 24/7** sur le serveur via systemd (`cryptobot.service`)
* **Tout est servi sur le port 8000** : API + WebSocket + Dashboard React (fichiers statiques via FastAPI)
* **Dashboard** : `http://146.190.31.71:8000`
* **Projet installé dans** `/opt/cryptobot` (user système `cryptobot`)
* **Le .env sur le serveur** contient les vraies clés API (pas dans git)

### Déployer un changement

Après chaque modification du code, lancer depuis PowerShell :

```powershell
.\scripts\deploy.ps1
```

Ce script fait : `git push` → SSH sur le serveur → `git pull` → rebuild dashboard → restart service.

Ou manuellement :

```bash
git push
ssh root@146.190.31.71 "cd /opt/cryptobot && git pull origin main && cd dashboard && npm run build && systemctl restart cryptobot"
```

### Commandes utiles sur le serveur (via SSH)

```bash
ssh root@146.190.31.71                          # Se connecter
systemctl status cryptobot                       # Statut du bot
systemctl restart cryptobot                      # Redémarrer
journalctl -u cryptobot -f                       # Logs en direct
journalctl -u cryptobot --since '1 hour ago'     # Logs récents
```

### Modifier le .env sur le serveur

Le `.env` n'est PAS dans git. Pour changer une valeur (paires, capital, etc.) :

```bash
ssh root@146.190.31.71
nano /opt/cryptobot/.env
systemctl restart cryptobot
```
