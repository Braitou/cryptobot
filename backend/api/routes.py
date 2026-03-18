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
        # Dernier log de chaque agent v4
        agents = {}
        for agent_name in ["regime_advisor", "post_trade_logger"]:
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
        agents["regime_detector"] = {
            "regime": o.regime_detector.current_regime if o.regime_detector else "UNKNOWN",
            "info": o.regime_detector.regime_info if o.regime_detector else {},
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
        """Retourne la config v4 complète : config.json + preset actif + settings."""
        o = _orch()
        s = o.settings
        config_json = o.config_manager.config if o.config_manager else {}
        preset = o.config_manager.get_active_preset() if o.config_manager else {}
        regime = o.config_manager.get_active_regime() if o.config_manager else "RANGING"
        regime_info = o.regime_detector.regime_info if o.regime_detector else {}
        next_event = o.calendar_guard.get_next_event() if o.calendar_guard else None
        cal_mult = o.calendar_guard.get_current_multiplier() if o.calendar_guard else 1.0

        return {
            "config_json": config_json,
            "active_regime": regime,
            "active_preset": preset,
            "regime_info": regime_info,
            "calendar_multiplier": cal_mult,
            "next_calendar_event": next_event,
            "settings": {
                "pairs": s.pairs_list,
                "trading_mode": s.TRADING_MODE,
                "initial_capital": s.INITIAL_CAPITAL,
                "max_position_pct": s.MAX_POSITION_PCT,
                "max_open_positions": s.MAX_OPEN_POSITIONS,
                "max_daily_loss_pct": s.MAX_DAILY_LOSS_PCT,
                "max_total_drawdown_pct": s.MAX_TOTAL_DRAWDOWN_PCT,
                "testnet": s.BINANCE_TESTNET,
            },
        }

    @router.get("/signal_stats")
    async def get_signal_stats() -> dict[str, Any]:
        """Retourne les compteurs de signaux filtrés/exécutés aujourd'hui."""
        o = _orch()
        o._check_stats_reset()
        return o.signal_stats

    @router.get("/open_positions")
    async def get_open_positions() -> list[dict[str, Any]]:
        """Retourne les positions ouvertes avec prix actuel et P&L non réalisé."""
        o = _orch()
        trades = await o.db.fetchall("SELECT * FROM trades WHERE status = 'open'")
        positions = []
        for t in trades:
            trade = dict(t)
            pair = trade["pair"]
            try:
                current_price = await o.binance.get_price(pair)
            except Exception:
                current_price = trade["entry_price"]

            entry = trade["entry_price"]
            qty = trade["quantity"]
            if trade["side"] == "BUY":
                unrealized_pnl = (current_price - entry) * qty
                unrealized_pct = ((current_price - entry) / entry) * 100 if entry > 0 else 0
            else:
                unrealized_pnl = (entry - current_price) * qty
                unrealized_pct = ((entry - current_price) / entry) * 100 if entry > 0 else 0

            trade["current_price"] = current_price
            trade["unrealized_pnl"] = round(unrealized_pnl, 4)
            trade["unrealized_pct"] = round(unrealized_pct, 2)
            positions.append(trade)
        return positions

    @router.get("/guards")
    async def get_guards() -> dict[str, Any]:
        """Retourne l'état de tous les garde-fous."""
        o = _orch()
        portfolio = await o._get_portfolio_state()

        # Exposition corrélée
        open_trades = await o.db.fetchall("SELECT * FROM trades WHERE status = 'open'")
        long_exposure = sum(
            (t["entry_price"] or 0) * (t["quantity"] or 0)
            for t in open_trades if t["side"] == "BUY"
        )
        capital = portfolio["capital"]
        corr_pct = (long_exposure / capital * 100) if capital > 0 else 0

        return {
            "daily_loss_pct": abs(portfolio["daily_pnl_pct"]) * 100 if portfolio["daily_pnl_pct"] < 0 else 0,
            "daily_loss_max": o.settings.MAX_DAILY_LOSS_PCT * 100,
            "drawdown_pct": portfolio["drawdown_pct"] * 100,
            "drawdown_max": o.settings.MAX_TOTAL_DRAWDOWN_PCT * 100,
            "correlated_exposure_pct": round(corr_pct, 1),
            "correlated_exposure_max": 15.0,
            "open_positions": portfolio["open_positions"],
            "max_positions": o.settings.MAX_OPEN_POSITIONS,
            "kill_switch": o.risk_guard.kill_status if o.risk_guard else {},
            "calendar_multiplier": o.calendar_guard.get_current_multiplier() if o.calendar_guard else 1.0,
            "next_event": o.calendar_guard.get_next_event() if o.calendar_guard else None,
            "config_meta_updated": o.config_manager.config.get("_meta", {}).get("updated_at") if o.config_manager else None,
        }

    @router.get("/ai_feed")
    async def get_ai_feed(limit: int = 30) -> list[dict[str, Any]]:
        """Retourne les dernières décisions IA (Regime Advisor + Post-Trade Logger)."""
        o = _orch()
        return await o.db.fetchall(
            """SELECT timestamp, agent, action, response_received, cost_usd, data
               FROM agent_logs
               WHERE agent IN ('regime_advisor', 'post_trade_logger')
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        )

    @router.get("/feed")
    async def get_feed() -> list[dict[str, Any]]:
        """Retourne les 100 derniers events pour le Live Feed."""
        from backend.api.server import _ws_manager

        return _ws_manager.get_history()

    return router
