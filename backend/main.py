"""Orchestrateur principal v4 — relie tous les agents et dispatch les messages.

Architecture v4 :
- Exécution = 100% Python, déterministe, < 50ms
- IA = stratège asynchrone (Regime Advisor), ne bloque jamais l'exécution
- RegimeDetector (Python) détecte le régime toutes les 15 min sur candles 1H
- ConfigManager lit/écrit config.json avec le preset actif
- CalendarGuard pause automatiquement avant les événements macro
- CorrelationGuard limite l'exposition corrélée à 15% du capital
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.agents.ai_post_trade_logger import PostTradeLogger
from backend.agents.ai_regime_advisor import RegimeAdvisor
from backend.agents.base import AgentMessage
from backend.agents.calendar_guard import CalendarGuard
from backend.agents.correlation_guard import CorrelationGuard
from backend.agents.data_collector import DataCollector
from backend.agents.executor import OrderExecutor
from backend.agents.news_scraper import NewsScraper
from backend.agents.regime_detector import RegimeDetector
from backend.agents.risk_guard import RiskGuard
from backend.agents.signal_analyzer import SignalAnalyzer
from backend.config import Settings, get_settings
from backend.config_manager import ConfigManager
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
        self.risk_guard: RiskGuard | None = None
        self.executor: OrderExecutor | None = None

        # v4 — nouveaux composants
        self.config_manager: ConfigManager | None = None
        self.regime_detector: RegimeDetector | None = None
        self.calendar_guard: CalendarGuard | None = None
        self.correlation_guard: CorrelationGuard | None = None
        self.news_scraper: NewsScraper | None = None
        self.regime_advisor: RegimeAdvisor | None = None
        self.post_trade_logger: PostTradeLogger | None = None
        self._regime_task: asyncio.Task | None = None

        # Trigger urgence : prix BTC de la dernière vérification
        self._last_btc_price: float | None = None
        self._last_btc_check_time: datetime | None = None

        # Compteurs de signaux (reset à minuit UTC)
        self.signal_stats: dict[str, int] = self._empty_signal_stats()
        self._signal_stats_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _empty_signal_stats() -> dict[str, int]:
        return {
            "analyzed": 0,
            "filtered_atr_low": 0,
            "filtered_micro_trend": 0,
            "filtered_regime_off": 0,
            "blocked_calendar": 0,
            "blocked_correlation": 0,
            "blocked_risk_guard": 0,
            "executed": 0,
        }

    def _check_stats_reset(self) -> None:
        """Reset les compteurs à minuit UTC."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._signal_stats_date:
            self.signal_stats = self._empty_signal_stats()
            self._signal_stats_date = today

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

        # v4 — Config + Regime + Guards
        self.config_manager = ConfigManager()
        self.regime_detector = RegimeDetector()
        self.calendar_guard = CalendarGuard()
        self.correlation_guard = CorrelationGuard()

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
            max_open_positions=s.MAX_OPEN_POSITIONS,
            max_positions_per_pair=s.MAX_POSITIONS_PER_PAIR,
            max_daily_loss_pct=s.MAX_DAILY_LOSS_PCT,
            max_total_drawdown_pct=s.MAX_TOTAL_DRAWDOWN_PCT,
            scalp_max_sl_pct=s.SCALP_MAX_SL_PCT,
            scalp_max_tp_pct=s.SCALP_MAX_TP_PCT,
            momentum_max_sl_pct=s.MOMENTUM_MAX_SL_PCT,
            momentum_max_tp_pct=s.MOMENTUM_MAX_TP_PCT,
            trailing_stop_activation_pct=s.TRAILING_STOP_ACTIVATION_PCT,
            trailing_stop_distance_pct=s.TRAILING_STOP_DISTANCE_PCT,
            pair_cooldown_after_sl_minutes=s.PAIR_COOLDOWN_AFTER_SL_MINUTES,
            stop_loss_atr_mult=s.STOP_LOSS_ATR_MULT,
            take_profit_atr_mult=s.TAKE_PROFIT_ATR_MULT,
            trailing_stop_atr_mult=s.TRAILING_STOP_ATR_MULT,
        )
        self.executor = OrderExecutor(
            binance=self.binance, db=self.db,
            trading_mode=s.TRADING_MODE, bus=self.bus,
            risk_guard=self.risk_guard,
        )

        # News Scraper (Python pur)
        self.news_scraper = NewsScraper(self.db)

        # Agents IA v4
        model = s.AI_MODEL_FAST
        self.regime_advisor = RegimeAdvisor(
            self.claude, self.config_manager, self.db, model, self.bus,
        )
        self.post_trade_logger = PostTradeLogger(self.claude, self.db, model, self.bus)

        logger.info("Orchestrator v4 setup OK — mode {} / {} / régime {}",
                     s.TRADING_MODE,
                     "testnet" if s.BINANCE_TESTNET else "LIVE",
                     self.config_manager.get_active_regime())

    async def run(self) -> None:
        """Lance le data collector, l'executor monitor, le regime loop et le dispatcher."""
        self._running = True
        await self.data_collector.start()

        # Charger les candles 1H historiques via REST pour le RegimeDetector (ADX)
        # Le WebSocket ne couvre que 1m/5m/15m — sans cet appel, le RegimeDetector
        # n'a aucune donnée 1H et ne peut pas calculer l'ADX.
        await self.data_collector.load_historical_candles("BTCUSDT", "1h", limit=200)

        await self.executor.start()
        await self.news_scraper.start()
        self._regime_task = asyncio.create_task(self._regime_loop())

        logger.info("Orchestrator v4 running — dispatcher en écoute sur le bus")
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
        if self._regime_task and not self._regime_task.done():
            self._regime_task.cancel()
        if self.news_scraper:
            await self.news_scraper.stop()
        if self.data_collector:
            await self.data_collector.stop()
        if self.executor:
            await self.executor.stop()
        if self.binance:
            await self.binance.close()
        if self.db:
            await self.db.close()
        logger.info("Orchestrator arrêté")

    # ─── Regime Loop (5min ticks, 15min regime, 1h advisor) ─────────

    REGIME_INTERVAL_TICKS = 3      # 3 × 5min = 15min → RegimeDetector
    ADVISOR_INTERVAL_TICKS = 12    # 12 × 5min = 60min → Regime Advisor IA
    EMERGENCY_PRICE_CHANGE_PCT = 3.0  # > 3% en 30min → appel urgence IA

    async def _regime_loop(self) -> None:
        """Tourne toutes les 5 min. Sous-tâches à intervalles différents :
        - Toutes les 5 min : vérifier trigger urgence (prix BTC)
        - Toutes les 15 min : RegimeDetector (ADX sur candles 1H)
        - Toutes les 60 min : Regime Advisor IA (Haiku)
        """
        # Laisser le data collector se remplir
        await asyncio.sleep(30)

        tick_count = 0

        while True:
            try:
                tick_count += 1

                # ── Toutes les 5 min : vérifier trigger urgence prix BTC ──
                await self._check_emergency_trigger()

                # ── Toutes les 15 min : RegimeDetector Python ──
                if tick_count % self.REGIME_INTERVAL_TICKS == 0:
                    await self._run_regime_detection()

                # ── Toutes les 60 min : Regime Advisor IA ──
                if tick_count % self.ADVISOR_INTERVAL_TICKS == 0:
                    await self._run_regime_advisor("scheduled")

                # ── Toujours : mettre à jour le calendrier ──
                cal_mult = self.calendar_guard.get_current_multiplier()
                self.config_manager.update_calendar_multiplier(cal_mult)

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("RegimeLoop erreur: {}", e)

            await asyncio.sleep(300)  # 5 minutes

    async def _run_regime_detection(self) -> None:
        """Détecte le régime via ADX sur candles 1H BTCUSDT."""
        df_1h = await self.data_collector.get_recent_candles("BTCUSDT", "1h", limit=200)
        if df_1h.empty or len(df_1h) < 30:
            logger.debug("RegimeDetect: pas assez de candles 1H ({} dispo)",
                         len(df_1h) if not df_1h.empty else 0)
            return

        old_regime = self.regime_detector.current_regime
        new_regime = self.regime_detector.detect(df_1h)

        if new_regime != old_regime:
            self.config_manager.update_regime(
                regime=new_regime,
                source="python_adx",
                reason=f"ADX regime change: {old_regime} -> {new_regime}",
            )
            await self._broadcast_ws(AgentMessage(
                type="regime_change",
                data={"old": old_regime, "new": new_regime},
                source="regime_detector",
            ))

    async def _check_emergency_trigger(self) -> None:
        """Vérifie si le prix BTC a bougé > 3% depuis la dernière vérification (5min).

        Si oui → appel urgence du Regime Advisor.
        """
        try:
            current_price = await self.binance.get_price("BTCUSDT")
        except Exception:
            return

        now = datetime.now(timezone.utc)

        if self._last_btc_price is not None and self._last_btc_check_time is not None:
            elapsed_min = (now - self._last_btc_check_time).total_seconds() / 60

            # Comparer sur les 30 dernières minutes max
            if elapsed_min <= 35:
                change_pct = abs(current_price - self._last_btc_price) / self._last_btc_price * 100
                if change_pct >= self.EMERGENCY_PRICE_CHANGE_PCT:
                    logger.warning(
                        "URGENCE: BTC {:.2f}% en {:.0f}min ({:.0f} → {:.0f}) — appel Regime Advisor",
                        change_pct, elapsed_min, self._last_btc_price, current_price,
                    )
                    await self._run_regime_advisor(f"emergency_price_move_{change_pct:.1f}pct")

        self._last_btc_price = current_price
        self._last_btc_check_time = now

    async def _run_regime_advisor(self, trigger_reason: str) -> None:
        """Appelle le Regime Advisor Haiku."""
        try:
            portfolio = await self._get_portfolio_state()
            news_summary = self.news_scraper.get_summary_for_advisor()
            regime = self.config_manager.get_active_regime()
            regime_info = self.regime_detector.regime_info

            await self.regime_advisor.advise(
                current_regime=regime,
                regime_info=regime_info,
                news_summary=news_summary,
                portfolio=portfolio,
                trigger_reason=trigger_reason,
            )

            # Recharger la config après l'écriture éventuelle par le Regime Advisor
            self.config_manager.reload()

        except Exception as e:
            import traceback
            logger.error("RegimeAdvisor erreur: {}\n{}", e, traceback.format_exc())

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
        """Candle fermée → calcul signal avec le preset actif."""
        pair = msg.data.get("pair", "")
        interval = msg.data.get("interval", "")

        # On analyse uniquement sur 5m pour déclencher les signaux
        if interval != "5m":
            return

        df = await self.data_collector.get_recent_candles(pair, interval, limit=100)
        if df.empty or len(df) < 30:
            return

        orderbook = self.data_collector.get_orderbook(pair)
        preset = self.config_manager.get_active_preset()
        await self.signal_analyzer.analyze(pair, df, orderbook, preset=preset)

    async def _on_signal(self, msg: AgentMessage) -> None:
        """Signal détecté → guards → SCALP direct Python OU MOMENTUM (reporté)."""
        pair = msg.data.get("pair", "")
        score = msg.data.get("score", 0)
        indicators = msg.data.get("indicators", {})

        self._check_stats_reset()
        self.signal_stats["analyzed"] += 1

        # Kill switch
        if self.risk_guard.is_killed:
            logger.warning("Signal {} ignoré — kill switch actif", pair)
            return

        # Trading activé ?
        if not self.config_manager.is_trading_enabled():
            logger.info("Signal {} ignoré — trading désactivé dans config.json", pair)
            return

        # Nettoyer les cooldowns expirés
        self.risk_guard.clear_expired_cooldowns()

        # Recharger le preset actif
        preset = self.config_manager.get_active_preset()
        regime = self.config_manager.get_active_regime()

        # Classifier le signal avec le preset
        signal_classification = self.signal_analyzer.classify_signal(pair, indicators, score, preset)
        mode = signal_classification["mode"]

        if mode == "NO_SIGNAL":
            # Déterminer la raison du filtrage pour les stats
            atr_pct = indicators.get("atr_14", 0) / indicators.get("price", 1) if indicators.get("price", 0) > 0 else 0
            if atr_pct < self.signal_analyzer.MIN_ATR_PCT:
                self.signal_stats["filtered_atr_low"] += 1
            else:
                self.signal_stats["filtered_regime_off"] += 1
            return

        if mode.startswith("SCALP_"):
            await self._handle_scalp(pair, mode, indicators, score, signal_classification, regime)
        elif mode.startswith("MOMENTUM_"):
            # v4 : momentum reporté — pas d'appel IA décisionnel pour l'instant
            self.signal_stats["filtered_regime_off"] += 1
            logger.info("MOMENTUM {} score={:.3f} — reporté (v4: pas d'IA décisionnelle)", pair, score)

    # ─── SCALP : exécution directe Python (pas d'appel IA) ──────────

    async def _handle_scalp(
        self, pair: str, mode: str, indicators: dict, score: float,
        signal: dict, regime: str,
    ) -> None:
        """Scalp = décision purement Python → Guards → Risk Guard → Executor."""
        price = indicators.get("price", 0)
        portfolio = await self._get_portfolio_state()

        if mode == "SCALP_LONG":
            action = "BUY"
            # SL/TP en ratio décimal (ex: 0.008 = 0.8%) — retourné par calculate_trade_levels()
            sl_pct = signal["stop_loss_pct"]
            tp_pct = signal["take_profit_pct"]
            pos_pct = signal["position_size_pct"] / 100  # 5.0% → 0.05

            # Appliquer les multiplicateurs (calendar + config global)
            cal_mult = self.calendar_guard.get_current_multiplier()
            config_mult = self.config_manager.get_position_multiplier()
            effective_mult = cal_mult * config_mult

            if effective_mult <= 0:
                self.signal_stats["blocked_calendar"] += 1
                logger.info("SCALP {} bloqué — multiplicateur = 0 (calendar={:.2f} config={:.2f})",
                             pair, cal_mult, config_mult)
                return

            pos_pct *= effective_mult

            # SL/TP en prix absolu (sl_pct et tp_pct sont déjà des ratios décimaux)
            stop_loss = round(price * (1 - sl_pct), 2)
            take_profit = round(price * (1 + tp_pct), 2)

            reasoning = (
                f"Scalp auto [{regime}]: RSI9={indicators['rsi_9']:.1f}, "
                f"BB%={indicators['bb_pct']:.2f}, Vol={indicators['volume_ratio']:.1f}x, "
                f"ATR={indicators['atr_14']:.2f}, mult={effective_mult:.2f}"
            )

            logger.info("SCALP_AUTO {} — {} @ {:.2f} (RSI9={:.0f} BB%={:.2f} regime={} mult={:.2f})",
                         pair, action, price, indicators["rsi_9"], indicators["bb_pct"],
                         regime, effective_mult)

        elif mode == "SCALP_SHORT_EXIT":
            # Vendre si on a une position ouverte sur cette paire
            open_trade = await self.db.fetchone(
                "SELECT * FROM trades WHERE pair = ? AND status = 'open' AND side = 'BUY'",
                (pair,),
            )
            if open_trade:
                logger.info("SCALP_EXIT {} — fermeture position ouverte (RSI9={:.0f})",
                             pair, indicators["rsi_9"])
                await self.executor._close_position(
                    dict(open_trade), price, "closed_scalp_exit"
                )
            return
        else:
            return

        # CorrelationGuard — vérifier l'exposition corrélée
        open_trades = await self.db.fetchall("SELECT * FROM trades WHERE status = 'open'")
        corr_ok, corr_reason = self.correlation_guard.check(
            [dict(t) for t in open_trades], portfolio["capital"]
        )
        if not corr_ok:
            self.signal_stats["blocked_correlation"] += 1
            logger.warning("CorrelationGuard SCALP {} : REJETÉ — {}", pair, corr_reason)
            return

        # Risk Guard
        pair_open = await self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM trades WHERE pair = ? AND status = 'open'",
            (pair,),
        )
        portfolio["pair_positions"] = pair_open["cnt"] if pair_open else 0

        guard_decision = {
            "pair": pair,
            "action": action,
            "position_size_pct": pos_pct,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "quantity": self.risk_guard.compute_quantity(portfolio["capital"], pos_pct, price),
            "entry_price": price,
        }

        check = self.risk_guard.check(guard_decision, portfolio)
        if not check.approved:
            self.signal_stats["blocked_risk_guard"] += 1
            logger.warning("RiskGuard SCALP {} : REJETÉ — {}", pair, check.reason)
            return

        self.signal_stats["executed"] += 1

        # Executor
        exec_decision = {
            "pair": pair,
            "action": action,
            "quantity": guard_decision["quantity"],
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "signal_score": score,
            "decision_reasoning": reasoning,
            "indicators_snapshot": indicators,
            "max_hold_minutes": signal.get("max_hold_minutes", 30),
            "trade_mode": f"SCALP_AUTO_{regime}",
        }
        await self.executor.execute(exec_decision)

    # ─── Post-Trade ──────────────────────────────────────────────────

    async def _on_order_closed(self, msg: AgentMessage) -> None:
        """Trade fermé → Post-Trade Logger (tags numériques, pas de narrative)."""
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

        # Régime au moment de la clôture
        regime = self.config_manager.get_active_regime()

        # Post-Trade Logger v4 : tags numériques dans trade_tags
        await self.post_trade_logger.analyze(
            trade=trade_dict,
            indicators_at_entry=indicators_snapshot,
            indicators_at_exit=indicators_snapshot,
            regime=regime,
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
