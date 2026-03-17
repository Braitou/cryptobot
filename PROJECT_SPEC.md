# CryptoBot v0.1 — Spécification technique détaillée

## Vision

Bot de trading crypto où des agents IA (Claude) raisonnent réellement à chaque décision,
apprennent de leurs erreurs via une mémoire persistante, et s'améliorent avec le temps.
Budget trading : 100€. Budget API : ~2€/jour.

---

## 1. Fondations

### 1.1 Config (config.py)

```python
class Settings(BaseSettings):
    # Binance
    BINANCE_API_KEY: str
    BINANCE_API_SECRET: str
    BINANCE_TESTNET: bool = True

    # Trading
    PAIRS: list[str] = ["BTCUSDT", "ETHUSDT"]
    CANDLE_INTERVALS: list[str] = ["1m", "5m", "15m"]
    TRADING_MODE: Literal["paper", "live"] = "paper"
    INITIAL_CAPITAL: float = 100.0

    # Risk Guard (limites dures Python)
    MAX_POSITION_PCT: float = 0.05
    STOP_LOSS_ATR_MULT: float = 1.5
    TAKE_PROFIT_ATR_MULT: float = 2.0
    TRAILING_STOP_ATR_MULT: float = 1.0
    MAX_OPEN_POSITIONS: int = 2
    MAX_DAILY_LOSS_PCT: float = 0.03
    MAX_TOTAL_DRAWDOWN_PCT: float = 0.15

    # Claude API
    ANTHROPIC_API_KEY: str
    AI_MODEL_FAST: str = "claude-haiku-4-5-20251001"   # Agents quotidiens
    AI_MODEL_DEEP: str = "claude-sonnet-4-6"            # Stratégiste hebdo
    AI_MAX_TOKENS: int = 1024
    AI_TEMPERATURE: float = 0.3       # Bas = plus déterministe

    # API Dashboard
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    model_config = SettingsConfigDict(env_file=".env")
```

### 1.2 Base de données SQLite (storage/schemas.py)

```sql
CREATE TABLE candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER NOT NULL,
    quote_volume REAL NOT NULL,
    trades_count INTEGER NOT NULL,
    UNIQUE(pair, interval, open_time)
);

CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,                    -- "BUY" ou "SELL"
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity REAL NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',   -- open, closed_tp, closed_sl, closed_trailing, closed_timeout, closed_manual
    pnl REAL,
    pnl_pct REAL,
    fees_paid REAL DEFAULT 0,

    -- Contexte IA au moment de l'entrée
    signal_score REAL,
    market_analysis TEXT,                  -- Réponse complète du Market Analyst
    decision_reasoning TEXT,               -- Raisonnement du Decision Agent
    risk_evaluation TEXT,                  -- Évaluation du Risk Evaluator
    indicators_snapshot TEXT,              -- JSON des indicateurs

    -- Contexte IA à la sortie
    post_trade_analysis TEXT,              -- Analyse du Post-Trade Learner
    lesson_learned TEXT,                   -- Leçon extraite pour la mémoire

    binance_order_id TEXT
);

CREATE TABLE agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    agent TEXT NOT NULL,
    action TEXT NOT NULL,                  -- "analyze", "decide", "evaluate", "learn"
    prompt_sent TEXT,                      -- Le prompt envoyé (pour debug)
    response_received TEXT,                -- La réponse Claude complète
    tokens_used INTEGER,                   -- Suivi consommation API
    cost_usd REAL,                         -- Coût estimé de l'appel
    duration_ms INTEGER,                   -- Latence de l'appel
    data TEXT                              -- JSON contexte additionnel
);

CREATE TABLE portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    total_capital REAL NOT NULL,
    available_cash REAL NOT NULL,
    open_positions INTEGER NOT NULL,
    daily_pnl REAL NOT NULL,
    daily_pnl_pct REAL NOT NULL,
    total_pnl REAL NOT NULL,
    total_pnl_pct REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    total_api_cost REAL NOT NULL           -- Coût API cumulé
);

CREATE TABLE memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source_trade_id INTEGER,               -- Trade qui a généré la leçon
    category TEXT NOT NULL,                 -- "pattern", "mistake", "insight", "rule"
    content TEXT NOT NULL,                  -- La leçon en texte
    confidence REAL DEFAULT 0.5,           -- 0-1, augmente si la leçon se confirme
    times_referenced INTEGER DEFAULT 0,    -- Nb de fois citée par les agents
    active BOOLEAN DEFAULT TRUE            -- Désactivée si contredite
);
```

