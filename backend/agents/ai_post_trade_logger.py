"""Post-Trade Logger v4 — Tags numériques + scores, pas de narrative.

Remplace le Post-Trade Learner narratif (qui écrivait des leçons textuelles dans memory.md).
Écrit des CHIFFRES et des TAGS dans la table SQLite trade_tags.

Modèle : Haiku (rapide, pas cher).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.agents.base import BaseAgent
from backend.storage.database import Database
from backend.utils.claude_client import ClaudeClient, ClaudeResponse
from backend.utils.logger import logger

POST_TRADE_LOGGER_SYSTEM = """Tu es un analyseur de trades. Tu reçois un trade fermé et tu le TAGS.

Tu ne génères PAS de leçon textuelle. Tu produis des DONNÉES STRUCTURÉES :

1. tags : liste de tags courts décrivant le trade. Exemples :
   - "rsi_extreme", "high_volume", "low_volume", "night_trade", "news_driven"
   - "mean_reversion", "trend_follow", "breakout", "fake_breakout"
   - "fast_exit", "timeout_exit", "sl_hit", "tp_hit", "trailing_exit"
   - "scalp", "momentum", "btc", "eth", "sol", "link", "avax"
   - "ranging_regime", "trending_regime", "high_vol_regime"

2. entry_quality (0 à 1) : le timing d'entrée était-il bon ?
   - 1.0 = entrée parfaite (prix au plus bas avant rebond)
   - 0.5 = entrée correcte
   - 0.0 = entrée au pire moment

3. exit_quality (0 à 1) : la sortie était-elle optimale ?
   - 1.0 = sortie au meilleur moment
   - 0.5 = sortie correcte (SL/TP standard)
   - 0.0 = sortie trop tôt ou trop tard

4. notable_fact : UNE phrase max ou null. Uniquement si quelque chose de surprenant s'est passé.

Réponds UNIQUEMENT en JSON."""

POST_TRADE_LOGGER_SCHEMA = {
    "tags": ["tag1", "tag2"],
    "entry_quality": 0.5,
    "exit_quality": 0.5,
    "notable_fact": "null ou 1 phrase",
}


class PostTradeLogger(BaseAgent):
    """Analyse un trade fermé et écrit des tags numériques dans trade_tags."""

    name = "post_trade_logger"

    def __init__(
        self,
        claude: ClaudeClient,
        db: Database,
        model: str,
        bus: asyncio.Queue | None = None,
    ) -> None:
        super().__init__(bus=bus)
        self.claude = claude
        self.db = db
        self.model = model

    async def analyze(
        self,
        trade: dict[str, Any],
        indicators_at_entry: dict[str, float],
        indicators_at_exit: dict[str, float],
        regime: str,
    ) -> dict[str, Any] | None:
        """Analyse un trade fermé, génère des tags et les stocke dans trade_tags."""
        prompt = self._build_prompt(trade, indicators_at_entry, indicators_at_exit, regime)

        try:
            response = await self.claude.ask_json(
                model=self.model,
                system=POST_TRADE_LOGGER_SYSTEM,
                prompt=prompt,
                schema=POST_TRADE_LOGGER_SCHEMA,
            )
        except Exception as e:
            logger.error("PostTradeLogger erreur API: {}", e)
            return None

        await self._log_api_call(trade, prompt, response)

        if response.json_data is None:
            logger.error("PostTradeLogger — JSON invalide pour trade #{}", trade.get("id"))
            return None

        data = response.json_data

        # Stocker dans trade_tags
        tags = data.get("tags", [])
        entry_q = data.get("entry_quality")
        exit_q = data.get("exit_quality")
        notable = data.get("notable_fact")
        if notable == "null" or notable == "":
            notable = None

        trade_id = trade.get("id")
        if trade_id:
            await self.db.execute(
                """INSERT INTO trade_tags (trade_id, timestamp, tags, entry_quality,
                   exit_quality, regime_at_entry, notable_fact)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_id,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(tags),
                    entry_q,
                    exit_q,
                    regime,
                    notable,
                ),
            )

        await self.publish("trade_tagged", {
            "trade_id": trade_id,
            "tags": tags,
            "entry_quality": entry_q,
            "exit_quality": exit_q,
        })

        logger.info(
            "PostTradeLogger #{} — tags={} entry_q={:.1f} exit_q={:.1f}{}",
            trade_id,
            tags,
            entry_q or 0,
            exit_q or 0,
            f" — {notable}" if notable else "",
        )
        return data

    def _build_prompt(
        self,
        trade: dict[str, Any],
        indicators_at_entry: dict[str, float],
        indicators_at_exit: dict[str, float],
        regime: str,
    ) -> str:
        pnl_pct = trade.get("pnl_pct", 0) or 0
        pnl = trade.get("pnl", 0) or 0
        duration = trade.get("duration_minutes", 0)

        return f"""## Trade #{trade.get('id', '?')}

Paire: {trade.get('pair', '?')} | Side: {trade.get('side', '?')}
Entrée: {trade.get('entry_price', 0)} à {trade.get('entry_time', '?')}
Sortie: {trade.get('exit_price', 0)} à {trade.get('exit_time', '?')}
Résultat: {pnl_pct:+.2f}% ({pnl:+.2f} USDT)
Durée: {duration}min
Sortie par: {trade.get('status', '?')}
Régime: {regime}
Mode: {trade.get('market_analysis', '?')}

### Raisonnement à l'entrée
{trade.get('decision_reasoning', 'N/A')}

### Indicateurs entrée
RSI9={indicators_at_entry.get('rsi_9', 0):.1f} RSI14={indicators_at_entry.get('rsi_14', 0):.1f}
MACD={indicators_at_entry.get('macd_histogram', 0):.4f} BB%={indicators_at_entry.get('bb_pct', 0):.2f}
Volume={indicators_at_entry.get('volume_ratio', 0):.1f}x ATR={indicators_at_entry.get('atr_14', 0):.2f}

### Indicateurs sortie
RSI9={indicators_at_exit.get('rsi_9', 0):.1f} RSI14={indicators_at_exit.get('rsi_14', 0):.1f}
MACD={indicators_at_exit.get('macd_histogram', 0):.4f} BB%={indicators_at_exit.get('bb_pct', 0):.2f}

Réponds en JSON :
{{
  "tags": ["tag1", "tag2"],
  "entry_quality": 0.5,
  "exit_quality": 0.5,
  "notable_fact": null
}}"""

    async def _log_api_call(
        self, trade: dict[str, Any], prompt: str, response: ClaudeResponse
    ) -> None:
        await self.db.execute(
            """INSERT INTO agent_logs (timestamp, agent, action, prompt_sent,
               response_received, tokens_used, cost_usd, duration_ms, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                self.name,
                "tag_trade",
                prompt,
                response.content,
                response.tokens_in + response.tokens_out,
                response.cost_usd,
                response.duration_ms,
                json.dumps({"trade_id": trade.get("id")}),
            ),
        )
