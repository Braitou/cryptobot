"""Test clé Phase 4 : l'IA dit BUY, le Risk Guard refuse.

Le Risk Guard Python est INVIOLABLE — peu importe ce que l'IA décide.
4 scénarios :
  1. Drawdown 16% → kill switch total → BLOQUÉ
  2. Perte jour -4% → kill switch jour → BLOQUÉ
  3. 2 positions ouvertes → max atteint → BLOQUÉ
  4. Tout OK, Risk Evaluator réduit la position → Risk Guard approuve → trade exécuté
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.ai_decision import DecisionAgent
from backend.agents.ai_market_analyst import MarketAnalystAgent
from backend.agents.ai_risk_evaluator import RiskEvaluatorAgent
from backend.agents.executor import OrderExecutor
from backend.agents.risk_guard import RiskGuard
from backend.config import get_settings
from backend.memory.manager import MemoryManager
from backend.storage.database import Database
from backend.utils.binance_client import BinanceClient
from backend.utils.claude_client import ClaudeClient
from backend.utils.logger import logger

# Signal hyper-bullish — l'IA DEVRAIT vouloir acheter
BULLISH = {
    "rsi_14": 22.0, "macd_line": 20.0, "macd_signal": 8.0, "macd_histogram": 12.0,
    "bb_upper": 84500.0, "bb_middle": 83200.0, "bb_lower": 81900.0, "bb_pct": 0.05,
    "vwap": 82200.0, "ema_9": 83500.0, "ema_21": 83100.0, "atr_14": 300.0,
    "volume_ratio": 3.5, "price_change_5m": 1.5, "price_change_15m": 2.0,
    "price_change_1h": 0.5, "price": 82000.0,
}
ORDERBOOK = {
    "bid_ask_spread": 0.02, "imbalance_ratio": 0.75,
    "best_bid": 81990, "best_ask": 82010, "bids_volume": 25, "asks_volume": 8,
}


async def main() -> None:
    settings = get_settings()
    db = Database()
    await db.connect()

    claude = ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)
    memory = MemoryManager(db)
    bus: asyncio.Queue = asyncio.Queue()
    model = settings.AI_MODEL_FAST

    binance = BinanceClient(
        settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, settings.BINANCE_TESTNET
    )
    await binance.connect()

    analyst = MarketAnalystAgent(claude, memory, db, model, bus)
    decision_agent = DecisionAgent(claude, memory, db, model, bus)
    risk_eval_agent = RiskEvaluatorAgent(claude, memory, db, model, bus)

    rg = RiskGuard(
        max_position_pct=settings.MAX_POSITION_PCT,
        max_open_positions=settings.MAX_OPEN_POSITIONS,
        max_daily_loss_pct=settings.MAX_DAILY_LOSS_PCT,
        max_total_drawdown_pct=settings.MAX_TOTAL_DRAWDOWN_PCT,
    )
    executor = OrderExecutor(binance, db, trading_mode="paper", bus=bus)

    price = BULLISH["price"]
    atr = BULLISH["atr_14"]

    logger.info("=" * 60)
    logger.info("TEST CLÉ : IA dit BUY → Risk Guard refuse")
    logger.info("=" * 60)

    # ── Étape 1 : faire raisonner l'IA sur un signal bullish évident ──
    logger.info("")
    logger.info("Étape 1 : Chaîne IA sur signal bullish fort...")

    analysis = await analyst.analyze("BTCUSDT", BULLISH, ORDERBOOK)
    assert analysis is not None
    logger.info("  Analyst: {} (force {})", analysis.market_regime, analysis.strength)

    portfolio_ok = {
        "capital": 100.0, "open_positions": 0,
        "daily_pnl": 0, "daily_pnl_pct": 0, "drawdown_pct": 0,
    }
    decision = await decision_agent.decide("BTCUSDT", 0.70, analysis, BULLISH, portfolio_ok)
    assert decision is not None
    logger.info(
        "  Decision Agent: {} (confiance {:.0%}, position {:.1%})",
        decision.action, decision.confidence, decision.position_size_pct,
    )

    # Si l'IA dit WAIT malgré le signal bullish, on force un BUY
    if decision.action == "WAIT":
        logger.info("  (IA conservatrice — on force BUY pour tester les rejets)")
        decision.action = "BUY"
        decision.position_size_pct = 0.04

    ia_said_buy = decision.action == "BUY"
    logger.info("  → L'IA veut {} à {:.1%} du capital", decision.action, decision.position_size_pct)

    # Préparer la décision pour le Risk Guard
    def make_guard_decision(pct: float) -> dict:
        return {
            "action": "BUY",
            "position_size_pct": pct,
            "stop_loss": rg.compute_stop_loss(price, "BUY", atr),
            "take_profit": rg.compute_take_profit(price, "BUY", atr),
            "quantity": rg.compute_quantity(100.0, pct, price),
            "entry_price": price,
        }

    guard_dec = make_guard_decision(decision.position_size_pct)

    # ── Scénario 1 : Drawdown 16% ──
    logger.info("")
    logger.info("--- Scénario 1 : Drawdown 16% (> max 15%) ---")

    check = rg.check(guard_dec, {
        "capital": 85.0, "open_positions": 0,
        "daily_pnl_pct": -0.01, "drawdown_pct": 0.16,
    })
    assert not check.approved, "ÉCHEC CRITIQUE : Risk Guard aurait dû refuser !"
    logger.info("  Risk Guard: REJETÉ — {}", check.violations)
    logger.success("  IA dit BUY → Risk Guard dit NON (drawdown) → PAS DE TRADE")

    rg.reset_total_kill()

    # ── Scénario 2 : Perte jour -4% ──
    logger.info("")
    logger.info("--- Scénario 2 : Perte jour -4% (> max 3%) ---")

    check = rg.check(guard_dec, {
        "capital": 96.0, "open_positions": 0,
        "daily_pnl_pct": -0.04, "drawdown_pct": 0.04,
    })
    assert not check.approved, "ÉCHEC CRITIQUE : Risk Guard aurait dû refuser !"
    logger.info("  Risk Guard: REJETÉ — {}", check.violations)
    logger.success("  IA dit BUY → Risk Guard dit NON (perte jour) → PAS DE TRADE")

    # Vérifier que le kill switch persiste
    check_after = rg.check(guard_dec, portfolio_ok)
    assert not check_after.approved, "Kill switch jour doit persister !"
    logger.success("  Kill switch jour persiste — même un portfolio OK est bloqué")

    rg.reset_daily_kill()

    # ── Scénario 3 : 2 positions ouvertes ──
    logger.info("")
    logger.info("--- Scénario 3 : 2 positions déjà ouvertes (max=2) ---")

    check = rg.check(guard_dec, {
        "capital": 100.0, "open_positions": 2,
        "daily_pnl_pct": 0, "drawdown_pct": 0,
    })
    assert not check.approved, "ÉCHEC CRITIQUE : Risk Guard aurait dû refuser !"
    logger.info("  Risk Guard: REJETÉ — {}", check.violations)
    logger.success("  IA dit BUY → Risk Guard dit NON (max positions) → PAS DE TRADE")

    # ── Scénario 4 : Tout OK → Risk Evaluator réduit → Risk Guard approuve → trade ──
    logger.info("")
    logger.info("--- Scénario 4 : Portfolio sain — chaîne complète jusqu'à l'exécution ---")

    risk_verdict = await risk_eval_agent.evaluate(
        "BTCUSDT", decision, analysis, BULLISH, portfolio_ok
    )
    assert risk_verdict is not None
    logger.info(
        "  Risk Evaluator: {} (position {:.1%} → {:.1%})",
        risk_verdict.verdict, decision.position_size_pct, risk_verdict.adjusted_position_pct,
    )

    if risk_verdict.verdict == "REJECT":
        logger.info("  Risk Evaluator a rejeté — le Risk Guard n'a pas besoin d'intervenir")
    else:
        final_pct = risk_verdict.adjusted_position_pct
        final_dec = make_guard_decision(final_pct)

        check = rg.check(final_dec, portfolio_ok)
        logger.info("  Risk Guard: approved={}", check.approved)

        if check.approved:
            exec_dec = {
                "pair": "BTCUSDT", "action": "BUY",
                "quantity": final_dec["quantity"],
                "stop_loss": final_dec["stop_loss"],
                "take_profit": final_dec["take_profit"],
                "signal_score": 0.70,
                "decision_reasoning": decision.reasoning,
            }
            result = await executor.execute(exec_dec)
            assert result.success
            logger.success(
                "  Trade #{} exécuté — BUY {:.6f} BTC @ {:.2f} (position {:.1%})",
                result.trade_id, result.quantity, result.entry_price, final_pct,
            )
        else:
            logger.info("  Risk Guard a rejeté (montant trop petit : {:.2f} USDT)", final_pct * 100)

    # ── Bilan ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("BILAN")
    logger.info("=" * 60)
    logger.info("Scénario 1 (drawdown 16%)     : IA=BUY → RiskGuard=REJETÉ → Pas de trade")
    logger.info("Scénario 2 (perte jour -4%)    : IA=BUY → RiskGuard=REJETÉ → Pas de trade")
    logger.info("Scénario 3 (2 positions)       : IA=BUY → RiskGuard=REJETÉ → Pas de trade")
    logger.info("Scénario 4 (portfolio sain)    : IA=BUY → RiskEval ajuste → RiskGuard vérifie → Trade")
    logger.info("Coût API : ${:.4f}", claude.total_cost)
    logger.success("")
    logger.success("LE RISK GUARD PYTHON EST INVIOLABLE.")
    logger.success("Aucun agent IA ne peut le contourner.")
    logger.success("=" * 60)

    await binance.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
