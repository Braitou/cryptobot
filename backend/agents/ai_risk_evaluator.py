"""Risk Evaluator Agent — Challenge les décisions via Claude Haiku."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from backend.agents.base import BaseAgent
from backend.memory.manager import MemoryManager
from backend.prompts.decision import MarketAnalysis, TradeDecision
from backend.prompts.risk_evaluator import (
    RISK_EVALUATOR_LEARNING_ADDENDUM,
    RISK_EVALUATOR_SYSTEM,
    RISK_VERDICT_SCHEMA,
    RiskVerdict,
    build_risk_evaluator_prompt,
)
from backend.storage.database import Database
from backend.utils.claude_client import ClaudeClient, ClaudeResponse
from backend.utils.logger import logger


class RiskEvaluatorAgent(BaseAgent):
    """Challenge la décision du Decision Agent. Peut réduire ou refuser."""

    name = "risk_evaluator"

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

    async def evaluate(
        self,
        pair: str,
        decision: TradeDecision,
        analysis: MarketAnalysis,
        indicators: dict[str, float],
        portfolio: dict[str, Any],
    ) -> RiskVerdict | None:
        """Appelle Claude pour évaluer le risque. Retourne None si erreur."""
        memory_ctx = await self.memory.get_context()
        recent_trades = await self.memory.get_recent_trades_summary()

        decision_dict = {
            "action": decision.action,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
            "position_size_pct": decision.position_size_pct,
            "expected_holding_time": decision.expected_holding_time,
            "key_factors": decision.key_factors,
            "risks_acknowledged": decision.risks_acknowledged,
        }
        analysis_dict = asdict(analysis)

        prompt = build_risk_evaluator_prompt(
            pair=pair,
            decision=decision_dict,
            analysis=analysis_dict,
            indicators=indicators,
            portfolio=portfolio,
            memory=memory_ctx,
            recent_trades=recent_trades,
        )

        # Mode learning si < 30 trades clôturés
        trade_count = await self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM trades WHERE status != 'open'"
        )
        system = RISK_EVALUATOR_SYSTEM
        if (trade_count["cnt"] if trade_count else 0) < 30:
            system += RISK_EVALUATOR_LEARNING_ADDENDUM

        response = await self.claude.ask_json(
            model=self.model,
            system=system,
            prompt=prompt,
            schema=RISK_VERDICT_SCHEMA,
        )

        await self._log(pair, prompt, response)

        if response.json_data is None:
            logger.error("RiskEvaluator — JSON invalide pour {}", pair)
            return None

        data = response.json_data
        verdict = RiskVerdict(
            verdict=data.get("verdict", "REJECT"),
            adjusted_position_pct=float(data.get("adjusted_position_pct", 0)),
            reasoning=data.get("reasoning", ""),
            concerns=data.get("concerns", []),
            referenced_memory=data.get("referenced_memory", []),
        )

        await self.publish("risk_evaluated", {
            "pair": pair,
            "verdict": verdict.verdict,
            "adjusted_position_pct": verdict.adjusted_position_pct,
            "reasoning": verdict.reasoning,
        })

        logger.info(
            "RiskEvaluator {} — {} (pos {:.1%}) — {}",
            pair, verdict.verdict, verdict.adjusted_position_pct, verdict.reasoning[:80],
        )
        return verdict

    async def _log(self, pair: str, prompt: str, response: ClaudeResponse) -> None:
        await self.db.execute(
            """INSERT INTO agent_logs (timestamp, agent, action, prompt_sent,
               response_received, tokens_used, cost_usd, duration_ms, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                self.name,
                "evaluate",
                prompt,
                response.content,
                response.tokens_in + response.tokens_out,
                response.cost_usd,
                response.duration_ms,
                json.dumps({"pair": pair}),
            ),
        )
