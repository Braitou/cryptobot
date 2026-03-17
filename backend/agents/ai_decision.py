"""Decision Agent — Décide buy/sell/wait via Claude Haiku."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.agents.base import BaseAgent
from backend.memory.manager import MemoryManager
from backend.prompts.decision import (
    DECISION_AGENT_LEARNING_ADDENDUM,
    DECISION_AGENT_SYSTEM,
    TRADE_DECISION_SCHEMA,
    MarketAnalysis,
    TradeDecision,
    build_decision_prompt,
)
from backend.storage.database import Database
from backend.utils.claude_client import ClaudeClient, ClaudeResponse
from backend.utils.logger import logger


class DecisionAgent(BaseAgent):
    """Décide d'acheter, vendre ou attendre, avec un raisonnement explicite."""

    name = "decision_agent"

    def __init__(
        self,
        claude: ClaudeClient,
        memory: MemoryManager,
        db: Database,
        model: str,
        bus: asyncio.Queue | None = None,
    ) -> None:
        super().__init__(bus=bus)
        self.claude = claude
        self.memory = memory
        self.db = db
        self.model = model

    async def decide(
        self,
        pair: str,
        signal_score: float,
        analysis: MarketAnalysis,
        indicators: dict[str, float],
        portfolio: dict[str, Any],
    ) -> TradeDecision | None:
        """Appelle Claude pour décider. Retourne None si erreur."""
        memory_ctx = await self.memory.get_context()
        recent_trades = await self.memory.get_recent_trades_summary()

        prompt = build_decision_prompt(
            pair=pair,
            signal_score=signal_score,
            analysis=analysis,
            indicators=indicators,
            memory=memory_ctx,
            recent_trades=recent_trades,
            portfolio=portfolio,
        )

        # Mode learning si < 30 trades clôturés
        trade_count = await self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM trades WHERE status != 'open'"
        )
        system = DECISION_AGENT_SYSTEM
        if (trade_count["cnt"] if trade_count else 0) < 30:
            system += DECISION_AGENT_LEARNING_ADDENDUM

        response = await self.claude.ask_json(
            model=self.model,
            system=system,
            prompt=prompt,
            schema=TRADE_DECISION_SCHEMA,
        )

        await self._log(pair, prompt, response, signal_score)

        if response.json_data is None:
            logger.error("DecisionAgent — JSON invalide pour {}", pair)
            return None

        data = response.json_data
        decision = TradeDecision(
            action=data.get("action", "WAIT"),
            confidence=float(data.get("confidence", 0)),
            reasoning=data.get("reasoning", ""),
            position_size_pct=float(data.get("position_size_pct", 0)),
            expected_holding_time=data.get("expected_holding_time", "1h"),
            key_factors=data.get("key_factors", []),
            risks_acknowledged=data.get("risks_acknowledged", []),
        )

        await self.publish("decision_made", {
            "pair": pair,
            "action": decision.action,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
        })

        logger.info(
            "DecisionAgent {} — {} (confiance {:.0%}) — {}",
            pair, decision.action, decision.confidence, decision.reasoning[:80],
        )
        return decision

    async def _log(
        self, pair: str, prompt: str, response: ClaudeResponse, signal_score: float
    ) -> None:
        await self.db.execute(
            """INSERT INTO agent_logs (timestamp, agent, action, prompt_sent,
               response_received, tokens_used, cost_usd, duration_ms, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                self.name,
                "decide",
                prompt,
                response.content,
                response.tokens_in + response.tokens_out,
                response.cost_usd,
                response.duration_ms,
                json.dumps({"pair": pair, "signal_score": signal_score}),
            ),
        )
