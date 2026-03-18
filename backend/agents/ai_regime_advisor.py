"""Regime Advisor — SEUL module IA qui écrit dans config.json.

Appelé toutes les 1h OU en urgence si prix BTC change > 3% en 30min.
Ne modifie QUE : regime_override, regime_override_expires, position_size_multiplier.
Écrit UNIQUEMENT via ConfigManager (jamais d'écriture directe).

Modèle : Haiku (rapide, pas cher).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.agents.base import BaseAgent
from backend.config_manager import ConfigManager
from backend.storage.database import Database
from backend.utils.claude_client import ClaudeClient, ClaudeResponse
from backend.utils.logger import logger

REGIME_ADVISOR_SYSTEM = """Tu es un conseiller de régime de marché pour un bot de trading crypto spot.

TON RÔLE : décider si le régime détecté par Python (ADX/EMA) doit être surchargé
temporairement, et ajuster le multiplicateur de position.

Tu reçois :
- Le régime Python actuel (RANGING, TRENDING_UP, TRENDING_DOWN, HIGH_VOLATILITY)
- L'ADX et l'EMA slope actuels
- Le Fear & Greed Index
- Les funding rates Binance
- Les headlines crypto récentes
- Les positions ouvertes et le P&L du jour

Tu peux faire EXACTEMENT 3 choses :
1. Surcharger le régime (ex: Python dit RANGING mais tu vois un crash imminent → TRENDING_DOWN)
2. Ajuster le multiplicateur de position (0.25 à 1.5)
3. Ne rien changer (action: "HOLD")

CONTRAINTES :
- Le multiplicateur ne peut PAS dépasser 1.5
- Un override expire obligatoirement (max 4h)
- Tu ne modifies PAS les presets, les seuils RSI, les TP/SL — ça c'est le code Python
- En cas de doute, choisis "HOLD" — le Python fait déjà un bon travail

Réponds UNIQUEMENT en JSON."""

REGIME_ADVISOR_SCHEMA = {
    "action": "HOLD|OVERRIDE_REGIME|ADJUST_MULTIPLIER",
    "regime_override": "RANGING|TRENDING_UP|TRENDING_DOWN|HIGH_VOLATILITY|null",
    "override_duration_hours": "1 à 4 (null si HOLD)",
    "position_multiplier": "0.25 à 1.5",
    "reasoning": "1-2 phrases max",
    "confidence": "0 à 100",
}


class RegimeAdvisor(BaseAgent):
    """Conseiller IA de régime — écrit dans config.json via ConfigManager."""

    name = "regime_advisor"

    def __init__(
        self,
        claude: ClaudeClient,
        config_manager: ConfigManager,
        db: Database,
        model: str,
        bus: asyncio.Queue | None = None,
    ) -> None:
        super().__init__(bus=bus)
        self.claude = claude
        self.config_manager = config_manager
        self.db = db
        self.model = model

    async def advise(
        self,
        current_regime: str,
        regime_info: dict[str, Any],
        news_summary: str,
        portfolio: dict[str, Any],
        trigger_reason: str = "scheduled",
    ) -> dict[str, Any] | None:
        """Appelle Haiku pour obtenir un conseil sur le régime.

        trigger_reason : "scheduled" (1h) ou "emergency_price_move" (> 3% en 30min)
        """
        prompt = self._build_prompt(current_regime, regime_info, news_summary, portfolio, trigger_reason)

        try:
            response = await self.claude.ask_json(
                model=self.model,
                system=REGIME_ADVISOR_SYSTEM,
                prompt=prompt,
                schema=REGIME_ADVISOR_SCHEMA,
            )
        except Exception as e:
            logger.error("RegimeAdvisor erreur API: {}", e)
            return None

        await self._log(prompt, response, trigger_reason)

        if response.json_data is None:
            logger.error("RegimeAdvisor — JSON invalide")
            return None

        data = response.json_data
        await self._apply(data)

        logger.info(
            "RegimeAdvisor [{}] — {} (confiance {}, mult={}, override={})",
            trigger_reason,
            data.get("action", "?"),
            data.get("confidence", "?"),
            data.get("position_multiplier", "?"),
            data.get("regime_override", "null"),
        )
        return data

    async def _apply(self, data: dict[str, Any]) -> None:
        """Applique la décision du Regime Advisor via ConfigManager."""
        action = data.get("action", "HOLD")

        if action == "OVERRIDE_REGIME":
            override = data.get("regime_override")
            duration_h = data.get("override_duration_hours", 2)
            if override and duration_h:
                # Cap la durée à 4h max
                duration_h = min(float(duration_h), 4.0)
                from datetime import timedelta
                expires = (datetime.now(timezone.utc) + timedelta(hours=duration_h)).isoformat()
                reasoning = data.get("reasoning", "IA override")

                # Écriture via ConfigManager UNIQUEMENT
                self.config_manager.set_override(override, expires, reasoning)

        if action in ("ADJUST_MULTIPLIER", "OVERRIDE_REGIME"):
            mult = data.get("position_multiplier")
            if mult is not None:
                mult = max(0.25, min(float(mult), 1.5))  # Cap 0.25 à 1.5
                self.config_manager.config["global"]["position_size_multiplier"] = mult
                self.config_manager.config["_meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
                self.config_manager.config["_meta"]["updated_by"] = "ia_regime_advisor"
                ConfigManager.atomic_write(self.config_manager.path, self.config_manager.config)
                logger.info("RegimeAdvisor: multiplicateur ajusté → {:.2f}", mult)

    def _build_prompt(
        self,
        current_regime: str,
        regime_info: dict[str, Any],
        news_summary: str,
        portfolio: dict[str, Any],
        trigger_reason: str,
    ) -> str:
        return f"""## Conseil de régime — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
Trigger: {trigger_reason}

### Régime Python actuel
{current_regime}
Détails: {json.dumps(regime_info, indent=2)}

### Données macro/sentiment
{news_summary}

### Portefeuille
Capital: {portfolio.get('capital', 0):.2f} USDT
Positions ouvertes: {portfolio.get('open_positions', 0)}
P&L jour: {portfolio.get('daily_pnl', 0):+.2f} USDT ({portfolio.get('daily_pnl_pct', 0):.1%})
Drawdown: {portfolio.get('drawdown_pct', 0):.1%}

### Que faire ?
Réponds en JSON :
{{
  "action": "HOLD|OVERRIDE_REGIME|ADJUST_MULTIPLIER",
  "regime_override": null,
  "override_duration_hours": null,
  "position_multiplier": 1.0,
  "reasoning": "1-2 phrases",
  "confidence": 50
}}"""

    async def _log(self, prompt: str, response: ClaudeResponse, trigger: str) -> None:
        await self.db.execute(
            """INSERT INTO agent_logs (timestamp, agent, action, prompt_sent,
               response_received, tokens_used, cost_usd, duration_ms, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                self.name,
                "advise",
                prompt,
                response.content,
                response.tokens_in + response.tokens_out,
                response.cost_usd,
                response.duration_ms,
                json.dumps({"trigger": trigger}),
            ),
        )