### 1.3 Claude Client (utils/claude_client.py)

Wrapper centralisé pour tous les appels API :

```python
class ClaudeClient:
    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def ask(
        self,
        model: str,          # "haiku" ou "sonnet"
        system: str,         # System prompt (rôle de l'agent)
        prompt: str,         # User prompt (contexte + question)
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> ClaudeResponse:
        """Appelle Claude et retourne la réponse + métadonnées.
        - Gère les retries (3 tentatives, backoff exponentiel)
        - Log chaque appel dans agent_logs (tokens, coût, latence)
        - Parse le JSON si la réponse en contient
        - Calcule le coût estimé :
          Haiku : $0.80/M input, $4/M output
          Sonnet : $3/M input, $15/M output
        """
        ...

    async def ask_json(self, model: str, system: str, prompt: str, schema: dict) -> dict:
        """Comme ask() mais force une réponse JSON valide.
        Ajoute au prompt : "Réponds UNIQUEMENT en JSON valide suivant ce schéma: {schema}"
        Retry une fois si le JSON est invalide.
        """
        ...
```

```python
@dataclass
class ClaudeResponse:
    content: str              # Texte de la réponse
    json_data: dict | None    # Parsé si JSON détecté
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_ms: int
    model: str
```

---

## 2. Couche Python (mécanique, 0€)

### 2.1 Data Collector (agents/data_collector.py)

Identique à la v1 — collecte données Binance via WebSocket.

Streams : `{pair}@kline_{interval}`, `{pair}@depth20@100ms`, `{pair}@trade`

```python
class DataCollector(BaseAgent):
    async def _on_candle(self, pair: str, interval: str, candle: dict):
        """Insère dans SQLite + publie 'candle_closed' sur le bus."""
        ...

    async def _on_orderbook(self, pair: str, data: dict):
        """Met à jour le cache mémoire + publie 'orderbook_update'.
        Calcule : bid_ask_spread, imbalance_ratio
        """
        ...

    async def get_recent_candles(self, pair: str, interval: str, limit: int = 100) -> pd.DataFrame:
        ...
```

Reconnexion automatique avec backoff exponentiel (1s → 60s max).

### 2.2 Signal Analyzer (agents/signal_analyzer.py)

Calcule les indicateurs techniques et filtre le bruit.
**Ne prend aucune décision** — il détecte simplement quand le marché est "intéressant".

```python
class SignalAnalyzer(BaseAgent):
    def _compute_indicators(self, df: pd.DataFrame) -> dict:
        """Retourne :
        {
            "rsi_14": float,          # 0-100
            "macd_line": float,
            "macd_signal": float,
            "macd_histogram": float,
            "bb_upper": float,
            "bb_middle": float,
            "bb_lower": float,
            "bb_pct": float,          # 0=lower, 1=upper
            "vwap": float,
            "ema_9": float,
            "ema_21": float,
            "atr_14": float,
            "volume_ratio": float,    # volume / SMA(volume, 20)
            "price_change_5m": float, # % change
            "price_change_15m": float,
            "price_change_1h": float,
        }
        """
        ...

    def _compute_score(self, indicators: dict, orderbook: dict) -> float:
        """Score composite -1.0 à +1.0.
        Pondération :
        - Tendance (EMA9 vs EMA21 + prix vs VWAP) : 30%
        - Momentum (RSI + MACD) : 30%
        - Volatilité (Bollinger %B) : 20%
        - Order book (imbalance) : 20%
        """
        ...
```

