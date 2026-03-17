"""Test Phase 0 — Vérifie config, DB, connexion Binance testnet et appel Claude Haiku."""

import asyncio
import sys
from pathlib import Path

# Ajouter la racine du projet au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.storage.database import Database
from backend.utils.binance_client import BinanceClient
from backend.utils.claude_client import ClaudeClient
from backend.utils.logger import logger


async def test_config() -> None:
    logger.info("=== Test 1 : Config ===")
    settings = get_settings()
    logger.info("PAIRS = {}", settings.pairs_list)
    logger.info("TRADING_MODE = {}", settings.TRADING_MODE)
    logger.info("BINANCE_TESTNET = {}", settings.BINANCE_TESTNET)
    logger.info("AI_MODEL_FAST = {}", settings.AI_MODEL_FAST)
    assert settings.BINANCE_TESTNET is True, "TESTNET doit être True pour les tests !"
    assert settings.TRADING_MODE == "paper", "Mode doit être paper !"
    logger.success("Config OK")


async def test_database() -> None:
    logger.info("=== Test 2 : Database ===")
    db = Database()
    await db.connect()

    # Vérifie que les tables existent
    tables = await db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = [t["name"] for t in tables]
    logger.info("Tables créées : {}", table_names)
    for expected in ["candles", "trades", "agent_logs", "portfolio", "memory_entries"]:
        assert expected in table_names, f"Table manquante : {expected}"

    await db.close()
    logger.success("Database OK")


async def test_binance() -> None:
    logger.info("=== Test 3 : Binance testnet ===")
    settings = get_settings()
    binance = BinanceClient(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        testnet=settings.BINANCE_TESTNET,
    )
    await binance.connect()

    btc_price = await binance.get_price("BTCUSDT")
    logger.info("BTC/USDT prix = {}", btc_price)
    assert btc_price > 0, "Prix BTC doit être > 0"

    orderbook = await binance.get_orderbook("BTCUSDT")
    logger.info("Spread = {:.4f}% | Imbalance = {:.2f}", orderbook["bid_ask_spread"], orderbook["imbalance_ratio"])

    klines = await binance.get_klines("BTCUSDT", "1m", limit=5)
    logger.info("{} candles récupérées — dernière close = {}", len(klines), klines[-1]["close"])

    await binance.close()
    logger.success("Binance testnet OK")


async def test_claude() -> None:
    logger.info("=== Test 4 : Claude Haiku ===")
    settings = get_settings()
    claude = ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)

    response = await claude.ask(
        model=settings.AI_MODEL_FAST,
        system="Tu es un assistant de test. Réponds en une phrase.",
        prompt="Dis 'CryptoBot Phase 0 OK' si tu reçois ce message.",
        max_tokens=64,
    )
    logger.info("Réponse : {}", response.content)
    logger.info("Tokens : {} in / {} out — coût ${:.4f} — {}ms", response.tokens_in, response.tokens_out, response.cost_usd, response.duration_ms)
    assert response.tokens_in > 0
    assert response.tokens_out > 0
    logger.success("Claude Haiku OK — coût total session : ${:.4f}", claude.total_cost)


async def main() -> None:
    logger.info("========== CryptoBot — Test Phase 0 ==========")
    try:
        await test_config()
        await test_database()
        await test_binance()
        await test_claude()
        logger.success("========== PHASE 0 : TOUS LES TESTS OK ==========")
    except Exception as e:
        logger.error("ÉCHEC : {}", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
