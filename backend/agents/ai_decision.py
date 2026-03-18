"""Decision Agent v2 — Décide buy/sell/wait via Claude Haiku (scalper agressif)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.agents.base import BaseAgent
from backend.prompts.decision import (
    DECISION_AGENT_SYSTEM,
    TRADE_DECISION_SCHEMA,
    TradeDecision,
    build_decision_prompt,
)
from backend.memory.manager import MemoryManager
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
        signal_classification: dict[str, Any],
        indicators: dict[str, float],
        portfolio: dict[str, Any],
    ) -> TradeDecision | None:
        """Appelle Claude pour décider. Retourne None si erreur."""
        memory_ctx = await self.memory.get_context()

        prompt = build_decision_prompt(
            pair=pair,
            signal_classification=signal_classification,
            indicators=indicators,
            memory=memory_ctx,
            portfolio=portfolio,
        )

        response = await self.claude.ask_json(
            model=self.model,
            system=DECISION_AGENT_SYSTEM,
            prompt=prompt,
            schema=TRADE_DECISION_SCHEMA,
        )

        await self._log(pair, prompt, response, signal_classification)

        if response.json_data is None:
            logger.error("DecisionAgent — JSON invalide pour {}", pair)
            return None

        data = response.json_data
        decision = TradeDecision(
            action=data.get("action", "WAIT"),
            confidence=float(data.get("confidence", 0)),
            reasoning=data.get("reasoning", ""),
            position_size_pct=float(data.get("position_size_pct", 0)) / 100,
            stop_loss_pct=float(data.get("stop_loss_pct", 0.3)),
            take_profit_pct=float(data.get("take_profit_pct", 0.5)),
            max_hold_minutes=int(data.get("max_hold_minutes", 30)),
        )

        await self.publish("decision_made", {
            "pair": pair,
            "action": decision.action,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
        })

        logger.info(
            "DecisionAgent {} — {} (confiance {:.0f}%) — {}",
            pair, decision.action, decision.confidence, decision.reasoning[:80],
        )
        return decision

    async def _log(
        self, pair: str, prompt: str, response: ClaudeResponse,
        signal_classification: dict[str, Any],
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
                json.dumps({"pair": pair, "signal": signal_classification}),
            ),
        )
