"""Post-Trade Learner Agent — Analyse chaque trade fermé et écrit dans la mémoire."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.agents.base import BaseAgent
from backend.memory.manager import MemoryManager
from backend.prompts.post_trade import (
    POST_TRADE_SCHEMA,
    POST_TRADE_SYSTEM,
    build_post_trade_prompt,
)
from backend.storage.database import Database
from backend.utils.claude_client import ClaudeClient, ClaudeResponse
from backend.utils.logger import logger


class PostTradeAgent(BaseAgent):
    """Analyse chaque trade fermé, extrait une leçon, met à jour la mémoire."""

    name = "post_trade_learner"

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
        self,
        trade: dict[str, Any],
        indicators_at_entry: dict[str, float],
        indicators_at_exit: dict[str, float],
    ) -> dict[str, Any] | None:
        """Analyse un trade fermé et met à jour la mémoire.

        Retourne le dict de la réponse Claude ou None si erreur.
        """
        memory_ctx = await self.memory.get_context()

        prompt = build_post_trade_prompt(
            trade=trade,
            indicators_at_entry=indicators_at_entry,
            indicators_at_exit=indicators_at_exit,
            memory=memory_ctx,
        )

        response = await self.claude.ask_json(
            model=self.model,
            system=POST_TRADE_SYSTEM,
            prompt=prompt,
            schema=POST_TRADE_SCHEMA,
        )

        await self._log(trade, prompt, response)

        if response.json_data is None:
            logger.error("PostTrade — JSON invalide pour trade #{}", trade.get("id"))
            return None

        data = response.json_data

        # Sauvegarder l'analyse dans le trade
        if trade.get("id"):
            await self.db.execute(
                "UPDATE trades SET post_trade_analysis = ? WHERE id = ?",
                (data.get("outcome_analysis", ""), trade["id"]),
            )

        # Extraire et sauvegarder la leçon — seulement si worth_learning
        worth = data.get("worth_learning", True)
        lesson = data.get("lesson") or {}
        if worth and lesson and lesson.get("content"):
            await self.memory.add_lesson(
                trade_id=trade.get("id"),
                category=lesson.get("category", "insight"),
                content=lesson["content"],
                confidence=float(lesson.get("confidence", 0.5)),
            )
            if trade.get("id"):
                await self.db.execute(
                    "UPDATE trades SET lesson_learned = ? WHERE id = ?",
                    (lesson["content"], trade["id"]),
                )
        elif not worth:
            logger.info("PostTrade trade #{} — pas de leçon (trade prévisible)", trade.get("id", "?"))

        # Traiter les mises à jour de mémoire existante
        for update in data.get("should_update_existing_memory", []):
            entry_id = update.get("id")
            action = update.get("action")
            if not entry_id or entry_id == 0:
                continue
            if action == "reinforce":
                await self.memory.reinforce(entry_id)
                logger.info("PostTrade — mémoire #{} renforcée", entry_id)
            elif action == "weaken":
                await self.memory.weaken(entry_id)
                logger.info("PostTrade — mémoire #{} affaiblie", entry_id)

        await self.publish("lesson_learned", {
            "trade_id": trade.get("id"),
            "lesson": lesson,
            "outcome_analysis": data.get("outcome_analysis", ""),
        })

        logger.info(
            "PostTrade trade #{} — [{}] {}",
            trade.get("id", "?"),
            lesson.get("category", "?"),
            lesson.get("content", "?")[:80],
        )
        return data

    async def _log(
        self, trade: dict[str, Any], prompt: str, response: ClaudeResponse
    ) -> None:
        await self.db.execute(
            """INSERT INTO agent_logs (timestamp, agent, action, prompt_sent,
               response_received, tokens_used, cost_usd, duration_ms, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                self.name,
                "learn",
                prompt,
                response.content,
                response.tokens_in + response.tokens_out,
                response.cost_usd,
                response.duration_ms,
                json.dumps({"trade_id": trade.get("id")}),
            ),
        )