**Seuil de déclenchement des agents IA** :
- score > +0.5 ou < -0.5 → réveiller la chaîne d'agents IA
- entre -0.5 et +0.5 → ne rien faire (économise les tokens API)

C'est ce seuil qui contrôle le coût API : plus il est haut, moins on appelle Claude.

### 2.3 Risk Guard (agents/risk_guard.py)

**Filet de sécurité Python pur.** Aucun agent IA ne peut le contourner.

```python
class RiskGuard:
    """Vérifications binaires. Pas de raisonnement, pas d'IA.
    Si une limite est dépassée → rejet immédiat, pas de discussion."""

    def check(self, decision: TradeDecision, portfolio: Portfolio) -> RiskVerdict:
        """Séquence de vérification (court-circuit au premier refus) :
        1. Kill switch actif ? → REJECT
        2. position_size > MAX_POSITION_PCT × capital ? → REJECT
        3. Positions ouvertes >= MAX_OPEN_POSITIONS ? → REJECT
        4. Perte journalière >= MAX_DAILY_LOSS_PCT ? → REJECT + kill switch jour
        5. Drawdown >= MAX_TOTAL_DRAWDOWN_PCT ? → REJECT + kill switch total
        6. Stop-loss absent ou mal placé ? → REJECT
        7. Montant < minimum Binance (~5 USDT) ? → REJECT
        Sinon → APPROVE
        """
        ...

    def compute_stop_loss(self, entry_price: float, side: str, atr: float) -> float:
        """BUY → entry - 1.5 × ATR | SELL → entry + 1.5 × ATR"""
        ...

    def compute_take_profit(self, entry_price: float, side: str, atr: float) -> float:
        """BUY → entry + 2.0 × ATR | SELL → entry - 2.0 × ATR"""
        ...

    def check_trailing_stop(self, trade: dict, current_price: float, atr: float) -> bool:
        """Active à 1 × ATR de profit. Suit avec offset de 1 × ATR."""
        ...
```

### 2.4 Executor (agents/executor.py)

```python
class OrderExecutor(BaseAgent):
    async def execute(self, decision: TradeDecision) -> ExecutionResult:
        """Séquence :
        1. Log dans SQLite (status='pending')
        2. Paper → prix actuel + slippage 0.05%, fees 0.1%
        3. Live → limit order, fallback market après 30s, puis OCO (TP+SL)
        4. Update SQLite (status='open')
        5. Publie 'order_executed' sur le bus
        """
        ...

    async def monitor_open_positions(self):
        """Toutes les 5 secondes :
        - SL/TP touché ?
        - Trailing stop touché ?
        - Timeout > 4h → fermer (scalping)
        """
        ...
```

---

## 3. Couche IA — Agents Claude

### 3.1 Système de mémoire (memory/manager.py)

La mémoire est ce qui rend le bot intelligent au fil du temps.

```python
class MemoryManager:
    def __init__(self, db: Database):
        self.db = db

    async def get_context(self, max_entries: int = 30) -> str:
        """Retourne les leçons actives, triées par confidence × pertinence.
        Format markdown injecté dans les prompts :

        ## Leçons apprises (30 plus récentes/pertinentes)
        - [pattern] Les faux breakouts Bollinger sont fréquents entre 2h-5h UTC (confiance: 0.8)
        - [mistake] Ne pas acheter quand RSI < 30 mais volume en baisse — signal trompeur (confiance: 0.7)
        - [insight] ETH suit BTC avec 5-10min de retard lors de gros mouvements (confiance: 0.6)
        - [rule] Réduire la position de 50% quand ATR > 2× sa moyenne 24h (confiance: 0.9)
        """
        ...

    async def add_lesson(self, trade_id: int, category: str, content: str, confidence: float = 0.5):
        """Ajoute une leçon. Vérifie les doublons (cosine similarity basique).
        Si une leçon similaire existe → augmente sa confidence au lieu d'ajouter.
        """
        ...

    async def reinforce(self, entry_id: int):
        """Augmente la confidence d'une leçon quand elle se confirme."""
        ...

    async def weaken(self, entry_id: int):
        """Réduit la confidence. Désactive si < 0.2."""
        ...

    async def get_recent_trades_summary(self, n: int = 10) -> str:
        """Résumé des N derniers trades pour le contexte des agents.
        Format :
        ## 10 derniers trades
        1. BTC/USDT BUY +1.2% (TP touché, 45min) — RSI rebond + MACD cross
        2. ETH/USDT BUY -1.8% (SL touché, 12min) — Faux breakout Bollinger
        ...
        Bilan : 6 wins, 4 losses, win rate 60%, profit factor 1.4
        """
        ...
```

