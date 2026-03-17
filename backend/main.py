"""Orchestrateur principal — relie tous les agents et dispatch les messages."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.agents.ai_decision import DecisionAgent
from backend.agents.ai_market_analyst import MarketAnalystAgent
from backend.agents.ai_post_trade import PostTradeAgent
from backend.agents.ai_risk_evaluator import RiskEvaluatorAgent
from backend.agents.base import AgentMessage
from backend.agents.data_collector import DataCollector
from backend.agents.executor import OrderExecutor
from backend.agents.risk_guard import RiskGuard
from backend.agents.signal_analyzer import SignalAnalyzer
from backend.config import Settings, get_settings
from backend.memory.manager import MemoryManager
from backend.storage.database import Database
from backend.utils.binance_client import BinanceClient
from backend.utils.claude_client import ClaudeClient
from backend.utils.logger import logger


class Orchestrator:
    """Point d'entrée — instancie tout et route les messages."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bus: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._running = False

        # Initialisés dans setup()
        self.db: Database | None = None
        self.binance: BinanceClient | None = None
        self.claude: ClaudeClient | None = None
        self.memory: MemoryManager | None = None
        self.data_collector: DataCollector | None = None
        self.signal_analyzer: SignalAnalyzer | None = None
        self.market_analyst: MarketAnalystAgent | None = None
        self.decision_agent: DecisionAgent | None = None
        self.risk_evaluator: RiskEvaluatorAgent | None = None
        self.post_trade: PostTradeAgent | None = None
        self.risk_guard: RiskGuard | None = None
        self.executor: OrderExecutor | None = None

        # WebSocket broadcast callback (set by API server)
        self._ws_broadcast: Any = None

    async def setup(self) -> None:
        """Initialise toutes les dépendances et agents."""
        s = self.settings

        # Infrastructure
        self.db = Database()
        await self.db.connect()

        self.binance = BinanceClient(s.BINANCE_API_KEY, s.BINANCE_API_SECRET, s.BINANCE_TESTNET)
        await self.binance.connect()

        self.claude = ClaudeClient(api_key=s.ANTHROPIC_API_KEY, default_max_tokens=s.AI_MAX_TOKENS)
        self.memory = MemoryManager(self.db)

        # Agents Python
        self.data_collector = DataCollector(
            binance=self.binance, db=self.db,
            pairs=s.pairs_list, intervals=s.candle_intervals_list,
            bus=self.bus,
        )
        self.signal_analyzer = SignalAnalyzer(
            signal_threshold=s.SIGNAL_THRESHOLD, bus=self.bus,
        )
        self.risk_guard = RiskGuard(
            max_position_pct=s.MAX_POSITION_PCT,
            stop_loss_atr_mult=s.STOP_LOSS_ATR_MULT,
            take_profit_atr_mult=s.TAKE_PROFIT_ATR_MULT,
            trailing_stop_atr_mult=s.TRAILING_STOP_ATR_MULT,
            max_open_positions=s.MAX_OPEN_POSITIONS,
            max_positions_per_pair=s.MAX_POSITIONS_PER_PAIR,
            max_daily_loss_pct=s.MAX_DAILY_LOSS_PCT,
            max_total_drawdown_pct=s.MAX_TOTAL_DRAWDOWN_PCT,
        )
        self.executor = OrderExecutor(
            binance=self.binance, db=self.db,
            trading_mode=s.TRADING_MODE, bus=self.bus,
        )

        # Agents IA
        model = s.AI_MODEL_FAST
        self.market_analyst = MarketAnalystAgent(self.claude, self.memory, self.db, model, self.bus)
        self.decision_agent = DecisionAgent(self.claude, self.memory, self.db, model, self.bus)
        self.risk_evaluator = RiskEvaluatorAgent(self.claude, self.memory, self.db, model, self.bus)
        self.post_trade = PostTradeAgent(self.claude, self.memory, self.db, model, self.bus)

        logger.info("Orchestrator setup OK — mode {} / {}", s.TRADING_MODE, "testnet" if s.BINANCE_TESTNET else "LIVE")

    async def run(self) -> None:
        """Lance le data collector, l'executor monitor et le dispatcher."""
        self._running = True
        await self.data_collector.start()
        await self.executor.start()

        logger.info("Orchestrator running — dispatcher en écoute sur le bus")
        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(self.bus.get(), timeout=1.0)
                    await self._dispatch(msg)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Arrêt propre."""
        self._running = False
        logger.info("Orchestrator shutdown...")
        if self.data_collector:
            await self.data_collector.stop()
        if self.executor:
            await self.executor.stop()
        if self.binance:
            await self.binance.close()
        if self.db:
            await self.db.close()
        logger.info("Orchestrator arrêté")

    # ─── Dispatcher ───────────────────────────────────────────────────

    async def _dispatch(self, msg: AgentMessage) -> None:
        """Route un message vers le bon handler."""
        try:
            if msg.type == "candle_closed":
                await self._on_candle_closed(msg)
            elif msg.type == "signal":
                await self._on_signal(msg)
            elif msg.type == "order_closed":
                await self._on_order_closed(msg)
            # Broadcast tous les messages au WebSocket
            await self._broadcast_ws(msg)
        except Exception as e:
            logger.error("Dispatch erreur sur {}: {}", msg.type, e)

    async def _on_candle_closed(self, msg: AgentMessage) -> None:
        """Candle fermée → calcul signal."""
        pair = msg.data.get("pair", "")
        interval = msg.data.get("interval", "")

        # On analyse uniquement sur 5m pour déclencher les signaux
        if interval != "5m":
            return

        df = await self.data_collector.get_recent_candles(pair, interval, limit=100)
        if df.empty or len(df) < 30:
            return

        orderbook = self.data_collector.get_orderbook(pair)
        await self.signal_analyzer.analyze(pair, df, orderbook)

    async def _on_signal(self, msg: AgentMessage) -> None:
        """Signal fort détecté → chaîne IA complète."""
        pair = msg.data.get("pair", "")
        score = msg.data.get("score", 0)
        indicators = msg.data.get("indicators", {})
        orderbook = msg.data.get("orderbook", {})

        if self.risk_guard.is_killed:
            logger.warning("Signal {} ignoré — kill switch actif", pair)
            return

        logger.info("Signal {} score={:.3f} — lancement chaîne IA", pair, score)

        # Broadcast "thinking" au dashboard
        await self._broadcast_ws(AgentMessage(
            type="thinking", data={"agent": "market_analyst", "status": "reasoning", "pair": pair},
            source="orchestrator",
        ))

        # 1. Market Analyst
        analysis = await self.market_analyst.analyze(pair, indicators, orderbook)
        if analysis is None:
            return

        # 2. Decision Agent
        await self._broadcast_ws(AgentMessage(
            type="thinking", data={"agent": "decision", "status": "reasoning", "pair": pair},
            source="orchestrator",
        ))
        portfolio = await self._get_portfolio_state()
        decision = await self.decision_agent.decide(pair, score, analysis, indicators, portfolio)
        if decision is None:
            return

        if decision.action == "WAIT":
            logger.info("Decision {} : WAIT — aucune action", pair)
            return

        # 3. Risk Evaluator
        await self._broadcast_ws(AgentMessage(
            type="thinking", data={"agent": "risk_evaluator", "status": "reasoning", "pair": pair},
            source="orchestrator",
        ))
        verdict = await self.risk_evaluator.evaluate(pair, decision, analysis, indicators, portfolio)
        if verdict is None or verdict.verdict == "REJECT":
            logger.info("RiskEvaluator {} : REJECT — trade annulé", pair)
            return

        # Appliquer l'ajustement de position
        final_pct = verdict.adjusted_position_pct
        atr = indicators.get("atr_14", 300)
        price = indicators.get("price", 0)

        # 4. Risk Guard (Python, inviolable)
        # Compter les positions ouvertes sur cette paire
        pair_open = await self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM trades WHERE pair = ? AND status = 'open'",
            (pair,),
        )
        portfolio["pair_positions"] = pair_open["cnt"] if pair_open else 0

        guard_decision = {
            "pair": pair,
            "action": decision.action,
            "position_size_pct": final_pct,
            "stop_loss": self.risk_guard.compute_stop_loss(price, decision.action, atr),
            "take_profit": self.risk_guard.compute_take_profit(price, decision.action, atr),
            "quantity": self.risk_guard.compute_quantity(portfolio["capital"], final_pct, price),
            "entry_price": price,
        }

        check = self.risk_guard.check(guard_decision, portfolio)
        if not check.approved:
            logger.warning("RiskGuard {} : REJETÉ — {}", pair, check.reason)
            return

        # 5. Executor
        exec_decision = {
            "pair": pair,
            "action": decision.action,
            "quantity": guard_decision["quantity"],
            "stop_loss": guard_decision["stop_loss"],
            "take_profit": guard_decision["take_profit"],
            "signal_score": score,
            "market_analysis": analysis.summary,
            "decision_reasoning": decision.reasoning,
            "risk_evaluation": verdict.reasoning,
            "indicators_snapshot": indicators,
        }
        await self.executor.execute(exec_decision)

    async def _on_order_closed(self, msg: AgentMessage) -> None:
        """Trade fermé → Post-Trade Learner."""
        trade_id = msg.data.get("trade_id")
        if not trade_id:
            return

        trade = await self.db.fetchone("SELECT * FROM trades WHERE id = ?", (trade_id,))
        if not trade:
            return

        # Indicateurs approximatifs (on prend les derniers disponibles)
        indicators_snapshot = {}
        raw = trade.get("indicators_snapshot", "{}")
        if raw:
            try:
                indicators_snapshot = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                pass

        # Calculer duration_minutes à partir de entry_time et exit_time
        trade_dict = dict(trade)
        try:
            entry_dt = datetime.fromisoformat(trade_dict["entry_time"])
            exit_dt = datetime.fromisoformat(trade_dict["exit_time"])
            trade_dict["duration_minutes"] = round((exit_dt - entry_dt).total_seconds() / 60, 1)
        except (KeyError, TypeError, ValueError):
            trade_dict["duration_minutes"] = 0

        # Indicateurs de sortie = approximation avec les derniers
        await self.post_trade.analyze(
            trade=trade_dict,
            indicators_at_entry=indicators_snapshot,
            indicators_at_exit=indicators_snapshot,
        )

    # ─── Helpers ──────────────────────────────────────────────────────

    async def _get_portfolio_state(self) -> dict[str, Any]:
        """Calcule l'état actuel du portefeuille."""
        s = self.settings
        open_trades = await self.db.fetchall("SELECT * FROM trades WHERE status = 'open'")
        closed_today = await self.db.fetchall(
            "SELECT pnl FROM trades WHERE status != 'open' AND exit_time >= date('now')"
        )

        daily_pnl = sum(t["pnl"] or 0 for t in closed_today)
        total_closed = await self.db.fetchall(
            "SELECT pnl FROM trades WHERE status != 'open'"
        )
        total_pnl = sum(t["pnl"] or 0 for t in total_closed)
        capital = s.INITIAL_CAPITAL + total_pnl
        drawdown_pct = abs(min(0, total_pnl)) / s.INITIAL_CAPITAL if s.INITIAL_CAPITAL > 0 else 0

        return {
            "capital": capital,
            "open_positions": len(open_trades),
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pnl / s.INITIAL_CAPITAL if s.INITIAL_CAPITAL > 0 else 0,
            "drawdown_pct": drawdown_pct,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl / s.INITIAL_CAPITAL * 100 if s.INITIAL_CAPITAL > 0 else 0,
        }

    async def _broadcast_ws(self, msg: AgentMessage) -> None:
        """Envoie un message à tous les clients WebSocket connectés."""
        if self._ws_broadcast:
            await self._ws_broadcast(msg)


async def run_bot() -> None:
    """Point d'entrée principal du bot (sans API)."""
    settings = get_settings()
    orchestrator = Orchestrator(settings)
    await orchestrator.setup()
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(run_bot())
