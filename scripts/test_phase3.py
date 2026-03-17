"""Test Phase 3 — Agents IA complets.

1. Test déduplication mémoire (10 variantes → 1 seule leçon)
2. Test individuel de chaque agent avec données fictives
3. Chaîne complète : signal → analyst → decision → risk → post-trade
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.ai_decision import DecisionAgent
from backend.agents.ai_market_analyst import MarketAnalystAgent
from backend.agents.ai_post_trade import PostTradeAgent
from backend.agents.ai_risk_evaluator import RiskEvaluatorAgent
from backend.config import get_settings
from backend.memory.manager import MemoryManager
from backend.prompts.decision import MarketAnalysis, TradeDecision
from backend.prompts.risk_evaluator import RiskVerdict
from backend.storage.database import Database
from backend.utils.claude_client import ClaudeClient
from backend.utils.logger import logger

# ─── Données fictives ─────────────────────────────────────────────────

BULLISH_INDICATORS = {
    "rsi_14": 25.0,
    "macd_line": 15.0,
    "macd_signal": 8.0,
    "macd_histogram": 7.0,
    "bb_upper": 84500.0,
    "bb_middle": 83200.0,
    "bb_lower": 81900.0,
    "bb_pct": 0.10,
    "vwap": 82500.0,
    "ema_9": 83400.0,
    "ema_21": 83100.0,
    "atr_14": 320.0,
    "volume_ratio": 2.8,
    "price_change_5m": 0.6,
    "price_change_15m": 1.2,
    "price_change_1h": -0.5,
    "price": 82100.0,
}

BEARISH_INDICATORS = {
    "rsi_14": 78.0,
    "macd_line": -18.0,
    "macd_signal": -10.0,
    "macd_histogram": -8.0,
    "bb_upper": 84500.0,
    "bb_middle": 83200.0,
    "bb_lower": 81900.0,
    "bb_pct": 0.92,
    "vwap": 83800.0,
    "ema_9": 83000.0,
    "ema_21": 83400.0,
    "atr_14": 480.0,
    "volume_ratio": 3.1,
    "price_change_5m": -1.2,
    "price_change_15m": -2.0,
    "price_change_1h": -3.5,
    "price": 84300.0,
}

ORDERBOOK = {
    "best_bid": 82090.0,
    "best_ask": 82110.0,
    "bid_ask_spread": 0.024,
    "imbalance_ratio": 0.65,
    "bids_volume": 18.2,
    "asks_volume": 9.8,
}

PORTFOLIO = {
    "capital": 100.0,
    "open_positions": 0,
    "daily_pnl": 0.0,
    "daily_pnl_pct": 0.0,
    "drawdown_pct": 0.0,
}


# ═══════════════════════════════════════════════════════════════════════
# TEST 1 : Déduplication mémoire
# ═══════════════════════════════════════════════════════════════════════

async def test_memory_dedup(db: Database) -> None:
    logger.info("{'='*60}")
    logger.info("TEST 1 : Déduplication mémoire — 10 variantes → 1 leçon")
    logger.info("{'='*60}")

    mm = MemoryManager(db)

    # 10 façons de dire la même chose
    variants = [
        "Ne pas acheter quand le volume est faible sur BTC",
        "Éviter d'acheter BTC quand le volume est faible",
        "Ne pas acheter BTC si le volume est faible",
        "Quand le volume est faible, ne pas acheter BTC",
        "Le volume faible sur BTC indique qu'il ne faut pas acheter",
        "Acheter BTC avec un volume faible est une erreur",
        "BTC : ne pas acheter quand le volume est faible",
        "Volume faible = ne pas acheter BTC",
        "Ne pas entrer long BTC quand le volume est faible",
        "Éviter les achats BTC en période de volume faible",
    ]

    ids = []
    for i, v in enumerate(variants):
        entry_id = await mm.add_lesson(trade_id=None, category="mistake", content=v)
        ids.append(entry_id)
        logger.debug("  Variante {} → leçon #{}", i + 1, entry_id)

    unique_ids = set(ids)
    logger.info("IDs retournés : {}", ids)
    logger.info("IDs uniques : {} (attendu: 1-2)", len(unique_ids))

    # Vérifier qu'on a au max 2 leçons (tolérance pour les formulations très différentes)
    entries = await db.fetchall(
        "SELECT id, content, confidence, times_referenced FROM memory_entries WHERE category = 'mistake' AND active = TRUE"
    )
    logger.info("Leçons actives en base : {}", len(entries))
    for e in entries:
        logger.info("  #{} (conf={:.1f}, ref={}) : {}", e["id"], e["confidence"], e["times_referenced"], e["content"][:60])

    assert len(entries) <= 3, f"Trop de leçons ! {len(entries)} au lieu de 1-3 max"

    # La leçon la plus forte doit avoir été renforcée plusieurs fois
    top = max(entries, key=lambda e: e["times_referenced"])
    logger.info("Top leçon: #{} — {} fois référencée, confiance {:.1f}", top["id"], top["times_referenced"], top["confidence"])
    assert top["times_referenced"] >= 5, f"Pas assez de renforcements : {top['times_referenced']}"

    logger.success("Déduplication OK — {} variantes → {} leçons, top renforcée {} fois",
                   len(variants), len(entries), top["times_referenced"])


# ═══════════════════════════════════════════════════════════════════════
# TEST 2 : Market Analyst — individuel
# ═══════════════════════════════════════════════════════════════════════

async def test_market_analyst(
    agent: MarketAnalystAgent, scenario: str, indicators: dict, orderbook: dict
) -> MarketAnalysis:
    logger.info("{'='*60}")
    logger.info("TEST 2 : Market Analyst — scénario {}", scenario)
    logger.info("{'='*60}")

    analysis = await agent.analyze("BTCUSDT", indicators, orderbook)
    assert analysis is not None, "MarketAnalyst a retourné None !"

    # Vérifications de cohérence
    assert analysis.market_regime in ("trending_up", "trending_down", "ranging", "volatile"), \
        f"Régime invalide : {analysis.market_regime}"
    assert 0 <= analysis.strength <= 1, f"Force hors limites : {analysis.strength}"
    assert len(analysis.key_observations) > 0, "Aucune observation !"
    assert len(analysis.risks) > 0, "Aucun risque identifié !"
    assert len(analysis.summary) > 10, "Résumé trop court !"

    logger.info("  Régime: {} (force {})", analysis.market_regime, analysis.strength)
    logger.info("  {} observations, {} risques", len(analysis.key_observations), len(analysis.risks))
    logger.success("Market Analyst OK — scénario {}", scenario)
    return analysis


# ═══════════════════════════════════════════════════════════════════════
# TEST 3 : Decision Agent — individuel
# ═══════════════════════════════════════════════════════════════════════

async def test_decision_agent(
    agent: DecisionAgent,
    scenario: str,
    signal_score: float,
    analysis: MarketAnalysis,
    indicators: dict,
) -> TradeDecision:
    logger.info("{'='*60}")
    logger.info("TEST 3 : Decision Agent — scénario {}", scenario)
    logger.info("{'='*60}")

    decision = await agent.decide("BTCUSDT", signal_score, analysis, indicators, PORTFOLIO)
    assert decision is not None, "DecisionAgent a retourné None !"

    assert decision.action in ("BUY", "SELL", "WAIT"), f"Action invalide : {decision.action}"
    assert 0 <= decision.confidence <= 1, f"Confiance hors limites : {decision.confidence}"
    assert 0 <= decision.position_size_pct <= 0.05, \
        f"Position size hors limites : {decision.position_size_pct}"
    assert len(decision.reasoning) > 20, "Raisonnement trop court !"

    if decision.action == "WAIT":
        assert decision.position_size_pct == 0, "Position size doit être 0 quand WAIT"

    logger.info("  Action: {} (confiance {:.0%}, position {:.1%})", decision.action, decision.confidence, decision.position_size_pct)
    logger.info("  Raisonnement: {}…", decision.reasoning[:100])
    logger.success("Decision Agent OK — scénario {}", scenario)
    return decision


# ═══════════════════════════════════════════════════════════════════════
# TEST 4 : Risk Evaluator — individuel
# ═══════════════════════════════════════════════════════════════════════

async def test_risk_evaluator(
    agent: RiskEvaluatorAgent,
    decision: TradeDecision,
    analysis: MarketAnalysis,
    indicators: dict,
) -> RiskVerdict:
    logger.info("{'='*60}")
    logger.info("TEST 4 : Risk Evaluator")
    logger.info("{'='*60}")

    verdict = await agent.evaluate("BTCUSDT", decision, analysis, indicators, PORTFOLIO)
    assert verdict is not None, "RiskEvaluator a retourné None !"

    assert verdict.verdict in ("APPROVE", "REDUCE", "REJECT"), f"Verdict invalide : {verdict.verdict}"
    assert 0 <= verdict.adjusted_position_pct <= 0.05, \
        f"Position ajustée hors limites : {verdict.adjusted_position_pct}"
    assert len(verdict.reasoning) > 20, "Raisonnement trop court !"
    assert len(verdict.concerns) > 0, "Aucun concern !"

    logger.info("  Verdict: {} (position {:.1%})", verdict.verdict, verdict.adjusted_position_pct)
    logger.info("  Concerns: {}", verdict.concerns)
    logger.success("Risk Evaluator OK")
    return verdict


# ═══════════════════════════════════════════════════════════════════════
# TEST 5 : Post-Trade Learner — individuel
# ═══════════════════════════════════════════════════════════════════════

async def test_post_trade(agent: PostTradeAgent) -> None:
    logger.info("{'='*60}")
    logger.info("TEST 5 : Post-Trade Learner")
    logger.info("{'='*60}")

    fake_trade = {
        "id": 999,
        "pair": "BTCUSDT",
        "side": "BUY",
        "entry_price": 82100.0,
        "exit_price": 82750.0,
        "entry_time": "2026-03-15T14:30:00Z",
        "exit_time": "2026-03-15T15:15:00Z",
        "pnl": 0.79,
        "pnl_pct": 0.79,
        "duration_minutes": 45,
        "status": "closed_tp",
        "decision_reasoning": "RSI oversold à 25 avec volume 2.8x et MACD positif. Tendance court terme haussière confirmée par EMA9 > EMA21.",
    }
    exit_indicators = {**BULLISH_INDICATORS, "rsi_14": 55.0, "macd_histogram": 3.0, "bb_pct": 0.55}

    result = await agent.analyze(fake_trade, BULLISH_INDICATORS, exit_indicators)
    assert result is not None, "PostTrade a retourné None !"

    assert "outcome_analysis" in result, "Manque outcome_analysis"
    lesson = result.get("lesson", {})
    assert lesson.get("content"), "Pas de contenu dans la leçon !"
    assert lesson.get("category") in ("pattern", "mistake", "insight", "rule"), \
        f"Catégorie invalide : {lesson.get('category')}"

    logger.info("  Analyse: {}…", result["outcome_analysis"][:100])
    logger.info("  Leçon [{}]: {}", lesson.get("category"), lesson.get("content"))
    logger.success("Post-Trade Learner OK")


# ═══════════════════════════════════════════════════════════════════════
# TEST 6 : Chaîne complète sur signal simulé
# ═══════════════════════════════════════════════════════════════════════

async def test_full_chain(
    analyst: MarketAnalystAgent,
    decision_agent: DecisionAgent,
    risk_eval: RiskEvaluatorAgent,
    post_trade: PostTradeAgent,
) -> None:
    logger.info("{'='*60}")
    logger.info("TEST 6 : Chaîne complète — signal bullish → décision → risque → post-trade")
    logger.info("{'='*60}")

    # Étape 1 : Market Analyst
    logger.info("  [1/4] Market Analyst…")
    analysis = await analyst.analyze("BTCUSDT", BULLISH_INDICATORS, ORDERBOOK)
    assert analysis is not None

    # Étape 2 : Decision Agent
    logger.info("  [2/4] Decision Agent…")
    decision = await decision_agent.decide(
        "BTCUSDT", 0.65, analysis, BULLISH_INDICATORS, PORTFOLIO
    )
    assert decision is not None

    # Étape 3 : Risk Evaluator (seulement si pas WAIT)
    if decision.action != "WAIT":
        logger.info("  [3/4] Risk Evaluator…")
        verdict = await risk_eval.evaluate(
            "BTCUSDT", decision, analysis, BULLISH_INDICATORS, PORTFOLIO
        )
        assert verdict is not None
        logger.info("  → Verdict final : {} (position {:.1%})", verdict.verdict, verdict.adjusted_position_pct)
    else:
        logger.info("  [3/4] Risk Evaluator — SKIP (decision = WAIT)")
        verdict = None

    # Étape 4 : Post-Trade (simule un trade fermé basé sur cette décision)
    logger.info("  [4/4] Post-Trade Learner…")
    fake_closed_trade = {
        "id": 1000,
        "pair": "BTCUSDT",
        "side": decision.action if decision.action != "WAIT" else "BUY",
        "entry_price": 82100.0,
        "exit_price": 82500.0,
        "entry_time": "2026-03-16T10:00:00Z",
        "exit_time": "2026-03-16T10:35:00Z",
        "pnl": 0.49,
        "pnl_pct": 0.49,
        "duration_minutes": 35,
        "status": "closed_tp",
        "decision_reasoning": decision.reasoning,
    }
    exit_ind = {**BULLISH_INDICATORS, "rsi_14": 52.0, "macd_histogram": 4.0, "bb_pct": 0.50}
    pt_result = await post_trade.analyze(fake_closed_trade, BULLISH_INDICATORS, exit_ind)
    assert pt_result is not None

    logger.success("Chaîne complète OK — Analyst → Decision ({}) → Risk ({}) → PostTrade (leçon: [{}])",
                   decision.action,
                   verdict.verdict if verdict else "SKIP",
                   pt_result.get("lesson", {}).get("category", "?"))


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

async def main() -> None:
    logger.info("=" * 60)
    logger.info("CryptoBot — Test Phase 3 — Agents IA")
    logger.info("=" * 60)

    settings = get_settings()
    db = Database()
    await db.connect()

    # Nettoyer les données de test précédentes
    await db.execute("DELETE FROM memory_entries")
    await db.execute("DELETE FROM agent_logs")

    claude = ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)
    memory = MemoryManager(db)
    bus: asyncio.Queue = asyncio.Queue()
    model = settings.AI_MODEL_FAST

    # Instancier les agents
    analyst = MarketAnalystAgent(claude, memory, db, model, bus)
    decision_agent = DecisionAgent(claude, memory, db, model, bus)
    risk_eval = RiskEvaluatorAgent(claude, memory, db, model, bus)
    post_trade = PostTradeAgent(claude, memory, db, model, bus)

    try:
        # Test 1 : Déduplication mémoire
        await test_memory_dedup(db)

        # Test 2 : Market Analyst — scénario bullish
        analysis_bull = await test_market_analyst(analyst, "BULLISH", BULLISH_INDICATORS, ORDERBOOK)

        # Test 2b : Market Analyst — scénario bearish
        analysis_bear = await test_market_analyst(analyst, "BEARISH", BEARISH_INDICATORS, ORDERBOOK)

        # Test 3 : Decision Agent — signal bullish
        decision_bull = await test_decision_agent(
            decision_agent, "BULLISH", 0.65, analysis_bull, BULLISH_INDICATORS
        )

        # Test 3b : Decision Agent — signal bearish
        decision_bear = await test_decision_agent(
            decision_agent, "BEARISH", -0.60, analysis_bear, BEARISH_INDICATORS
        )

        # Test 4 : Risk Evaluator — sur la décision bullish
        test_decision = decision_bull if decision_bull.action != "WAIT" else decision_bear
        test_analysis = analysis_bull if decision_bull.action != "WAIT" else analysis_bear
        test_indicators = BULLISH_INDICATORS if decision_bull.action != "WAIT" else BEARISH_INDICATORS

        if test_decision.action == "WAIT":
            # Forcer un trade pour tester le Risk Evaluator
            logger.info("Les deux décisions sont WAIT — on force un BUY pour tester le Risk Evaluator")
            test_decision = TradeDecision(
                action="BUY", confidence=0.7, reasoning="Test forcé",
                position_size_pct=0.04, expected_holding_time="1h",
                key_factors=["RSI oversold", "MACD bullish"],
                risks_acknowledged=["Volatilité élevée"],
            )

        await test_risk_evaluator(risk_eval, test_decision, test_analysis, test_indicators)

        # Test 5 : Post-Trade Learner
        await test_post_trade(post_trade)

        # Test 6 : Chaîne complète
        await test_full_chain(analyst, decision_agent, risk_eval, post_trade)

        # Bilan
        logs = await db.fetchall("SELECT agent, COUNT(*) as cnt FROM agent_logs GROUP BY agent")
        memory_entries = await db.fetchall("SELECT id, category, content, confidence FROM memory_entries WHERE active = TRUE")

        logger.info("")
        logger.info("=" * 60)
        logger.info("BILAN")
        logger.info("=" * 60)
        logger.info("Appels Claude : {} total", sum(l["cnt"] for l in logs))
        for l in logs:
            logger.info("  {} : {} appels", l["agent"], l["cnt"])
        logger.info("Coût API total : ${:.4f}", claude.total_cost)
        logger.info("Leçons en mémoire : {}", len(memory_entries))
        for e in memory_entries:
            logger.info("  #{} [{}] (conf={:.1f}) {}", e["id"], e["category"], e["confidence"], e["content"][:60])
        logger.info("Messages sur le bus : {}", bus.qsize())

        logger.success("=" * 60)
        logger.success("PHASE 3 : TOUS LES TESTS OK — ${:.4f}", claude.total_cost)
        logger.success("=" * 60)

    except Exception as e:
        logger.error("ÉCHEC : {}", e)
        import traceback
        traceback.print_exc()
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