### 3.2 Market Analyst Agent (agents/ai_market_analyst.py)

**Rôle** : Analyser le contexte du marché avant toute décision.
**Quand** : À chaque signal fort (score > 0.5 ou < -0.5)
**Modèle** : Haiku

```python
class MarketAnalystAgent(BaseAgent):
    async def analyze(self, pair: str, indicators: dict, orderbook: dict) -> MarketAnalysis:
        memory = await self.memory.get_context()
        recent_trades = await self.memory.get_recent_trades_summary()

        prompt = build_market_analyst_prompt(
            pair=pair,
            indicators=indicators,
            orderbook=orderbook,
            memory=memory,
            recent_trades=recent_trades,
        )
        response = await self.claude.ask_json(
            model="haiku",
            system=MARKET_ANALYST_SYSTEM,
            prompt=prompt,
            schema=MARKET_ANALYSIS_SCHEMA,
        )
        return MarketAnalysis(**response.json_data)
```

**System prompt** (prompts/market_analyst.py) :
```python
MARKET_ANALYST_SYSTEM = """Tu es un analyste de marché crypto expérimenté.
Ton rôle est d'analyser l'état actuel du marché et de fournir un contexte
clair au Decision Agent qui prendra la décision finale.

Tu NE prends PAS de décision de trading. Tu analyses et tu décris.

Tu as accès à :
- Les indicateurs techniques actuels
- L'état de l'order book
- La mémoire des leçons apprises sur les trades passés
- L'historique récent des trades

Sois concis, factuel, et mentionne explicitement les risques que tu identifies.
Réponds UNIQUEMENT en JSON."""
```

**Prompt template** :
```python
def build_market_analyst_prompt(pair, indicators, orderbook, memory, recent_trades) -> str:
    return f"""Analyse le marché {pair} avec ces données :

## Indicateurs techniques
{json.dumps(indicators, indent=2)}

## Order book
- Spread: {orderbook['bid_ask_spread']}%
- Imbalance (bid/total): {orderbook['imbalance_ratio']}

{memory}

{recent_trades}

Réponds en JSON :
{{
  "market_regime": "trending_up|trending_down|ranging|volatile",
  "strength": 0.0 à 1.0,
  "key_observations": ["observation 1", "observation 2", ...],
  "risks": ["risque 1", "risque 2", ...],
  "relevant_memory": ["leçon pertinente 1", ...],
  "summary": "Résumé en 2-3 phrases"
}}"""
```

**MarketAnalysis** :
```python
@dataclass
class MarketAnalysis:
    market_regime: str       # trending_up, trending_down, ranging, volatile
    strength: float          # 0-1
    key_observations: list[str]
    risks: list[str]
    relevant_memory: list[str]
    summary: str
```

---

### 3.3 Decision Agent (agents/ai_decision.py)

**Rôle** : Décider d'acheter, vendre, ou attendre — avec un raisonnement explicite.
**Quand** : Après le Market Analyst
**Modèle** : Haiku

