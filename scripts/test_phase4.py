"""Test Phase 4 — Risk Guard + Executor (paper trading).

1. Risk Guard — 7 scénarios de rejet + 1 approbation
2. Calculs SL/TP/trailing
3. Executor — paper trade complet (ouverture + fermeture SL/TP)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.executor import OrderExecutor
from backend.agents.risk_guard import RiskGuard
from backend.config import get_settings
from backend.storage.database import Database
from backend.utils.binance_client import BinanceClient
from backend.utils.logger import logger

PORTFOLIO_OK = {
    "capital": 100.0,
    "open_positions": 0,
    "daily_pnl_pct": 0.0,
    "drawdown_pct": 0.0,
}


# ═══════════════════════════════════════════════════════════════════════
# TEST 1 : Risk Guard — rejets
# ═══════════════════════════════════════════════════════════════════════

async def test_risk_guard_rejections() -> None:
    logger.info("=" * 60)
    logger.info("TEST 1 : Risk Guard — scénarios de rejet")
    logger.info("=" * 60)

    settings = get_settings()
    rg = RiskGuard(
        max_position_pct=settings.MAX_POSITION_PCT,
        stop_loss_atr_mult=settings.STOP_LOSS_ATR_MULT,
        take_profit_atr_mult=settings.TAKE_PROFIT_ATR_MULT,
        trailing_stop_atr_mult=settings.TRAILING_STOP_ATR_MULT,
        max_open_positions=settings.MAX_OPEN_POSITIONS,
        max_daily_loss_pct=settings.MAX_DAILY_LOSS_PCT,
        max_total_drawdown_pct=settings.MAX_TOTAL_DRAWDOWN_PCT,
    )

    # Scénario 1 : position trop grosse
    result = rg.check(
        {"position_size_pct": 0.10, "stop_loss": 80000, "take_profit": 85000,
         "quantity": 0.001, "entry_price": 82000},
        PORTFOLIO_OK,
    )
    assert not result.approved, "Doit rejeter position > 5%"
    logger.info("  [1] Position 10% → REJETÉ ✓ : {}", result.reason)

    # Scénario 2 : trop de positions ouvertes
    result = rg.check(
        {"position_size_pct": 0.03, "stop_loss": 80000, "take_profit": 85000,
         "quantity": 0.001, "entry_price": 82000},
        {**PORTFOLIO_OK, "open_positions": 2},
    )
    assert not result.approved, "Doit rejeter si 2 positions ouvertes"
    logger.info("  [2] 2 positions ouvertes → REJETÉ ✓ : {}", result.reason)

    # Scénario 3 : perte journalière > 3%
    result = rg.check(
        {"position_size_pct": 0.03, "stop_loss": 80000, "take_profit": 85000,
         "quantity": 0.001, "entry_price": 82000},
        {**PORTFOLIO_OK, "daily_pnl_pct": -0.035},
    )
    assert not result.approved, "Doit rejeter si perte jour > 3%"
    assert rg._daily_kill, "Kill switch jour doit être activé"
    logger.info("  [3] Perte jour -3.5% → REJETÉ + KILL SWITCH JOUR ✓")

    # Scénario 3b : vérifier que le kill switch jour bloque
    result = rg.check(
        {"position_size_pct": 0.01, "stop_loss": 80000, "take_profit": 85000,
         "quantity": 0.001, "entry_price": 82000},
        PORTFOLIO_OK,
    )
    assert not result.approved, "Kill switch jour doit bloquer"
    logger.info("  [3b] Kill switch jour actif → REJETÉ ✓")

    # Reset pour les tests suivants
    rg.reset_daily_kill()

    # Scénario 4 : drawdown > 15%
    result = rg.check(
        {"position_size_pct": 0.03, "stop_loss": 80000, "take_profit": 85000,
         "quantity": 0.001, "entry_price": 82000},
        {**PORTFOLIO_OK, "drawdown_pct": 0.16},
    )
    assert not result.approved, "Doit rejeter si drawdown > 15%"
    assert rg._total_kill, "Kill switch total doit être activé"
    logger.info("  [4] Drawdown 16% → REJETÉ + KILL SWITCH TOTAL ✓")

    rg.reset_total_kill()

    # Scénario 5 : stop-loss absent
    result = rg.check(
        {"position_size_pct": 0.03, "stop_loss": None, "take_profit": 85000,
         "quantity": 0.001, "entry_price": 82000},
        PORTFOLIO_OK,
    )
    assert not result.approved, "Doit rejeter sans stop-loss"
    logger.info("  [5] Stop-loss absent → REJETÉ ✓")

    # Scénario 6 : take-profit absent
    result = rg.check(
        {"position_size_pct": 0.03, "stop_loss": 80000, "take_profit": None,
         "quantity": 0.001, "entry_price": 82000},
        PORTFOLIO_OK,
    )
    assert not result.approved, "Doit rejeter sans take-profit"
    logger.info("  [6] Take-profit absent → REJETÉ ✓")

    # Scénario 7 : montant < 5 USDT
    result = rg.check(
        {"position_size_pct": 0.001, "stop_loss": 80000, "take_profit": 85000,
         "quantity": 0.00001, "entry_price": 82000},
        PORTFOLIO_OK,
    )
    assert not result.approved, "Doit rejeter montant < 5 USDT"
    logger.info("  [7] Montant < 5 USDT → REJETÉ ✓")

    # Scénario 8 : tout OK → APPROUVÉ
    result = rg.check(
        {"position_size_pct": 0.03, "stop_loss": 81520, "take_profit": 82640,
         "quantity": 0.00037, "entry_price": 82000},
        PORTFOLIO_OK,
    )
    assert result.approved, f"Doit approuver : {result.reason}"
    logger.info("  [8] Tout OK → APPROUVÉ ✓")

    logger.success("Risk Guard rejets OK — 7/7 rejets + 1 approbation")


# ═══════════════════════════════════════════════════════════════════════
# TEST 2 : Calculs SL/TP/Trailing
# ═══════════════════════════════════════════════════════════════════════

async def test_sl_tp_calculations() -> None:
    logger.info("=" * 60)
    logger.info("TEST 2 : Calculs SL/TP/Trailing")
    logger.info("=" * 60)

    rg = RiskGuard()

    # SL/TP pour BUY
    sl_buy = rg.compute_stop_loss(82000, "BUY", 320)
    tp_buy = rg.compute_take_profit(82000, "BUY", 320)
    assert sl_buy == 82000 - 1.5 * 320, f"SL BUY incorrect: {sl_buy}"
    assert tp_buy == 82000 + 2.0 * 320, f"TP BUY incorrect: {tp_buy}"
    logger.info("  BUY @ 82000 (ATR=320) → SL={} TP={}", sl_buy, tp_buy)

    # SL/TP pour SELL
    sl_sell = rg.compute_stop_loss(82000, "SELL", 320)
    tp_sell = rg.compute_take_profit(82000, "SELL", 320)
    assert sl_sell == 82000 + 1.5 * 320, f"SL SELL incorrect: {sl_sell}"
    assert tp_sell == 82000 - 2.0 * 320, f"TP SELL incorrect: {tp_sell}"
    logger.info("  SELL @ 82000 (ATR=320) → SL={} TP={}", sl_sell, tp_sell)

    # Quantity
    qty = rg.compute_quantity(100.0, 0.03, 82000)
    expected = round(100.0 * 0.03 / 82000, 6)
    assert qty == expected, f"Qty incorrecte: {qty} != {expected}"
    logger.info("  Quantity: capital=100, pos=3%, price=82000 → {:.6f} BTC ({:.2f} USDT)", qty, qty * 82000)

    # Trailing stop — BUY
    # Pas encore activé (profit < 1 ATR)
    assert not rg.check_trailing_stop(82000, "BUY", 82200, 320, 82200), "Trailing pas activé à +200 (< ATR=320)"
    # Activé, mais prix au-dessus du trailing
    assert not rg.check_trailing_stop(82000, "BUY", 82500, 320, 82600), "Trailing pas déclenché, prix > trailing stop"
    # Activé et déclenché (prix redescend sous highest - ATR)
    assert rg.check_trailing_stop(82000, "BUY", 82200, 320, 82600), "Trailing doit déclencher à 82200 (highest=82600, stop=82280)"
    logger.info("  Trailing stop BUY : activation + déclenchement OK")

    # Trailing stop — SELL
    assert not rg.check_trailing_stop(82000, "SELL", 81900, 320, 81900), "Trailing pas activé"
    assert rg.check_trailing_stop(82000, "SELL", 81800, 320, 81400), "Trailing SELL doit déclencher"
    logger.info("  Trailing stop SELL : OK")

    logger.success("Calculs SL/TP/Trailing OK")


# ═══════════════════════════════════════════════════════════════════════
# TEST 3 : Executor paper trade complet
# ═══════════════════════════════════════════════════════════════════════

async def test_executor_paper(db: Database, binance: BinanceClient) -> None:
    logger.info("=" * 60)
    logger.info("TEST 3 : Executor — paper trade complet")
    logger.info("=" * 60)

    bus: asyncio.Queue = asyncio.Queue()
    executor = OrderExecutor(binance, db, trading_mode="paper", bus=bus)

    rg = RiskGuard()
    price = await binance.get_price("BTCUSDT")
    atr = 300.0  # estimé

    sl = rg.compute_stop_loss(price, "BUY", atr)
    tp = rg.compute_take_profit(price, "BUY", atr)
    qty = rg.compute_quantity(100.0, 0.03, price)

    logger.info("  Prix actuel: {:.2f} | SL={:.2f} | TP={:.2f} | Qty={:.6f}", price, sl, tp, qty)

    decision = {
        "pair": "BTCUSDT",
        "action": "BUY",
        "quantity": qty,
        "stop_loss": sl,
        "take_profit": tp,
        "signal_score": 0.65,
        "market_analysis": "Test Phase 4 — marché neutre",
        "decision_reasoning": "Test de l'executor paper trading",
        "risk_evaluation": "Test approuvé",
        "indicators_snapshot": {"rsi_14": 45, "atr_14": 300},
    }

    # Exécuter
    result = await executor.execute(decision)
    assert result.success, f"Exécution échouée: {result.error}"
    assert result.trade_id is not None
    assert result.entry_price > 0
    assert result.fees > 0

    logger.info(
        "  Trade #{} ouvert — entry={:.2f} qty={:.6f} fees={:.4f}",
        result.trade_id, result.entry_price, result.quantity, result.fees,
    )

    # Vérifier en base
    trade = await db.fetchone("SELECT * FROM trades WHERE id = ?", (result.trade_id,))
    assert trade is not None
    assert trade["status"] == "open"
    assert trade["pair"] == "BTCUSDT"
    assert trade["side"] == "BUY"
    assert float(trade["stop_loss"]) == sl
    assert float(trade["take_profit"]) == tp
    logger.info("  Vérifié en base: status={}, entry={}", trade["status"], trade["entry_price"])

    # Vérifier le bus
    assert bus.qsize() >= 1, "Pas de message sur le bus"
    msg = await bus.get()
    assert msg.type == "order_executed"
    logger.info("  Message bus: type={}, trade_id={}", msg.type, msg.data["trade_id"])

    # Fermer manuellement (simuler SL touché)
    await executor._close_position(trade, sl, "closed_sl")
    closed_trade = await db.fetchone("SELECT * FROM trades WHERE id = ?", (result.trade_id,))
    assert closed_trade["status"] == "closed_sl"
    assert closed_trade["pnl"] is not None
    assert closed_trade["exit_price"] is not None

    logger.info(
        "  Trade #{} fermé — exit={} pnl={:+.4f} USDT ({:+.2f}%) — {}",
        result.trade_id, closed_trade["exit_price"],
        closed_trade["pnl"], closed_trade["pnl_pct"], closed_trade["status"],
    )

    # Vérifier message de fermeture
    msg2 = await bus.get()
    assert msg2.type == "order_closed"
    logger.info("  Message bus: type={}, reason={}", msg2.type, msg2.data["reason"])

    logger.success("Executor paper trade OK")


# ═══════════════════════════════════════════════════════════════════════
# TEST 4 : Flux complet Risk Guard → Executor
# ═══════════════════════════════════════════════════════════════════════

async def test_full_flow(db: Database, binance: BinanceClient) -> None:
    logger.info("=" * 60)
    logger.info("TEST 4 : Flux complet Risk Guard → Executor")
    logger.info("=" * 60)

    settings = get_settings()
    rg = RiskGuard(
        max_position_pct=settings.MAX_POSITION_PCT,
        max_open_positions=settings.MAX_OPEN_POSITIONS,
    )
    bus: asyncio.Queue = asyncio.Queue()
    executor = OrderExecutor(binance, db, trading_mode="paper", bus=bus)

    price = await binance.get_price("ETHUSDT")
    atr = 80.0

    # Simuler une décision IA (position_size_pct=0.05 pour dépasser 5 USDT min)
    ai_decision = {
        "action": "BUY",
        "position_size_pct": 0.05,
        "stop_loss": rg.compute_stop_loss(price, "BUY", atr),
        "take_profit": rg.compute_take_profit(price, "BUY", atr),
        "quantity": rg.compute_quantity(100.0, 0.05, price),
        "entry_price": price,
    }

    # Risk Guard check
    check = rg.check(ai_decision, PORTFOLIO_OK)
    assert check.approved, f"Devrait être approuvé: {check.reason}"
    logger.info("  Risk Guard: APPROUVÉ")

    # Exécuter
    exec_decision = {
        "pair": "ETHUSDT",
        "action": "BUY",
        "quantity": ai_decision["quantity"],
        "stop_loss": ai_decision["stop_loss"],
        "take_profit": ai_decision["take_profit"],
        "signal_score": 0.45,
        "decision_reasoning": "Test flux complet",
    }
    result = await executor.execute(exec_decision)
    assert result.success
    logger.info("  Trade #{} ouvert — ETH @ {:.2f}", result.trade_id, result.entry_price)

    # Fermer au TP
    trade = await db.fetchone("SELECT * FROM trades WHERE id = ?", (result.trade_id,))
    await executor._close_position(trade, ai_decision["take_profit"], "closed_tp")

    closed = await db.fetchone("SELECT * FROM trades WHERE id = ?", (result.trade_id,))
    assert closed["status"] == "closed_tp"
    assert closed["pnl"] > 0, "PnL doit être positif au TP"
    logger.info(
        "  Trade #{} fermé au TP — pnl={:+.4f} USDT ({:+.2f}%)",
        result.trade_id, closed["pnl"], closed["pnl_pct"],
    )

    logger.success("Flux complet Risk Guard → Executor OK")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

async def main() -> None:
    logger.info("=" * 60)
    logger.info("CryptoBot — Test Phase 4 — Risk Guard + Executor")
    logger.info("=" * 60)

    settings = get_settings()
    db = Database()
    await db.connect()
    # Nettoyer les trades de test précédents
    await db.execute("DELETE FROM trades")

    binance = BinanceClient(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        testnet=settings.BINANCE_TESTNET,
    )
    await binance.connect()

    try:
        await test_risk_guard_rejections()
        await test_sl_tp_calculations()
        await test_executor_paper(db, binance)
        await test_full_flow(db, binance)

        # Bilan
        trades = await db.fetchall("SELECT id, pair, side, status, pnl, pnl_pct FROM trades")
        logger.info("")
        logger.info("BILAN — {} trades en base:", len(trades))
        for t in trades:
            logger.info("  #{} {} {} {} pnl={} ({}%)", t["id"], t["pair"], t["side"], t["status"], t["pnl"], t["pnl_pct"])

        logger.success("=" * 60)
        logger.success("PHASE 4 : TOUS LES TESTS OK")
        logger.success("=" * 60)
    except Exception as e:
        logger.error("ÉCHEC : {}", e)
        import traceback
        traceback.print_exc()
        raise
    finally:
        await binance.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
