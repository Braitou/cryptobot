# CryptoBot — Bot de trading crypto IA multi-agents

## Projet

Bot de trading crypto **intelligent** sur Binance. Des agents IA (Claude API) raisonnent,
décident et apprennent de leurs erreurs. Budget trading : 100€. Budget API : \~2€/jour.
Objectif = expérimentation. La perte totale du capital est un scénario accepté.

## Architecture — Deux couches

### Couche Python (tourne 24/7, coût = 0€)

Mécanique pure, pas d'intelligence :

* **Data Collector** : WebSocket Binance → candles, orderbook, trades
* **Signal Analyzer** : indicateurs techniques → score -1 à +1
* **Risk Guard** : filet de sécurité codé en dur (limites de risque inviolables)
* **Executor** : passe les ordres sur Binance (paper ou live)

### Couche IA (Claude API, raisonne réellement)

Chaque agent est un **prompt spécialisé** envoyé à Claude Haiku avec un contexte riche :

* **Market Analyst Agent** : analyse le contexte global du marché
* **Decision Agent** : décide d'acheter, vendre ou attendre, avec raisonnement
* **Risk Evaluator Agent** : challenge la décision, ajuste la position
* **Post-Trade Learner** : analyse chaque trade fermé, écrit dans la mémoire
* **Weekly Strategist** (Sonnet) : méta-analyse hebdo, ajuste la stratégie

### Flux d'une décision de trade

```
Signal Analyzer détecte score > 0.5 ou < -0.5
  → Market Analyst (Haiku) : "Voici les données, analyse le contexte"
    → Decision Agent (Haiku) : "Voici l'analyse + mémoire, on trade ?"
      → Risk Evaluator (Haiku) : "Voici la décision, est-ce prudent ?"
        → Risk Guard (Python) : vérifie limites dures (veto si violation)
          → Executor : passe l'ordre sur Binance
            → Post-Trade Learner (Haiku, à la clôture) : "Qu'ai-je appris ?"
              → Mémoire persistante mise à jour
```

## Stack