```python
class DecisionAgent(BaseAgent):
    async def decide(self, pair: str, signal_score: float,
                     analysis: MarketAnalysis, indicators: dict) -> TradeDecision:
        memory = await self.memory.get_context()
        recent_trades = await self.memory.get_recent_trades_summary()

        prompt = build_decision_prompt(
            pair=pair,
            signal_score=signal_score,
            analysis=analysis,
            indicators=indicators,
            memory=memory,
            recent_trades=recent_trades,
            portfolio=await self.get_portfolio_state(),
        )
        response = await self.claude.ask_json(
            model="haiku",
            system=DECISION_AGENT_SYSTEM,
            prompt=prompt,
            schema=TRADE_DECISION_SCHEMA,
        )
        return TradeDecision(**response.json_data)
```

**System prompt** (prompts/decision.py) :
```python
DECISION_AGENT_SYSTEM = """Tu es un trader crypto expérimenté qui gère un portefeuille de 100€.
Ton approche est du scalping (trades de quelques minutes à quelques heures).

Ton rôle est de décider : BUY, SELL, ou WAIT.

Principes :
- Tu es CONSERVATEUR. En cas de doute, tu attends (WAIT).
- Tu ne trades que quand tu as une conviction claire et argumentée.
- Tu apprends de tes erreurs passées (mémoire fournie).
- Tu prends en compte le contexte global fourni par le Market Analyst.
- Tu ne risques JAMAIS plus de 5% du capital sur un seul trade.
- Tu donnes TOUJOURS un raisonnement clair pour ta décision.

IMPORTANT : Si la mémoire mentionne une erreur similaire à la situation actuelle,
tu dois en tenir compte explicitement dans ton raisonnement.

Réponds UNIQUEMENT en JSON."""
```

**Prompt template** :
```python
def build_decision_prompt(pair, signal_score, analysis, indicators,
                          memory, recent_trades, portfolio) -> str:
    return f"""## Décision de trade — {pair}

### Signal technique
Score composite : {signal_score} ({'achat fort' if signal_score > 0.5 else 'vente forte'})

### Analyse du Market Analyst
Régime : {analysis.market_regime} (force: {analysis.strength})
Observations : {', '.join(analysis.key_observations)}
Risques identifiés : {', '.join(analysis.risks)}
Résumé : {analysis.summary}

### Indicateurs clés
RSI: {indicators['rsi_14']:.1f} | MACD hist: {indicators['macd_histogram']:.4f}
Bollinger %B: {indicators['bb_pct']:.2f} | Volume ratio: {indicators['volume_ratio']:.1f}x
ATR: {indicators['atr_14']:.2f} | EMA9 vs EMA21: {'↑' if indicators['ema_9'] > indicators['ema_21'] else '↓'}

### Portefeuille
Capital: {portfolio['capital']:.2f} USDT | Positions ouvertes: {portfolio['open_positions']}
P&L aujourd'hui: {portfolio['daily_pnl']:.2f} USDT ({portfolio['daily_pnl_pct']:.1f}%)
Drawdown total: {portfolio['drawdown_pct']:.1f}%

{memory}

{recent_trades}

Décide. Réponds en JSON :
{{
  "action": "BUY|SELL|WAIT",
  "confidence": 0.0 à 1.0,
  "reasoning": "Explication détaillée de ta décision en 3-5 phrases",
  "position_size_pct": 0.01 à 0.05 (% du capital à risquer, 0 si WAIT),
  "expected_holding_time": "5min|15min|1h|4h",
  "key_factors": ["facteur 1", "facteur 2", ...],
  "risks_acknowledged": ["risque 1", ...]
}}"""
```

**TradeDecision** :
```python
@dataclass
class TradeDecision:
    action: str                    # BUY, SELL, WAIT
    confidence: float              # 0-1
    reasoning: str                 # Raisonnement complet
    position_size_pct: float       # % du capital
    expected_holding_time: str
    key_factors: list[str]
    risks_acknowledged: list[str]
    # Ajoutés par le Risk Guard après validation :
    quantity: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
```

---

### 3.4 Risk Evaluator Agent (agents/ai_risk_evaluator.py)

