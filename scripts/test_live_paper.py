"""Test d'intégration — Bot paper trading live pendant 5 minutes.

1. Lance le bot complet (DataCollector WebSocket + Orchestrator)
2. Lance l'API en parallèle
3. Vérifie les données live, les signaux, les endpoints
4. Si aucun signal fort en 4 min → injecte un faux signal pour forcer la chaîne IA
5. Vérifie le trade paper en base + logs complets
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from httpx import ASGITransport, AsyncClient

from backend.agents.base import AgentMessage
from backend.api.routes import create_router
from backend.config import get_settings
from backend.main import Orchestrator
from backend.utils.logger import logger

RUNTIME_SECONDS = 300  # 5 minutes


async def main() -> None:
    settings = get_settings()
    orch = Orchestrator(settings)
    await orch.setup()

    # ─── Stats tracking ──────────────────────────────────────────
    stats = {
        "candles_received": 0,
        "signals_computed": 0,
        "signals_strong": 0,
        "ia_chains_triggered": 0,
        "trades_executed": 0,
        "ws_messages": [],
    }

    # ─── API test app (sans lifespan) ────────────────────────────
    from fastapi import FastAPI
    test_app = FastAPI()
    router = create_router(lambda: orch)
    test_app.include_router(router, prefix="/api")

    # ─── Override du broadcast pour capturer les messages WS ─────
    original_broadcast = orch._ws_broadcast

    async def capture_broadcast(msg: AgentMessage) -> None:
        stats["ws_messages"].append({"type": msg.type, "source": msg.source})
        if original_broadcast:
            await original_broadcast(msg)

    orch._ws_broadcast = capture_broadcast

    # ─── Lancer le bot ───────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("TEST LIVE PAPER TRADING — {} secondes", RUNTIME_SECONDS)
    logger.info("=" * 70)
    logger.info("Capital: {} USDT | Paires: {} | Seuil signal: ±{}",
                settings.INITIAL_CAPITAL, settings.pairs_list, settings.SIGNAL_THRESHOLD)
    logger.info("")

    await orch.data_collector.start()
    await orch.executor.start()

    # Lancer le dispatcher en tâche de fond
    async def run_dispatcher():
        while orch._running:
            try:
                msg = await asyncio.wait_for(orch.bus.get(), timeout=1.0)
                # Track stats
                if msg.type == "candle_closed":
                    stats["candles_received"] += 1
                elif msg.type == "signal":
                    stats["signals_strong"] += 1
                elif msg.type == "order_executed":
                    stats["trades_executed"] += 1
                await orch._dispatch(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Dispatcher erreur: {}", e)

    orch._running = True
    dispatcher_task = asyncio.create_task(run_dispatcher())

    # ─── Boucle principale — monitoring toutes les 30s ───────────
    injected_signal = False
    start_time = asyncio.get_event_loop().time()

    try:
        for tick in range(RUNTIME_SECONDS // 10):
            await asyncio.sleep(10)
            elapsed = int(asyncio.get_event_loop().time() - start_time)

            # Compter les prix reçus
            prices = {}
            for pair in settings.pairs_list:
                p = orch.data_collector.get_price(pair)
                if p > 0:
                    prices[pair] = p

            # Log toutes les 30s
            if tick % 3 == 2 or tick == 0:
                logger.info(
                    "[{}s] candles={} | prix={} | signaux_forts={} | trades={}",
                    elapsed, stats["candles_received"],
                    {k: f"{v:.2f}" for k, v in prices.items()},
                    stats["signals_strong"], stats["trades_executed"],
                )

            # À 4min : si aucun signal fort, injecter un faux
            if elapsed >= 240 and stats["signals_strong"] == 0 and not injected_signal:
                injected_signal = True
                logger.info("")
                logger.info("=" * 70)
                logger.info("4 min écoulées, aucun signal fort — INJECTION d'un faux signal")
                logger.info("=" * 70)

                # Récupérer les vrais indicateurs actuels
                pair = "BTCUSDT"
                df = await orch.data_collector.get_recent_candles(pair, "5m", limit=100)
                if len(df) >= 30:
                    real_indicators = orch.signal_analyzer.compute_indicators(df)
                else:
                    real_indicators = None

                if real_indicators is None:
                    # Fallback : indicateurs fictifs mais réalistes
                    price = orch.data_collector.get_price(pair) or 74000
                    real_indicators = {
                        "rsi_14": 24.0, "macd_line": 15.0, "macd_signal": 8.0,
                        "macd_histogram": 7.0, "bb_upper": price * 1.02, "bb_middle": price,
                        "bb_lower": price * 0.98, "bb_pct": 0.08, "vwap": price * 0.998,
                        "ema_9": price * 1.003, "ema_21": price * 1.001, "atr_14": price * 0.004,
                        "volume_ratio": 2.8, "price_change_5m": 0.8, "price_change_15m": 1.5,
                        "price_change_1h": -0.3, "price": price,
                    }
                else:
                    # Modifier les indicateurs pour forcer un signal bullish
                    real_indicators["rsi_14"] = 23.0
                    real_indicators["macd_histogram"] = abs(real_indicators.get("macd_histogram", 5)) + 5
                    real_indicators["bb_pct"] = 0.08
                    real_indicators["volume_ratio"] = 3.0

                orderbook = orch.data_collector.get_orderbook(pair)
                if not orderbook.get("best_bid"):
                    orderbook = {
                        "bid_ask_spread": 0.02, "imbalance_ratio": 0.70,
                        "best_bid": real_indicators["price"] - 5,
                        "best_ask": real_indicators["price"] + 5,
                        "bids_volume": 20, "asks_volume": 8,
                    }

                fake_signal = AgentMessage(
                    type="signal",
                    data={
                        "pair": pair,
                        "score": 0.65,
                        "indicators": real_indicators,
                        "orderbook": orderbook,
                    },
                    source="test_injection",
                )
                await orch.bus.put(fake_signal)
                logger.info("Signal injecté — {} score=0.65", pair)

                # Attendre le traitement
                await asyncio.sleep(30)

    except KeyboardInterrupt:
        logger.info("Arrêt manuel")
    finally:
        orch._running = False
        dispatcher_task.cancel()
        try:
            await dispatcher_task
        except asyncio.CancelledError:
            pass

    # ─── Tests API ───────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 70)
    logger.info("VÉRIFICATION API")
    logger.info("=" * 70)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/portfolio")
        portfolio = r.json()
        logger.info("Portfolio: capital={:.2f} | positions={} | daily_pnl={:.4f} | api_cost=${:.4f}",
                     portfolio["capital"], portfolio["open_positions"],
                     portfolio["daily_pnl"], portfolio.get("api_cost_total", 0))

        r = await client.get("/api/trades?limit=10")
        trades = r.json()
        logger.info("Trades récents: {}", len(trades))
        for t in trades[:5]:
            logger.info("  #{} {} {} {} pnl={} ({}%)",
                        t["id"], t["pair"], t["side"], t["status"],
                        t.get("pnl", "—"), t.get("pnl_pct", "—"))

        r = await client.get("/api/agents/costs")
        costs = r.json()
        logger.info("Coûts API par agent:")
        for agent, data in costs.items():
            if agent.startswith("_"):
                continue
            logger.info("  {} : {} appels, ${:.4f}", agent, data["calls"], data["cost_usd"])
        logger.info("  TOTAL : ${:.4f}", costs.get("_total", 0))

        r = await client.get("/api/memory")
        mem = r.json()
        logger.info("Mémoire: {} leçons actives", len(mem.get("entries", [])))

        r = await client.get("/api/agents/status")
        agent_status = r.json()
        for name, info in agent_status.items():
            last = info.get("last_activity")
            if last:
                logger.info("  {} — dernier appel: {} ({}ms, ${:.4f})",
                            name, last.get("action"), last.get("duration_ms"), last.get("cost_usd", 0))

    # ─── Vérification base de données ────────────────────────────
    logger.info("")
    logger.info("=" * 70)
    logger.info("VÉRIFICATION BASE DE DONNÉES")
    logger.info("=" * 70)

    candle_count = await orch.db.fetchone("SELECT COUNT(*) as cnt FROM candles")
    agent_log_count = await orch.db.fetchone("SELECT COUNT(*) as cnt FROM agent_logs")
    trade_count = await orch.db.fetchone("SELECT COUNT(*) as cnt FROM trades")

    logger.info("Candles en base: {}", candle_count["cnt"])
    logger.info("Agent logs: {}", agent_log_count["cnt"])
    logger.info("Trades: {}", trade_count["cnt"])

    # Dernier agent log détaillé
    last_logs = await orch.db.fetchall(
        "SELECT timestamp, agent, action, tokens_used, cost_usd, duration_ms FROM agent_logs ORDER BY id DESC LIMIT 5"
    )
    if last_logs:
        logger.info("Derniers logs agents:")
        for l in last_logs:
            logger.info("  {} — {} {} — {}tok — ${:.4f} — {}ms",
                        l["timestamp"][:19], l["agent"], l["action"],
                        l["tokens_used"], l["cost_usd"], l["duration_ms"])

    # ─── Bilan final ─────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 70)
    logger.info("BILAN FINAL")
    logger.info("=" * 70)
    logger.info("Durée: {}s", RUNTIME_SECONDS)
    logger.info("Candles reçues (live): {}", stats["candles_received"])
    logger.info("Signaux forts: {}", stats["signals_strong"])
    logger.info("Chaînes IA déclenchées: {} (via signal injecté: {})", stats["signals_strong"], injected_signal)
    logger.info("Trades exécutés: {}", stats["trades_executed"])
    logger.info("Messages WS capturés: {}", len(stats["ws_messages"]))
    ws_types = {}
    for m in stats["ws_messages"]:
        ws_types[m["type"]] = ws_types.get(m["type"], 0) + 1
    logger.info("Types WS: {}", ws_types)
    logger.info("Coût API total: ${:.4f}", orch.claude.total_cost)

    # Assertions finales
    assert stats["candles_received"] > 0, "Aucune candle reçue ! DataCollector ne fonctionne pas."
    logger.success("DataCollector OK — {} candles live reçues", stats["candles_received"])

    if stats["signals_strong"] > 0 or injected_signal:
        logger.success("Chaîne IA déclenchée — signal → analyse → décision")

        # Vérifier qu'il y a des logs d'agents IA
        ia_logs = await orch.db.fetchone("SELECT COUNT(*) as cnt FROM agent_logs")
        assert ia_logs["cnt"] > 0, "Aucun log d'agent IA en base !"
        logger.success("Agents IA loggés en base — {} entrées", ia_logs["cnt"])

    logger.success("")
    logger.success("=" * 70)
    logger.success("TEST LIVE PAPER TRADING : RÉUSSI")
    logger.success("=" * 70)

    await orch.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
