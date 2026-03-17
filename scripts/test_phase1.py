"""Test Phase 1 — DataCollector (REST) + SignalAnalyzer sur données réelles."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.signal_analyzer import SignalAnalyzer
from backend.config import get_settings
from backend.storage.database import Database
from backend.utils.binance_client import BinanceClient
from backend.utils.logger import logger


async def test_data_and_signals() -> None:
    settings = get_settings()

    # --- Connexion ---
    db = Database()
    await db.connect()

    binance = BinanceClient(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        testnet=settings.BINANCE_TESTNET,
    )
    await binance.connect()

    bus: asyncio.Queue = asyncio.Queue()
    analyzer = SignalAnalyzer(signal_threshold=0.5, bus=bus)

    for pair in settings.pairs_list:
        logger.info("=== {} ===", pair)

        # 1. Vérifier qu'on a des candles en base (depuis download_history)
        count_row = await db.fetchone(
            "SELECT COUNT(*) as cnt FROM candles WHERE pair = ? AND interval = '5m'",
            (pair,),
        )
        candle_count = count_row["cnt"] if count_row else 0
        logger.info("Candles 5m en base : {}", candle_count)

        if candle_count < 30:
            # Fallback : charger via REST
            logger.warning("Pas assez de candles en base, chargement REST…")
            klines = await binance.get_klines(pair, "5m", limit=100)
            import pandas as pd
            df = pd.DataFrame(klines)
        else:
            # Charger depuis SQLite
            rows = await db.fetchall(
                """SELECT open_time, open, high, low, close, volume, quote_volume, trades_count
                   FROM candles WHERE pair = ? AND interval = '5m'
                   ORDER BY open_time DESC LIMIT 100""",
                (pair,),
            )
            import pandas as pd
            df = pd.DataFrame(rows).sort_values("open_time").reset_index(drop=True)

        logger.info("DataFrame : {} lignes, colonnes = {}", len(df), list(df.columns))

        # 2. Indicateurs
        indicators = analyzer.compute_indicators(df)
        if indicators is None:
            logger.error("Pas assez de données pour les indicateurs !")
            continue

        logger.info(
            "RSI={:.1f} | MACD_h={:.6f} | BB%={:.2f} | EMA9/21={}/{}",
            indicators["rsi_14"],
            indicators["macd_histogram"],
            indicators["bb_pct"],
            "↑" if indicators["ema_9"] > indicators["ema_21"] else "↓",
            "",
        )
        logger.info(
            "ATR={:.2f} | VWAP={:.2f} | Vol_ratio={:.1f}x | Price={:.2f}",
            indicators["atr_14"],
            indicators["vwap"],
            indicators["volume_ratio"],
            indicators["price"],
        )

        # 3. Orderbook
        orderbook = await binance.get_orderbook(pair)
        logger.info(
            "Orderbook — spread={:.4f}% | imbalance={:.2f}",
            orderbook["bid_ask_spread"],
            orderbook["imbalance_ratio"],
        )

        # 4. Score
        score = analyzer.compute_score(indicators, orderbook)
        signal_type = (
            "ACHAT FORT" if score > 0.5
            else "VENTE FORTE" if score < -0.5
            else "neutre"
        )
        logger.info("Score = {:.4f} → {}", score, signal_type)

        # 5. Analyse complète (teste le publish)
        result = await analyzer.analyze(pair, df, orderbook)
        if result:
            logger.info("Analyse OK — score publié = {}", result["score"])

    # Vérifier si des signaux ont été publiés
    signals_count = bus.qsize()
    logger.info("Signaux publiés sur le bus : {}", signals_count)

    await binance.close()
    await db.close()


async def main() -> None:
    logger.info("========== CryptoBot — Test Phase 1 ==========")
    try:
        await test_data_and_signals()
        logger.success("========== PHASE 1 : TESTS OK ==========")
    except Exception as e:
        logger.error("ÉCHEC : {}", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