**Rôle** : Challenger la décision du Decision Agent. Peut réduire ou refuser.
**Quand** : Après le Decision Agent, si action ≠ WAIT
**Modèle** : Haiku

**System prompt** (prompts/risk_evaluator.py) :
```python
RISK_EVALUATOR_SYSTEM = """Tu es un gestionnaire de risque. Tu ne trades PAS.
Tu reçois une décision de trade et tu la challenges.

Ton rôle :
- Identifier les failles dans le raisonnement du Decision Agent
- Vérifier que le sizing est approprié au contexte
- Réduire la position si le risque te semble trop élevé
- Refuser le trade si tu identifies un danger non pris en compte

Tu es le gardien du capital. Tu préfères rater une opportunité que perdre de l'argent.
Si la mémoire contient des leçons pertinentes, cite-les.

Réponds UNIQUEMENT en JSON."""
```

**Réponse attendue** :
```json
{
  "verdict": "APPROVE|REDUCE|REJECT",
  "adjusted_position_pct": 0.03,
  "reasoning": "Le Decision Agent a raison sur le signal mais sous-estime la volatilité actuelle. ATR est 1.5× sa moyenne, je réduis la position de 5% à 3%.",
  "concerns": ["Volatilité élevée", "Deux pertes consécutives aujourd'hui"],
  "referenced_memory": ["Leçon #12: réduire quand ATR > 1.5× moyenne"]
}
```

---

### 3.5 Post-Trade Learner (agents/ai_post_trade.py)

**Rôle** : Analyser chaque trade fermé et écrire dans la mémoire.
**Quand** : À chaque clôture de position
**Modèle** : Haiku

**System prompt** (prompts/post_trade.py) :
```python
POST_TRADE_SYSTEM = """Tu es un analyste post-trade. Tu examines un trade terminé
et tu en extrais une leçon pour l'avenir.

Ton rôle :
- Comprendre POURQUOI le trade a gagné ou perdu
- Identifier ce qui aurait pu être fait différemment
- Formuler une leçon concise et actionnable
- Classer la leçon : pattern, mistake, insight, ou rule
- Évaluer ta confiance dans cette leçon (0.0 à 1.0)

Une bonne leçon est :
- Spécifique (pas "faire attention au marché")
- Actionnable (un autre agent peut l'utiliser)
- Vérifiable (on peut savoir si elle s'applique)

Exemples de bonnes leçons :
- [pattern] "Quand RSI < 25 ET volume > 3× moyenne → le rebond arrive dans les 10min"
- [mistake] "Ne pas acheter sur un signal RSI < 30 quand la tendance 15m est baissière"
- [rule] "Toujours attendre la confirmation MACD avant d'entrer sur un signal Bollinger"

Réponds UNIQUEMENT en JSON."""
```

**Prompt template** :
```python
def build_post_trade_prompt(trade, indicators_at_entry, indicators_at_exit, memory) -> str:
    return f"""## Analyse post-trade

### Le trade
Paire: {trade['pair']} | Side: {trade['side']}
Entrée: {trade['entry_price']} à {trade['entry_time']}
Sortie: {trade['exit_price']} à {trade['exit_time']}
Résultat: {trade['pnl_pct']:+.2f}% ({trade['pnl']:+.2f} USDT)
Durée: {trade['duration_minutes']}min
Sortie par: {trade['status']}

### Raisonnement à l'entrée
{trade['decision_reasoning']}

### Indicateurs à l'entrée vs sortie
Entrée : RSI={indicators_at_entry['rsi_14']:.1f}, MACD hist={indicators_at_entry['macd_histogram']:.4f}
Sortie : RSI={indicators_at_exit['rsi_14']:.1f}, MACD hist={indicators_at_exit['macd_histogram']:.4f}

{memory}

Analyse ce trade. Réponds en JSON :
{{
  "outcome_analysis": "Explication de pourquoi le trade a gagné/perdu",
  "what_went_right": ["chose 1", ...],
  "what_went_wrong": ["chose 1", ...],
  "lesson": {{
    "category": "pattern|mistake|insight|rule",
    "content": "La leçon en une phrase actionnable",
    "confidence": 0.0 à 1.0
  }},
  "should_update_existing_memory": [
    {{"id": 12, "action": "reinforce|weaken", "reason": "..."}}
  ]
}}"""
```

