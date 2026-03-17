"""Test Phase 2 — Prompts + Mémoire.

Envoie des données fictives à chaque prompt via Claude Haiku
et vérifie que les réponses JSON sont valides et cohérentes.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.memory.manager import MemoryManager
from backend.prompts.decision import (
    DECISION_AGENT_SYSTEM,
    TRADE_DECISION_SCHEMA,
    MarketAnalysis,
    build_decision_prompt,
)
from backend.prompts.market_analyst import (
    MARKET_ANALYST_SYSTEM,
    MARKET_ANALYSIS_SCHEMA,
    build_market_analyst_prompt,
)
from backend.prompts.post_trade import (
    POST_TRADE_SCHEMA,
    POST_TRADE_SYSTEM,
    build_post_trade_prompt,
)
from backend.prompts.risk_evaluator import (
    RISK_EVALUATOR_SYSTEM,
    RISK_VERDICT_SCHEMA,
    build_risk_evaluator_prompt,
)
from backend.storage.database import Database
from backend.utils.claude_client import ClaudeClient
from backend.utils.logger import logger

# ─── Données fictives réalistes ───────────────────────────────────────

FAKE_INDICATORS = {
    "rsi_14": 28.5,
    "macd_line": -12.5,
    "macd_signal": -8.3,
    "macd_histogram": -4.2,
    "bb_upper": 84500.0,
    "bb_middle": 83200.0,
    "bb_lower": 81900.0,
    "bb_pct": 0.15,
    "vwap": 83100.0,
    "ema_9": 82800.0,
    "ema_21": 83100.0,
    "atr_14": 450.0,
    "volume_ratio": 2.3,
    "price_change_5m": -0.8,
    "price_change_15m": -1.5,
    "price_change_1h": -2.1,
    "price": 82050.0,
}

FAKE_ORDERBOOK = {
    "best_bid": 82040.0,
    "best_ask": 82060.0,
    "bid_ask_spread": 0.024,
    "imbalance_ratio": 0.62,
    "bids_volume": 15.4,
    "asks_volume": 9.5,
}

FAKE_PORTFOLIO = {
    "capital": 98.50,
    "open_positions": 0,
    "daily_pnl": -1.50,
    "daily_pnl_pct": -1.5,
    "drawdown_pct": 1.5,
}


async def test_memory_manager() -> None:
    logger.info("=== Test 1 : MemoryManager ===")
    db = Database()
    await db.connect()
    mm = MemoryManager(db)

    # Ajouter des leçons
    id1 = await mm.add_lesson(None, "pattern", "RSI < 25 avec volume > 2x moyenne précède souvent un rebond BTC dans les 15min", 0.6)
    id2 = await mm.add_lesson(None, "mistake", "Ne pas acheter quand RSI oversold mais tendance 15m fortement baissière", 0.5)
    id3 = await mm.add_lesson(None, "rule", "Réduire la taille de position de 50% quand ATR > 1.5x sa moyenne 24h", 0.8)

    # Renforcer une leçon
    await mm.reinforce(id1)

    # Afficher le contexte
    context = await mm.get_context()
    logger.info("Contexte mémoire :\n{}", context)
    assert "pattern" in context
    assert "mistake" in context

    # Test doublon
    id_dup = await mm.add_lesson(None, "pattern", "RSI < 25 avec volume élevé déclenche un rebond BTC", 0.5)
    assert id_dup == id1, "Le doublon aurait dû renforcer la leçon existante"

    # Test trades summary (vide pour l'instant)
    summary = await mm.get_recent_trades_summary()
    logger.info("Trades summary : {}", summary)

    await db.close()
    logger.success("MemoryManager OK")


async def test_market_analyst_prompt(claude: ClaudeClient, model: str, memory: str) -> dict:
    logger.info("=== Test 2 : Market Analyst Prompt ===")

    prompt = build_market_analyst_prompt(
        pair="BTCUSDT",
        indicators=FAKE_INDICATORS,
        orderbook=FAKE_ORDERBOOK,
        memory=memory,
        recent_trades="## Historique récent\nAucun trade clôturé pour le moment.",
    )

    response = await claude.ask_json(
        model=model,
        system=MARKET_ANALYST_SYSTEM,
        prompt=prompt,
        schema=MARKET_ANALYSIS_SCHEMA,
    )

    assert response.json_data is not None, "Réponse JSON invalide !"
    data = response.json_data
    logger.info("Régime: {} | Force: {} | Résumé: {}", data.get("market_regime"), data.get("strength"), data.get("summary"))
    logger.info("Observations: {}", data.get("key_observations"))
    logger.info("Risques: {}", data.get("risks"))
    logger.success("Market Analyst Prompt OK — ${:.4f}", response.cost_usd)
    return data


async def test_decision_prompt(claude: ClaudeClient, model: str, memory: str, analysis_data: dict) -> dict:
    logger.info("=== Test 3 : Decision Agent Prompt ===")

    analysis = MarketAnalysis(
        market_regime=analysis_data.get("market_regime", "ranging"),
        strength=analysis_data.get("strength", 0.5),
        key_observations=analysis_data.get("key_observations", []),
        risks=analysis_data.get("risks", []),
        relevant_memory=analysis_data.get("relevant_memory", []),
        summary=analysis_data.get("summary", ""),
    )

    prompt = build_decision_prompt(
        pair="BTCUSDT",
        signal_score=-0.65,
        analysis=analysis,
        indicators=FAKE_INDICATORS,
        memory=memory,
        recent_trades="## Historique récent\nAucun trade clôturé pour le moment.",
        portfolio=FAKE_PORTFOLIO,
    )

    response = await claude.ask_json(
        model=model,
        system=DECISION_AGENT_SYSTEM,
        prompt=prompt,
        schema=TRADE_DECISION_SCHEMA,
    )

    assert response.json_data is not None, "Réponse JSON invalide !"
    data = response.json_data
    logger.info("Action: {} | Confiance: {} | Position: {}%", data.get("action"), data.get("confidence"), data.get("position_size_pct"))
    logger.info("Raisonnement: {}", data.get("reasoning"))
    logger.success("Decision Agent Prompt OK — ${:.4f}", response.cost_usd)
    return data


async def test_risk_evaluator_prompt(claude: ClaudeClient, model: str, memory: str, decision_data: dict, analysis_data: dict) -> dict:
    logger.info("=== Test 4 : Risk Evaluator Prompt ===")

    # Assurer les champs requis avec des valeurs par défaut
    decision = {
        "action": decision_data.get("action", "BUY"),
        "confidence": decision_data.get("confidence", 0.5),
        "reasoning": decision_data.get("reasoning", ""),
        "position_size_pct": decision_data.get("position_size_pct", 0.03),
        "expected_holding_time": decision_data.get("expected_holding_time", "1h"),
        "key_factors": decision_data.get("key_factors", []),
        "risks_acknowledged": decision_data.get("risks_acknowledged", []),
    }

    prompt = build_risk_evaluator_prompt(
        pair="BTCUSDT",
        decision=decision,
        analysis=analysis_data,
        indicators=FAKE_INDICATORS,
        portfolio=FAKE_PORTFOLIO,
        memory=memory,
        recent_trades="## Historique récent\nAucun trade clôturé pour le moment.",
    )

    response = await claude.ask_json(
        model=model,
        system=RISK_EVALUATOR_SYSTEM,
        prompt=prompt,
        schema=RISK_VERDICT_SCHEMA,
    )

    assert response.json_data is not None, "Réponse JSON invalide !"
    data = response.json_data
    logger.info("Verdict: {} | Position ajustée: {}%", data.get("verdict"), data.get("adjusted_position_pct"))
    logger.info("Raisonnement: {}", data.get("reasoning"))
    logger.info("Concerns: {}", data.get("concerns"))
    logger.success("Risk Evaluator Prompt OK — ${:.4f}", response.cost_usd)
    return data


async def test_post_trade_prompt(claude: ClaudeClient, model: str, memory: str) -> None:
    logger.info("=== Test 5 : Post-Trade Learner Prompt ===")

    fake_trade = {
        "pair": "BTCUSDT",
        "side": "BUY",
        "entry_price": 82050.0,
        "exit_price": 81200.0,
        "entry_time": "2026-03-15T14:30:00Z",
        "exit_time": "2026-03-15T14:45:00Z",
        "pnl": -1.05,
        "pnl_pct": -1.03,
        "duration_minutes": 15,
        "status": "closed_sl",
        "decision_reasoning": "RSI oversold à 28.5 avec volume élevé, achat sur signal de rebond. EMA9 < EMA21 indiquait une tendance baissière mais le volume ratio de 2.3x suggérait un retournement.",
    }
    fake_exit_indicators = {**FAKE_INDICATORS, "rsi_14": 35.2, "macd_histogram": -2.1}

    prompt = build_post_trade_prompt(
        trade=fake_trade,
        indicators_at_entry=FAKE_INDICATORS,
        indicators_at_exit=fake_exit_indicators,
        memory=memory,
    )

    response = await claude.ask_json(
        model=model,
        system=POST_TRADE_SYSTEM,
        prompt=prompt,
        schema=POST_TRADE_SCHEMA,
    )

    assert response.json_data is not None, "Réponse JSON invalide !"
    data = response.json_data
    logger.info("Analyse: {}", data.get("outcome_analysis"))
    lesson = data.get("lesson", {})
    logger.info("Leçon [{}]: {} (confiance: {})", lesson.get("category"), lesson.get("content"), lesson.get("confidence"))
    logger.success("Post-Trade Learner Prompt OK — ${:.4f}", response.cost_usd)


async def main() -> None:
    logger.info("========== CryptoBot — Test Phase 2 ==========")
    settings = get_settings()
    claude = ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)
    model = settings.AI_MODEL_FAST

    try:
        # 1. Memory Manager
        await test_memory_manager()

        # Recréer la mémoire pour les tests de prompts
        db = Database()
        await db.connect()
        mm = MemoryManager(db)
        memory = await mm.get_context()
        await db.close()

        # 2-5. Chaîne de prompts (séquentielle car chaque test dépend du précédent)
        analysis_data = await test_market_analyst_prompt(claude, model, memory)
        decision_data = await test_decision_prompt(claude, model, memory, analysis_data)

        if decision_data.get("action") != "WAIT":
            await test_risk_evaluator_prompt(claude, model, memory, decision_data, analysis_data)
        else:
            logger.info("=== Test 4 : Risk Evaluator SKIP (decision=WAIT) — test forcé ===")
            # Forcer un test même si WAIT
            decision_data["action"] = "BUY"
            decision_data["position_size_pct"] = decision_data.get("position_size_pct", 0.03) or 0.03
            await test_risk_evaluator_prompt(claude, model, memory, decision_data, analysis_data)

        await test_post_trade_prompt(claude, model, memory)

        logger.success(
            "========== PHASE 2 : TOUS LES TESTS OK — coût total ${:.4f} ==========",
            claude.total_cost,
        )
    except Exception as e:
        logger.error("ÉCHEC : {}", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
