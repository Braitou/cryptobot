"""Market Analyst Agent — Analyse le contexte du marché via Claude Haiku."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.agents.base import BaseAgent
from backend.memory.manager import MemoryManager
from backend.prompts.decision import MarketAnalysis
from backend.prompts.market_analyst import (
    MARKET_ANALYSIS_SCHEMA,
    MARKET_ANALYST_SYSTEM,
    build_market_analyst_prompt,
)
from backend.storage.database import Database
from backend.utils.claude_client import ClaudeClient, ClaudeResponse
from backend.utils.logger import logger


class MarketAnalystAgent(BaseAgent):
    """Analyse le contexte global du marché avant toute décision.

    Ne prend aucune décision de trading — fournit un contexte structuré
    au Decision Agent.
    """

    name = "market_analyst"

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

    async def analyze(
        self, pair: str, indicators: dict[str, float], orderbook: dict[str, Any]
    ) -> MarketAnalysis | None:
        """Appelle Claude pour analyser le marché. Retourne None si erreur."""
        memory_ctx = await self.memory.get_context()
        recent_trades = await self.memory.get_recent_trades_summary()

        prompt = build_market_analyst_prompt(
            pair=pair,
            indicators=indicators,
            orderbook=orderbook,
            memory=memory_ctx,
            recent_trades=recent_trades,
        )

        response = await self.claude.ask_json(
            model=self.model,
            system=MARKET_ANALYST_SYSTEM,
            prompt=prompt,
            schema=MARKET_ANALYSIS_SCHEMA,
        )

        await self._log(pair, prompt, response)

        if response.json_data is None:
            logger.error("MarketAnalyst — JSON invalide pour {}", pair)
            return None

        data = response.json_data
        analysis = MarketAnalysis(
            market_regime=data.get("market_regime", "ranging"),
            strength=float(data.get("strength", 0.5)),
            key_observations=data.get("key_observations", []),
            risks=data.get("risks", []),
            relevant_memory=data.get("relevant_memory", []),
            summary=data.get("summary", ""),
        )

        await self.publish("analysis_complete", {
            "pair": pair,
            "market_regime": analysis.market_regime,
            "strength": analysis.strength,
            "summary": analysis.summary,
        })

        logger.info(
            "MarketAnalyst {} — {} (force {}) — {}",
            pair, analysis.market_regime, analysis.strength, analysis.summary[:80],
        )
        return analysis

    async def _log(self, pair: str, prompt: str, response: ClaudeResponse) -> None:
        await self.db.execute(
            """INSERT INTO agent_logs (timestamp, agent, action, prompt_sent,
               response_received, tokens_used, cost_usd, duration_ms, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                self.name,
                "analyze",
                prompt,
                response.content,
                response.tokens_in + response.tokens_out,
                response.cost_usd,
                response.duration_ms,
                json.dumps({"pair": pair}),
            ),
        )
