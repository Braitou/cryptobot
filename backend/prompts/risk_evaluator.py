"""Prompt template — Risk Evaluator Agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

RISK_EVALUATOR_LEARNING_ADDENDUM = """
PHASE D'APPRENTISSAGE : Le bot a moins de 30 trades. L'objectif principal est
d'accumuler de l'expérience, pas de maximiser le profit.

Règles spéciales :
- Tu ne REJECT que si les limites dures du Risk Guard sont en danger
  (drawdown > 10%, perte jour > 2%, position > 10%)
- Sinon, tu APPROVE ou REDUCE — laisse le bot expérimenter
- Réduire la position est mieux que refuser : le bot apprend quand même
- Chaque trade génère une leçon — même les pertes ont de la valeur

Après 30 trades, tu redeviendras strict."""

RISK_VERDICT_SCHEMA = {
    "verdict": "APPROVE|REDUCE|REJECT",
    "adjusted_position_pct": "0.0 à 0.10",
    "reasoning": "Explication en 2-4 phrases",
    "concerns": ["concern 1", "concern 2"],
    "referenced_memory": ["leçon pertinente 1"],
}


@dataclass
class RiskVerdict:
    verdict: str
    adjusted_position_pct: float
    reasoning: str
    concerns: list[str]
    referenced_memory: list[str]


def build_risk_evaluator_prompt(
    pair: str,
    decision: dict[str, Any],
    analysis: dict[str, Any],
    indicators: dict[str, float],
    portfolio: dict[str, Any],
    memory: str,
    recent_trades: str,
) -> str:
    return f"""## Évaluation du risque — {pair}

### Décision du Decision Agent
Action : {decision['action']}
Confiance : {decision['confidence']}
Raisonnement : {decision['reasoning']}
Taille position : {decision['position_size_pct'] * 100:.1f}% du capital
Holding prévu : {decision['expected_holding_time']}
Facteurs clés : {', '.join(decision['key_factors'])}
Risques reconnus : {', '.join(decision['risks_acknowledged'])}

### Contexte marché
Régime : {analysis.get('market_regime', 'N/A')} (force: {analysis.get('strength', 'N/A')})
Risques identifiés par l'analyste : {', '.join(analysis.get('risks', []))}

### Indicateurs clés
RSI: {indicators['rsi_14']:.1f} | ATR: {indicators['atr_14']:.2f}
Volume ratio: {indicators['volume_ratio']:.1f}x | Bollinger %B: {indicators['bb_pct']:.2f}

### Portefeuille
Capital: {portfolio['capital']:.2f} USDT | Positions ouvertes: {portfolio['open_positions']}
P&L aujourd'hui: {portfolio['daily_pnl']:.2f} USDT ({portfolio['daily_pnl_pct']:.1f}%)
Drawdown total: {portfolio['drawdown_pct']:.1f}%

{memory}

{recent_trades}

Challenge cette décision. Réponds en JSON :
{{
  "verdict": "APPROVE|REDUCE|REJECT",
  "adjusted_position_pct": {decision['position_size_pct']},
  "reasoning": "Ton évaluation en 2-4 phrases",
  "concerns": ["concern 1"],
  "referenced_memory": ["leçon pertinente 1"]
}}"""
