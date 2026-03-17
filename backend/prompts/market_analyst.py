"""Prompt template — Market Analyst Agent."""

from __future__ import annotations

import json
from typing import Any

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

MARKET_ANALYSIS_SCHEMA = {
    "market_regime": "trending_up|trending_down|ranging|volatile",
    "strength": "0.0 à 1.0",
    "key_observations": ["observation 1", "observation 2"],
    "risks": ["risque 1", "risque 2"],
    "relevant_memory": ["leçon pertinente 1"],
    "summary": "Résumé en 2-3 phrases",
}


def build_market_analyst_prompt(
    pair: str,
    indicators: dict[str, float],
    orderbook: dict[str, Any],
    memory: str,
    recent_trades: str,
) -> str:
    return f"""Analyse le marché {pair} avec ces données :

## Indicateurs techniques
{json.dumps(indicators, indent=2)}

## Order book
- Spread: {orderbook['bid_ask_spread']:.4f}%
- Imbalance (bid/total): {orderbook['imbalance_ratio']:.2f}

{memory}

{recent_trades}

Réponds en JSON :
{{
  "market_regime": "trending_up|trending_down|ranging|volatile",
  "strength": 0.0,
  "key_observations": ["observation 1", "observation 2"],
  "risks": ["risque 1", "risque 2"],
  "relevant_memory": ["leçon pertinente 1"],
  "summary": "Résumé en 2-3 phrases"
}}"""
