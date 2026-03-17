"""Endpoints REST du dashboard."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from backend.utils.logger import logger


def create_router(get_orchestrator: Callable) -> APIRouter:
    """Crée le router avec accès à l'orchestrateur."""
    router = APIRouter()

    def _orch():
        o = get_orchestrator()
        if o is None:
            raise HTTPException(503, "Bot pas encore démarré")
        return o

    @router.get("/portfolio")
    async def get_portfolio() -> dict[str, Any]:
        o = _orch()
        state = await o._get_portfolio_state()
        state["api_cost_total"] = o.claude.total_cost if o.claude else 0
        state["kill_switch"] = o.risk_guard.kill_status if o.risk_guard else {}
        return state

    @router.get("/trades")
    async def get_trades(limit: int = 50) -> list[dict[str, Any]]:
        o = _orch()
        return await o.db.fetchall(
            """SELECT id, pair, side, entry_price, exit_price, quantity,
                      entry_time, exit_time, stop_loss, take_profit,
                      status, pnl, pnl_pct, fees_paid, signal_score,
                      decision_reasoning
               FROM trades ORDER BY id DESC LIMIT ?""",
            (limit,),
        )

    @router.get("/trades/{trade_id}")
    async def get_trade(trade_id: int) -> dict[str, Any]:
        o = _orch()
        trade = await o.db.fetchone("SELECT * FROM trades WHERE id = ?", (trade_id,))
        if not trade:
            raise HTTPException(404, "Trade non trouvé")
        return trade

    @router.get("/signals")
    async def get_signals() -> dict[str, Any]:
        o = _orch()
        signals = {}
        for pair in o.settings.pairs_list:
            price = o.data_collector.get_price(pair) if o.data_collector else 0
            ob = o.data_collector.get_orderbook(pair) if o.data_collector else {}
            signals[pair] = {"price": price, "orderbook": ob}
        return signals

    @router.get("/candles/{pair}")
    async def get_candles(pair: str, interval: str = "5m", limit: int = 200) -> list[dict[str, Any]]:
        o = _orch()
        return await o.db.fetchall(
            """SELECT open_time, open, high, low, close, volume
               FROM candles WHERE pair = ? AND interval = ?
               ORDER BY open_time DESC LIMIT ?""",
            (pair.upper(), interval, limit),
        )

    @router.get("/memory")
    async def get_memory() -> dict[str, Any]:
        o = _orch()
        entries = await o.memory.get_all_active()
        context = await o.memory.get_context()
        return {"entries": entries, "context": context}

    @router.get("/agents/status")
    async def get_agents_status() -> dict[str, Any]:
        o = _orch()
        # Dernier log de chaque agent
        agents = {}
        for agent_name in ["market_analyst", "decision_agent", "risk_evaluator", "post_trade_learner"]:
            last_log = await o.db.fetchone(
                """SELECT timestamp, action, response_received, tokens_used, cost_usd, duration_ms
                   FROM agent_logs WHERE agent = ? ORDER BY id DESC LIMIT 1""",
                (agent_name,),
            )
            agents[agent_name] = {
                "last_activity": last_log if last_log else None,
            }
        agents["data_collector"] = {
            "state": o.data_collector.state.value if o.data_collector else "unknown",
            "pairs": o.settings.pairs_list,
        }
        agents["risk_guard"] = {
            "kill_switch": o.risk_guard.kill_status if o.risk_guard else {},
        }
        return agents

    @router.get("/agents/costs")
    async def get_agents_costs() -> dict[str, Any]:
        o = _orch()
        rows = await o.db.fetchall(
            "SELECT agent, COUNT(*) as calls, SUM(cost_usd) as total_cost, SUM(tokens_used) as total_tokens FROM agent_logs GROUP BY agent"
        )
        costs = {r["agent"]: {"calls": r["calls"], "cost_usd": r["total_cost"], "tokens": r["total_tokens"]} for r in rows}
        costs["_total"] = o.claude.total_cost if o.claude else 0
        return costs

    @router.post("/kill-switch")
    async def activate_kill_switch() -> dict[str, str]:
        o = _orch()
        o.risk_guard._total_kill = True
        logger.warning("KILL SWITCH activé via API")
        return {"status": "kill_switch_activated"}

    @router.post("/resume")
    async def resume() -> dict[str, str]:
        o = _orch()
        o.risk_guard.reset_daily_kill()
        o.risk_guard.reset_total_kill()
        logger.info("Trading repris via API")
        return {"status": "resumed"}

    @router.get("/config")
    async def get_config() -> dict[str, Any]:
        o = _orch()
        s = o.settings
        return {
            "pairs": s.pairs_list,
            "candle_intervals": s.candle_intervals_list,
            "trading_mode": s.TRADING_MODE,
            "initial_capital": s.INITIAL_CAPITAL,
            "signal_threshold": s.SIGNAL_THRESHOLD,
            "max_position_pct": s.MAX_POSITION_PCT,
            "stop_loss_atr_mult": s.STOP_LOSS_ATR_MULT,
            "take_profit_atr_mult": s.TAKE_PROFIT_ATR_MULT,
            "trailing_stop_atr_mult": s.TRAILING_STOP_ATR_MULT,
            "max_open_positions": s.MAX_OPEN_POSITIONS,
            "max_daily_loss_pct": s.MAX_DAILY_LOSS_PCT,
            "max_total_drawdown_pct": s.MAX_TOTAL_DRAWDOWN_PCT,
            "ai_model_fast": s.AI_MODEL_FAST,
            "ai_model_deep": s.AI_MODEL_DEEP,
            "testnet": s.BINANCE_TESTNET,
        }

    return router
