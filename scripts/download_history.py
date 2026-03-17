"""Télécharge l'historique des candles Binance (30 jours) et les insère en SQLite."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.storage.database import Database
from backend.utils.binance_client import BinanceClient
from backend.utils.logger import logger

# Limites API Binance
MAX_KLINES_PER_REQUEST = 1000

# Intervalles en millisecondes
INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


async def download_pair_interval(
    binance: BinanceClient,
    db: Database,
    pair: str,
    interval: str,
    days: int = 30,
) -> int:
    """Télécharge les candles pour une paire/intervalle. Retourne le nb inséré."""
    import time

    end_ms = int(time.time() * 1000)
    iv_ms = INTERVAL_MS.get(interval, 60_000)
    start_ms = end_ms - (days * 86_400_000)
    total_inserted = 0

    logger.info("Téléchargement {} {} — {} jours…", pair, interval, days)

    current_start = start_ms
    while current_start < end_ms:
        raw = await binance.client.get_klines(
            symbol=pair,
            interval=interval,
            startTime=current_start,
            limit=MAX_KLINES_PER_REQUEST,
        )
        if not raw:
            break

        params = [
            (
                pair, interval, k[0],
                float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                float(k[5]), k[6], float(k[7]), k[8],
            )
            for k in raw
        ]
        await db.executemany(
            """INSERT OR IGNORE INTO candles
               (pair, interval, open_time, open, high, low, close,
                volume, close_time, quote_volume, trades_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            params,
        )
        total_inserted += len(params)

        # Avancer au-delà de la dernière candle reçue
        last_open_time = raw[-1][0]
        current_start = last_open_time + iv_ms

        # Rate limiting
        await asyncio.sleep(0.2)

    logger.info("  → {} {} : {} candles insérées", pair, interval, total_inserted)
    return total_inserted


async def main() -> None:
    settings = get_settings()
    db = Database()
    await db.connect()

    binance = BinanceClient(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        testnet=settings.BINANCE_TESTNET,
    )
    await binance.connect()

    total = 0
    for pair in settings.pairs_list:
        for interval in settings.candle_intervals_list:
            count = await download_pair_interval(binance, db, pair, interval, days=30)
            total += count

    logger.success("Historique complet — {} candles totales en base", total)

    await binance.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