---

### 3.6 Weekly Strategist (agents/ai_weekly_strategist.py)

**Rôle** : Méta-analyse hebdomadaire. Peut modifier les instructions des autres agents.
**Quand** : Une fois par semaine (dimanche minuit UTC)
**Modèle** : Sonnet (plus puissant, plus cher — mais une seule fois par semaine)

```python
WEEKLY_STRATEGIST_SYSTEM = """Tu es un stratège de trading senior.
Tu fais une revue hebdomadaire complète du bot de trading.

Tu as accès à :
- Toutes les métriques de la semaine
- La mémoire complète des leçons
- L'historique de tous les trades

Ton rôle :
1. Identifier les grands patterns de la semaine
2. Évaluer si la stratégie actuelle fonctionne
3. Proposer des ajustements concrets
4. Nettoyer la mémoire (supprimer les leçons obsolètes)
5. Suggérer des modifications aux seuils si nécessaire

Tu peux recommander de :
- Ajuster le seuil de signal (actuellement ±0.5)
- Modifier les pondérations du score composite
- Changer les multiplicateurs ATR pour SL/TP
- Exclure certaines heures de trading
- Favoriser une paire plutôt qu'une autre

Réponds UNIQUEMENT en JSON."""
```

**Réponse attendue** :
```json
{
  "week_summary": "Semaine difficile, 3 faux signaux sur BTC en période de faible volume...",
  "metrics_review": {
    "win_rate": 0.55,
    "profit_factor": 1.2,
    "assessment": "Légèrement profitable mais trop de trades inutiles"
  },
  "strategy_adjustments": [
    {
      "parameter": "signal_threshold",
      "current": 0.5,
      "recommended": 0.6,
      "reason": "Trop de faux signaux cette semaine"
    }
  ],
  "memory_cleanup": [
    {"id": 5, "action": "deactivate", "reason": "Contredite par 3 trades récents"},
    {"id": 8, "action": "reinforce", "reason": "Confirmée 4 fois cette semaine"}
  ],
  "next_week_focus": "Être plus sélectif, privilégier ETH qui a mieux performé"
}
```

---

## 4. Orchestrateur (main.py)

```python
async def main():
    """Séquence de démarrage :
    1. Charger la config
    2. Initialiser SQLite
    3. Créer le bus de messages (asyncio.Queue)
    4. Instancier tous les agents + ClaudeClient + MemoryManager
    5. Lancer DataCollector + SignalAnalyzer en tâches de fond
    6. Lancer le serveur FastAPI en parallèle
    7. Lancer le dispatcher
    """
    ...

async def dispatch(message: AgentMessage):
    """Route un message vers le bon handler.

    Flux principal :
    candle_closed
      → signal_analyzer.analyze()
        → si score > 0.5 ou < -0.5 :
            → ai_market_analyst.analyze()        # ~1s, ~$0.001
            → ai_decision.decide()               # ~1s, ~$0.001
            → si action ≠ WAIT :
                → ai_risk_evaluator.evaluate()   # ~1s, ~$0.001
                → si verdict ≠ REJECT :
                    → risk_guard.check()          # instant, 0€
                    → si approved :
                        → executor.execute()
    order_closed
      → ai_post_trade.analyze()                  # ~1s, ~$0.001
      → memory_manager.add_lesson()

    Coût par décision complète : ~$0.004 (4 appels Haiku)
    Si 20 signaux forts/jour : ~$0.08/jour ≈ 2.40$/mois
    """
    ...
```

---

## 5. API Dashboard (api/server.py)

