"""Test Phase 5 — Orchestrateur + API.

1. Test orchestrateur : setup, dispatch d'un faux signal, portfolio state
2. Test API : lancer le serveur, appeler chaque endpoint REST
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.base import AgentMessage
from backend.config import get_settings
from backend.main import Orchestrator
from backend.utils.logger import logger


# ═══════════════════════════════════════════════════════════════════════
# TEST 1 : Orchestrator setup + portfolio state
# ═══════════════════════════════════════════════════════════════════════

async def test_orchestrator_setup() -> Orchestrator:
    logger.info("=" * 60)
    logger.info("TEST 1 : Orchestrator setup")
    logger.info("=" * 60)

    settings = get_settings()
    orch = Orchestrator(settings)
    await orch.setup()

    assert orch.db is not None
    assert orch.binance is not None
    assert orch.claude is not None
    assert orch.data_collector is not None
    assert orch.signal_analyzer is not None
    assert orch.risk_guard is not None
    assert orch.executor is not None
    assert orch.market_analyst is not None
    assert orch.decision_agent is not None
    assert orch.risk_evaluator is not None
    assert orch.post_trade is not None

    logger.info("  Tous les agents instanciés")

    # Portfolio state
    state = await orch._get_portfolio_state()
    logger.info("  Portfolio: capital={:.2f} | open_pos={} | daily_pnl={:.2f} | drawdown={:.1%}",
                state["capital"], state["open_positions"], state["daily_pnl"], state["drawdown_pct"])
    assert state["capital"] > 0
    logger.success("Orchestrator setup OK")
    return orch


# ═══════════════════════════════════════════════════════════════════════
# TEST 2 : Dispatch d'un candle_closed (sans signal fort attendu)
# ═══════════════════════════════════════════════════════════════════════

async def test_dispatch_candle(orch: Orchestrator) -> None:
    logger.info("=" * 60)
    logger.info("TEST 2 : Dispatch candle_closed")
    logger.info("=" * 60)

    # On doit avoir des candles en base (du download_history)
    count = await orch.db.fetchone(
        "SELECT COUNT(*) as cnt FROM candles WHERE pair='BTCUSDT' AND interval='5m'"
    )
    logger.info("  Candles 5m en base: {}", count["cnt"])

    if count["cnt"] < 30:
        logger.warning("  Pas assez de candles — skip du test dispatch")
        return

    # Simuler un message candle_closed
    msg = AgentMessage(
        type="candle_closed",
        data={"pair": "BTCUSDT", "interval": "5m"},
        source="test",
    )
    await orch._dispatch(msg)
    logger.info("  Dispatch candle_closed traité (signal calculé)")

    # Vérifier qu'un signal a peut-être été publié
    signals = []
    while not orch.bus.empty():
        m = await orch.bus.get()
        signals.append(m)
        logger.info("  Message sur le bus: type={} source={}", m.type, m.source)

    logger.success("Dispatch candle_closed OK — {} messages générés", len(signals))


# ═══════════════════════════════════════════════════════════════════════
# TEST 3 : API — test de chaque endpoint via TestClient
# ═══════════════════════════════════════════════════════════════════════

async def test_api_endpoints() -> None:
    logger.info("=" * 60)
    logger.info("TEST 3 : API endpoints REST")
    logger.info("=" * 60)

    from httpx import ASGITransport, AsyncClient

    import backend.api.server as server_mod
    from backend.main import Orchestrator

    # Créer et injecter un orchestrateur directement (sans lifespan/bot loop)
    settings = get_settings()
    orch = Orchestrator(settings)
    await orch.setup()
    server_mod._orchestrator = orch

    # Créer l'app sans lifespan pour le test
    from fastapi import FastAPI
    from backend.api.routes import create_router
    test_app = FastAPI()
    router = create_router(lambda: server_mod._orchestrator)
    test_app.include_router(router, prefix="/api")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/config
        r = await client.get("/api/config")
        config = r.json()
        assert config["trading_mode"] == "paper"
        assert config["testnet"] is True
        logger.info("  GET /api/config — OK (mode={}, pairs={})", config["trading_mode"], config["pairs"])

        # GET /api/portfolio
        r = await client.get("/api/portfolio")
        assert r.status_code == 200
        portfolio = r.json()
        assert "capital" in portfolio
        assert "kill_switch" in portfolio
        logger.info("  GET /api/portfolio — OK (capital={:.2f})", portfolio["capital"])

        # GET /api/trades
        r = await client.get("/api/trades")
        assert r.status_code == 200
        trades = r.json()
        logger.info("  GET /api/trades — OK ({} trades)", len(trades))

        # GET /api/trades/999 (non-existent)
        r = await client.get("/api/trades/999999")
        assert r.status_code == 404
        logger.info("  GET /api/trades/999999 — 404 OK")

        # GET /api/signals
        r = await client.get("/api/signals")
        assert r.status_code == 200
        signals = r.json()
        logger.info("  GET /api/signals — OK (pairs={})", list(signals.keys()))

        # GET /api/memory
        r = await client.get("/api/memory")
        assert r.status_code == 200
        mem = r.json()
        logger.info("  GET /api/memory — OK ({} entries)", len(mem.get("entries", [])))

        # GET /api/agents/status
        r = await client.get("/api/agents/status")
        assert r.status_code == 200
        status = r.json()
        logger.info("  GET /api/agents/status — OK (agents={})", list(status.keys()))

        # GET /api/agents/costs
        r = await client.get("/api/agents/costs")
        assert r.status_code == 200
        costs = r.json()
        logger.info("  GET /api/agents/costs — OK (total=${:.4f})", costs.get("_total", 0))

        # POST /api/kill-switch
        r = await client.post("/api/kill-switch")
        assert r.status_code == 200
        assert r.json()["status"] == "kill_switch_activated"
        logger.info("  POST /api/kill-switch — OK")

        # POST /api/resume
        r = await client.post("/api/resume")
        assert r.status_code == 200
        assert r.json()["status"] == "resumed"
        logger.info("  POST /api/resume — OK")

        # Vérifier que le kill switch est bien reset
        r = await client.get("/api/portfolio")
        ks = r.json()["kill_switch"]
        assert ks["daily_kill"] is False
        assert ks["total_kill"] is False
        logger.info("  Kill switch reset vérifié — OK")

    logger.success("API endpoints OK — 10/10 endpoints testés")
    await orch.shutdown()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

async def main() -> None:
    logger.info("=" * 60)
    logger.info("CryptoBot — Test Phase 5 — Orchestrateur + API")
    logger.info("=" * 60)

    try:
        orch = await test_orchestrator_setup()
        await test_dispatch_candle(orch)
        await orch.shutdown()

        await test_api_endpoints()

        logger.success("=" * 60)
        logger.success("PHASE 5 : TOUS LES TESTS OK")
        logger.success("=" * 60)
    except Exception as e:
        logger.error("ÉCHEC : {}", e)
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