* **Backend** : Python 3.11+ (asyncio, FastAPI)
* **Agents IA** : Claude API (Haiku pour le quotidien, Sonnet pour l'hebdo)
* **Dashboard** : React + lightweight-charts + recharts
* **DB** : SQLite (trades, candles, logs, mémoire)
* **Paires** : BTC/USDT, ETH/USDT, SOL/USDT, AVAX/USDT, LINK/USDT

## Structure

```
cryptobot/
├── CLAUDE.md
├── PROJECT\_SPEC.md
├── requirements.txt
├── .env.example
├── backend/
│   ├── main.py                 # Orchestrateur (asyncio event loop)
│   ├── config.py               # Pydantic Settings, charge .env
│   ├── agents/
│   │   ├── base.py             # BaseAgent + AgentMessage
│   │   ├── data\_collector.py   # WebSocket Binance → données brutes
│   │   ├── signal\_analyzer.py  # Indicateurs techniques → score
│   │   ├── ai\_market\_analyst.py    # Claude Haiku — analyse contexte
│   │   ├── ai\_decision.py          # Claude Haiku — décide buy/sell/wait
│   │   ├── ai\_risk\_evaluator.py    # Claude Haiku — challenge la décision
│   │   ├── ai\_post\_trade.py        # Claude Haiku — apprend de chaque trade
│   │   ├── ai\_weekly\_strategist.py # Claude Sonnet — stratégie hebdo
│   │   ├── risk\_guard.py       # Limites dures Python (filet de sécurité)
│   │   └── executor.py         # Ordres Binance (paper + live)
│   ├── prompts/
│   │   ├── market\_analyst.py   # Prompt template du Market Analyst
│   │   ├── decision.py         # Prompt template du Decision Agent
│   │   ├── risk\_evaluator.py   # Prompt template du Risk Evaluator
│   │   ├── post\_trade.py       # Prompt template du Post-Trade Learner
│   │   └── weekly\_strategist.py # Prompt template du Weekly Strategist
│   ├── memory/
│   │   ├── manager.py          # Lecture/écriture mémoire persistante
│   │   └── memory.md           # Fichier mémoire des agents (leçons apprises)
│   ├── api/
│   │   ├── server.py           # FastAPI REST + WebSocket
│   │   └── routes.py           # Endpoints dashboard
│   ├── storage/
│   │   ├── database.py         # SQLite wrapper (aiosqlite)
│   │   └── schemas.py          # Schémas des tables
│   ├── utils/
│   │   ├── binance\_client.py   # Wrapper python-binance async
│   │   ├── claude\_client.py    # Wrapper Anthropic API (Haiku + Sonnet)
│   │   └── logger.py           # Loguru config
│   └── tests/
│       ├── test\_risk\_guard.py
│       ├── test\_signals.py
│       └── test\_prompts.py
├── dashboard/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── PriceChart.jsx
│   │   │   ├── TradeHistory.jsx
│   │   │   ├── PortfolioStats.jsx
│   │   │   ├── AgentStatus.jsx
│   │   │   ├── AgentReasoning.jsx  # Affiche le raisonnement de chaque agent
│   │   │   └── MemoryView.jsx      # Affiche la mémoire persistante
│   │   └── hooks/
│   │       └── useWebSocket.js
│   └── vite.config.js
└── scripts/
    ├── download\_history.py
    └── paper\_trade.py
```

## Conventions de code

### Python

* Async partout : tous les agents sont des coroutines async
* Type hints obligatoires sur toutes les fonctions
* Pydantic pour la validation des données et la config
* Loguru pour le logging (jamais print())
* Format : black (100 chars) + isort

```python
# Exemple : appel à un agent IA
async def call\_decision\_agent(context: MarketContext, memory: str) -> TradeDecision:
    prompt = build\_decision\_prompt(context, memory)
    response = await claude\_client.ask(model="haiku", prompt=prompt)
    return parse\_decision(response)
```

```python
# Exemple : le Risk Guard (Python pur, pas d'IA)
def check\_hard\_limits(decision: TradeDecision, portfolio: Portfolio) -> bool:
    """Retourne False si une limite dure est violée. Aucun agent IA ne peut bypass."""
    if decision.position\_size\_usdt > portfolio.capital \* MAX\_POSITION\_PCT:
        return False
    ...
```

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

## Gestion du risque

```python
# Risk Guard — limites dures (Python, pas d'IA)
MAX\_POSITION\_PCT = 0.05          # Plafond absolu : 5% du capital
STOP\_LOSS\_ATR\_MULT = 1.5        # Stop-loss = 1.5 × ATR
TAKE\_PROFIT\_ATR\_MULT = 2.0      # Take-profit = 2.0 × ATR
TRAILING\_STOP\_ATR\_MULT = 1.0    # Trailing activé à 1 × ATR de profit
MAX\_OPEN\_POSITIONS = 4
MAX\_DAILY\_LOSS\_PCT = 0.03       # -3% → stop journée
MAX\_TOTAL\_DRAWDOWN\_PCT = 0.15   # -15% → arrêt complet
```

Le Risk Evaluator (IA) raisonne sur le risque EN PLUS du Risk Guard.
Il peut réduire une position ou refuser un trade pour des raisons contextuelles.
Mais il ne peut JAMAIS dépasser les limites du Risk Guard Python.

## Mémoire persistante (backend/memory/)

Fichier markdown enrichi par le Post-Trade Learner après chaque trade.
Injecté dans le prompt de chaque agent IA comme contexte.
Taille limitée aux 50 dernières leçons pour contrôler les tokens.

## Workflow de développement

Construire dans cet ordre strict :

1. config.py + .env + database.py + schemas.py (fondations)
2. claude\_client.py (wrapper API Anthropic)
3. base.py + data\_collector.py + signal\_analyzer.py (données)
4. prompts/ (tous les templates de prompt)
5. memory/manager.py (système de mémoire)
6. ai\_market\_analyst.py + ai\_decision.py + ai\_risk\_evaluator.py (agents IA)
7. risk\_guard.py (filet de sécurité Python)
8. executor.py (paper trading d'abord)
9. main.py orchestrateur (relie tout)
10. api/server.py + dashboard React
11. ai\_post\_trade.py + ai\_weekly\_strategist.py (apprentissage)

Ne jamais passer à l'étape N+1 sans tester l'étape N.

