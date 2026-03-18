"""Prompt template — Post-Trade Learner Agent."""

from __future__ import annotations

from typing import Any

POST_TRADE_SYSTEM = """Tu es un analyste post-trade. Tu examines un trade terminé et tu cherches
des PATTERNS ACTIONNABLES.

RÈGLES CRITIQUES :
1. Tu ne génères JAMAIS de leçon qui dit "ne pas trader" ou "attendre plus de confirmation".
   Le bot DOIT trader pour apprendre. Les leçons doivent améliorer le COMMENT, pas empêcher le QUAND.

2. Bonnes leçons (améliorer l'exécution) :
   - "Sur LINK, le RSI rebondit plus vite quand le volume est > 2× → augmenter la taille"
   - "Les scalps après 2h du matin UTC ont un win rate plus bas → réduire la taille de 50%"
   - "Le TP de 0.5% est atteint dans 70% des cas en < 10min → garder ce target"

3. Mauvaises leçons (empêchent de trader) :
   - "Ne pas entrer sans confirmation dynamique" ← INTERDIT
   - "Attendre que tous les indicateurs soient alignés" ← INTERDIT
   - "Éviter les marchés en range" ← INTERDIT (le range EST notre setup de scalp)

4. Tu ne génères une leçon que si tu vois un pattern sur AU MOINS 2 trades similaires.
   Un seul trade perdant n'est pas un pattern, c'est de la variance.

5. Max 10 leçons actives. Si tu en ajoutes une 11ème, tu dois en désactiver une ancienne.

Réponds UNIQUEMENT en JSON."""

POST_TRADE_SCHEMA = {
    "outcome_analysis": "Explication de pourquoi le trade a gagné/perdu",
    "what_went_right": ["chose 1"],
    "what_went_wrong": ["chose 1"],
    "worth_learning": "true si ce trade a appris quelque chose de nouveau, false sinon",
    "lesson": {
        "category": "pattern|mistake|insight|rule",
        "content": "La leçon en une phrase actionnable",
        "confidence": "0.0 à 1.0",
    },
    "should_update_existing_memory": [
        {"id": 0, "action": "reinforce|weaken", "reason": "..."}
    ],
}


def build_post_trade_prompt(
    trade: dict[str, Any],
    indicators_at_entry: dict[str, float],
    indicators_at_exit: dict[str, float],
    memory: str,
) -> str:
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
  "what_went_right": ["chose 1"],
  "what_went_wrong": ["chose 1"],
  "worth_learning": true,
  "lesson": {{
    "category": "pattern|mistake|insight|rule",
    "content": "La leçon en une phrase actionnable",
    "confidence": 0.5
  }},
  "should_update_existing_memory": [
    {{"id": 0, "action": "reinforce|weaken", "reason": "..."}}
  ]
}}

Si worth_learning est false, mets lesson à null :
{{
  "outcome_analysis": "...",
  "what_went_right": [...],
  "what_went_wrong": [...],
  "worth_learning": false,
  "lesson": null,
  "should_update_existing_memory": [...]
}}"""
