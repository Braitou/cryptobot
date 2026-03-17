"""Prompt template — Weekly Strategist Agent."""

from __future__ import annotations

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

WEEKLY_STRATEGY_SCHEMA = {
    "week_summary": "Résumé de la semaine en 2-3 phrases",
    "metrics_review": {
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_pnl": 0.0,
        "total_trades": 0,
        "assessment": "Évaluation en 1-2 phrases",
    },
    "strategy_adjustments": [
        {
            "parameter": "nom du paramètre",
            "current": 0.0,
            "recommended": 0.0,
            "reason": "Explication",
        }
    ],
    "memory_cleanup": [
        {"id": 0, "action": "deactivate|reinforce", "reason": "..."}
    ],
    "next_week_focus": "Priorité pour la semaine prochaine",
}


def build_weekly_strategist_prompt(
    weekly_metrics: dict,
    all_trades_week: str,
    memory: str,
    current_config: dict,
) -> str:
    return f"""## Revue hebdomadaire du bot de trading

### Métriques de la semaine
Nombre de trades : {weekly_metrics.get('total_trades', 0)}
Trades gagnants : {weekly_metrics.get('wins', 0)}
Trades perdants : {weekly_metrics.get('losses', 0)}
Win rate : {weekly_metrics.get('win_rate', 0):.1%}
P&L total : {weekly_metrics.get('total_pnl', 0):+.2f} USDT ({weekly_metrics.get('total_pnl_pct', 0):+.1f}%)
Profit factor : {weekly_metrics.get('profit_factor', 0):.2f}
Coût API semaine : ${weekly_metrics.get('api_cost', 0):.2f}
Drawdown max semaine : {weekly_metrics.get('max_drawdown_pct', 0):.1f}%

### Configuration actuelle
Seuil de signal : ±{current_config.get('signal_threshold', 0.5)}
SL ATR mult : {current_config.get('stop_loss_atr_mult', 1.5)}
TP ATR mult : {current_config.get('take_profit_atr_mult', 2.0)}
Max position : {current_config.get('max_position_pct', 0.05) * 100:.0f}%

### Tous les trades de la semaine
{all_trades_week}

{memory}

Fais ta revue hebdomadaire. Réponds en JSON :
{{
  "week_summary": "Résumé en 2-3 phrases",
  "metrics_review": {{
    "win_rate": 0.0,
    "profit_factor": 0.0,
    "total_pnl": 0.0,
    "total_trades": 0,
    "assessment": "Évaluation en 1-2 phrases"
  }},
  "strategy_adjustments": [
    {{
      "parameter": "nom du paramètre",
      "current": 0.0,
      "recommended": 0.0,
      "reason": "Explication"
    }}
  ],
  "memory_cleanup": [
    {{"id": 0, "action": "deactivate|reinforce", "reason": "..."}}
  ],
  "next_week_focus": "Priorité pour la semaine prochaine"
}}"""
