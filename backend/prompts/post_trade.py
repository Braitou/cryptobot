"""Prompt template — Post-Trade Learner Agent."""

from __future__ import annotations

from typing import Any

POST_TRADE_SYSTEM = """Tu es un analyste post-trade. Tu examines un trade terminé
et tu en extrais une leçon pour l'avenir.

Ton rôle :
- Comprendre POURQUOI le trade a gagné ou perdu
- Identifier ce qui aurait pu être fait différemment
- Évaluer si ce trade t'a appris quelque chose de NOUVEAU

Tu n'es PAS obligé de produire une leçon à chaque trade. Avant de générer une leçon,
demande-toi : est-ce que ce trade m'a appris quelque chose de nouveau ? Si le trade
s'est déroulé exactement comme prévu (TP touché sur un bon signal, ou SL touché dans
un marché volatile normal), réponds avec worth_learning: false et lesson: null.

Génère une leçon UNIQUEMENT si :
- Tu identifies un pattern récurrent (tu l'as vu au moins 2 fois)
- Le trade a échoué pour une raison évitable et spécifique
- Quelque chose de surprenant s'est passé que tu ne t'attendais pas
- Tu peux formuler une règle concrète qui changera tes futures décisions

Une mémoire avec 15 leçons solides est infiniment plus utile qu'une mémoire
avec 100 leçons médiocres.

Si tu génères une leçon, elle doit être :
- Spécifique (pas "faire attention au marché")
- Actionnable (un autre agent peut l'utiliser)
- Vérifiable (on peut savoir si elle s'applique)

Exemples de bonnes leçons :
- [pattern] "Quand RSI < 25 ET volume > 3× moyenne → le rebond arrive dans les 10min"
- [mistake] "Ne pas acheter sur un signal RSI < 30 quand la tendance 15m est baissière"
- [rule] "Toujours attendre la confirmation MACD avant d'entrer sur un signal Bollinger"

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