### REST
```
GET  /api/portfolio          → état du portefeuille + coût API cumulé
GET  /api/trades             → historique avec raisonnement IA
GET  /api/trades/{id}        → détail + analysis + reasoning complets
GET  /api/signals            → derniers signaux
GET  /api/memory             → mémoire persistante (leçons apprises)
GET  /api/agents/status      → statut + dernier raisonnement de chaque agent
GET  /api/agents/costs       → consommation API par agent
POST /api/kill-switch        → arrêt d'urgence
POST /api/resume             → reprise
GET  /api/config             → config (sans secrets)
```

### WebSocket
```
WS /ws/live
- {"type": "price",     "data": {...}}
- {"type": "signal",    "data": {"pair": "BTCUSDT", "score": 0.72}}
- {"type": "thinking",  "data": {"agent": "decision", "status": "reasoning", "pair": "BTCUSDT"}}
- {"type": "decision",  "data": {"action": "BUY", "reasoning": "...", "confidence": 0.78}}
- {"type": "trade",     "data": {...}}
- {"type": "lesson",    "data": {"content": "...", "category": "pattern"}}
- {"type": "portfolio", "data": {...}}
```

Le message `thinking` est émis quand un agent IA commence à raisonner,
pour que le dashboard puisse afficher un indicateur "L'IA réfléchit...".

---

## 6. Plan de développement

### Phase 0 — Fondations
- [ ] config.py + .env.example
- [ ] database.py + schemas.py
- [ ] base.py (BaseAgent + AgentMessage)
- [ ] claude_client.py (wrapper Anthropic API)
- [ ] logger.py
- [ ] binance_client.py
- **Test** : connexion Binance testnet + appel Claude Haiku réussi

### Phase 1 — Données + Signaux
- [ ] data_collector.py (WebSocket)
- [ ] signal_analyzer.py (indicateurs + score)
- [ ] download_history.py (30 jours)
- **Test** : signaux détectés sur données live

### Phase 2 — Prompts + Mémoire
- [ ] Tous les fichiers dans prompts/
- [ ] memory/manager.py + memory_entries table
- [ ] Tester chaque prompt manuellement (envoyer des données fictives à Claude)
- **Test** : les réponses JSON sont valides et cohérentes

### Phase 3 — Agents IA
- [ ] ai_market_analyst.py
- [ ] ai_decision.py
- [ ] ai_risk_evaluator.py
- [ ] ai_post_trade.py
- **Test** : chaîne complète sur un signal simulé → décision + raisonnement

### Phase 4 — Sécurité + Exécution
- [ ] risk_guard.py (limites dures)
- [ ] executor.py (paper trading)
- [ ] test_risk_guard.py
- **Test** : le Risk Guard bloque un trade qui dépasse les limites

### Phase 5 — Orchestrateur + API
- [ ] main.py (dispatch)
- [ ] server.py + routes.py
- **Test** : flux complet de bout en bout

### Phase 6 — Dashboard
- [ ] PriceChart, TradeHistory, PortfolioStats
- [ ] AgentStatus, AgentReasoning (affiche les raisonnements IA)
- [ ] MemoryView (affiche les leçons apprises)
- **Test** : raisonnements visibles en temps réel

### Phase 7 — Paper Trading (5 jours minimum)
- [ ] Lancer en paper trading
- [ ] Observer les décisions et raisonnements
- [ ] ai_weekly_strategist.py (première analyse hebdo)
- **Go/No-Go** : les décisions IA sont-elles cohérentes ?

### Phase 8 — Live
- [ ] TRADING_MODE=live, BINANCE_TESTNET=False
- [ ] 100 USDT sur Binance
- [ ] Surveiller de près

---

## 7. Critères de succès

Succès si :
1. Les agents IA prennent des décisions argumentées et compréhensibles
2. La mémoire s'enrichit et les erreurs ne se répètent pas
3. Le dashboard montre le raisonnement de chaque décision
4. Le bot tourne 30 jours sans violer les règles de risque
5. On apprend quelque chose

Échec si :
1. Les décisions IA sont incohérentes ou incompréhensibles
2. La mémoire ne s'améliore pas
3. Les règles de risque sont violées
