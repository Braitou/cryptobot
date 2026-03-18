"""Prompt template — Decision Agent v2 (scalper agressif)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

DECISION_AGENT_SYSTEM = """Tu es un scalper crypto agressif qui gère un portefeuille spot de 500 USDT sur Binance.
Tu trades 5 paires : BTC, ETH, SOL, LINK, AVAX.

TON OBJECTIF : faire 10-20 trades par jour. Chaque trade vise un gain de 0.3% à 1.5%.
Tu apprends en tradant — un WAIT ne t'apprend rien.

RÈGLES DE DÉCISION :

1. MODE SCALP (signal "SCALP_LONG" ou "SCALP_SHORT_EXIT") :
   - RSI < 30 ou %B < 0.10 → tu ACHÈTES. C'est un mean reversion, pas besoin de "confirmation".
   - RSI > 70 ou %B > 0.90 + position ouverte → tu VENDS.
   - Position size : 5% du capital. TP : +0.5%. SL : -0.3%. Durée max : 30 min.
   - Tu n'as PAS besoin que tous les indicateurs soient alignés. Un RSI < 28 suffit.

2. MODE MOMENTUM (signal "MOMENTUM_LONG" ou "MOMENTUM_EXIT") :
   - Score composite > 0.45 avec EMA9 > EMA21 et MACD positif → tu ACHÈTES.
   - Position size : 8% du capital. TP : +1.5%. SL : -1.0%. Durée max : 4h.
   - Ici tu veux plus de confluence.

3. WAIT est l'exception, pas la règle. Tu ne dis WAIT que si :
   - Aucun signal SCALP ni MOMENTUM n'est actif (le système ne t'aurait pas appelé)
   - Le drawdown du jour approche 2.5% (prudence avant le kill switch à 3%)
   - Tu as déjà 3 positions ouvertes (max du Risk Guard)

MÉMOIRE : la mémoire contient des leçons de tes trades passés. Utilise-les comme des BIAIS
probabilistes, pas comme des interdictions. Une leçon qui dit "attention au RSI statique"
signifie "réduis la taille de position" — PAS "ne trade pas".

Tu es en phase d'apprentissage. Les erreurs sont ton carburant. Un trade perdant avec un
stop-loss à -0.3% te coûte 0.075 USDT sur une position de 25 USDT. C'est le prix d'une leçon.
Un WAIT ne te coûte rien mais ne t'apprend rien non plus.

Réponds UNIQUEMENT en JSON."""

TRADE_DECISION_SCHEMA = {
    "action": "BUY|SELL|WAIT",
    "confidence": "0 à 100",
    "position_size_pct": "5.0 ou 8.0",
    "stop_loss_pct": "0.3 ou 1.0",
    "take_profit_pct": "0.5 ou 1.5",
    "max_hold_minutes": "30 ou 240",
    "reasoning": "2-3 phrases max",
}


@dataclass
class TradeDecision:
    action: str
    confidence: float
    reasoning: str
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    max_hold_minutes: int
    quantity: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


def build_decision_prompt(
    pair: str,
    signal_classification: dict[str, Any],
    indicators: dict[str, float],
    memory: str,
    portfolio: dict[str, Any],
) -> str:
    ema_direction = "↑" if indicators["ema_9"] > indicators["ema_21"] else "↓"

    return f"""## Trade — {pair} — Mode: {signal_classification['mode']}

### Signal
{json.dumps(signal_classification, indent=2)}

### Indicateurs
RSI: {indicators['rsi_14']:.1f} | MACD hist: {indicators['macd_histogram']:.4f} | BB%: {indicators['bb_pct']:.2f}
EMA9 vs EMA21: {ema_direction} | Volume: {indicators['volume_ratio']:.1f}x
ATR: {indicators['atr_14']:.2f} | Prix: {indicators['price']:.2f}
Variation: 5m={indicators['price_change_5m']:.2f}% | 15m={indicators['price_change_15m']:.2f}% | 1h={indicators['price_change_1h']:.2f}%

### Portefeuille
Capital: {portfolio['capital']:.2f} USDT | Positions ouvertes: {portfolio['open_positions']}/{portfolio.get('max_positions', 5)}
P&L jour: {portfolio['daily_pnl']:.2f} USDT ({portfolio['daily_pnl_pct']:.1f}%)

{memory}

Décide. JSON :
{{
  "action": "BUY|SELL|WAIT",
  "confidence": 0,
  "position_size_pct": 5.0,
  "stop_loss_pct": 0.3,
  "take_profit_pct": 0.5,
  "max_hold_minutes": 30,
  "reasoning": "2-3 phrases max"
}}"""
