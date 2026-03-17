"""Prompt template — Decision Agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DECISION_AGENT_SYSTEM = """Tu es un trader crypto expérimenté qui gère un portefeuille de 500 USDT.
Ton approche est du scalping (trades de quelques minutes à quelques heures).

Ton rôle est de décider : BUY, SELL, ou WAIT.

Principes :
- Tu apprends de tes erreurs passées (mémoire fournie).
- Tu prends en compte le contexte global fourni par le Market Analyst.
- Tu ne risques JAMAIS plus de 10% du capital sur un seul trade.
- Tu donnes TOUJOURS un raisonnement clair pour ta décision.

IMPORTANT : Si la mémoire mentionne une erreur similaire à la situation actuelle,
tu dois en tenir compte explicitement dans ton raisonnement.

Réponds UNIQUEMENT en JSON."""

DECISION_AGENT_LEARNING_ADDENDUM = """
PHASE D'APPRENTISSAGE : Tu as moins de 30 trades en mémoire. Dans cette phase,
tu DOIS trader pour apprendre. Les erreurs sont acceptables et même nécessaires —
chaque trade perdu génère une leçon qui te rend meilleur.

Règles spéciales en phase d'apprentissage :
- Accepte les trades dès que ta confiance dépasse 50% (au lieu de 70%)
- Ne cite pas l'absence de données comme raison de WAIT
- Vise 3-5 trades par jour minimum
- Préfère un trade risqué qui t'apprend quelque chose à un WAIT qui ne t'apprend rien

Cette phase se désactive automatiquement après 30 trades — tu redeviendras
conservateur avec une vraie base d'expérience."""

TRADE_DECISION_SCHEMA = {
    "action": "BUY|SELL|WAIT",
    "confidence": "0.0 à 1.0",
    "reasoning": "Explication détaillée en 3-5 phrases",
    "position_size_pct": "0.05 à 0.10 (0 si WAIT)",
    "expected_holding_time": "5min|15min|1h|4h",
    "key_factors": ["facteur 1", "facteur 2"],
    "risks_acknowledged": ["risque 1"],
}


@dataclass
class MarketAnalysis:
    market_regime: str
    strength: float
    key_observations: list[str]
    risks: list[str]
    relevant_memory: list[str]
    summary: str


@dataclass
class TradeDecision:
    action: str
    confidence: float
    reasoning: str
    position_size_pct: float
    expected_holding_time: str
    key_factors: list[str]
    risks_acknowledged: list[str]
    quantity: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


def build_decision_prompt(
    pair: str,
    signal_score: float,
    analysis: MarketAnalysis,
    indicators: dict[str, float],
    memory: str,
    recent_trades: str,
    portfolio: dict[str, Any],
) -> str:
    signal_label = "achat fort" if signal_score > 0.5 else "vente forte"

    return f"""## Décision de trade — {pair}

### Signal technique
Score composite : {signal_score:.4f} ({signal_label})

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
  "confidence": 0.0,
  "reasoning": "Explication détaillée de ta décision en 3-5 phrases",
  "position_size_pct": 0.0,
  "expected_holding_time": "5min|15min|1h|4h",
  "key_factors": ["facteur 1", "facteur 2"],
  "risks_acknowledged": ["risque 1"]
}}"""
