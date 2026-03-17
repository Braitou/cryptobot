"""DataCollector — WebSocket Binance → candles, orderbook en cache mémoire."""

from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd

from backend.agents.base import AgentState, BaseAgent
from backend.storage.database import Database
from backend.utils.binance_client import BinanceClient
from backend.utils.logger import logger


class DataCollector(BaseAgent):
    """Collecte les données Binance via WebSocket et REST.

    - Klines (candles) → SQLite + bus 'candle_closed'
    - Order book → cache mémoire + bus 'orderbook_update'
    - Reconnexion automatique avec backoff exponentiel (1s → 60s max).
    """

    name = "data_collector"

    def __init__(
        self,
        binance: BinanceClient,
        db: Database,
        pairs: list[str],
        intervals: list[str],
        bus: asyncio.Queue | None = None,
    ) -> None:
        super().__init__(bus=bus)
        self.binance = binance
        self.db = db
        self.pairs = pairs
        self.intervals = intervals
        # Cache mémoire pour l'orderbook (pair → dict)
        self.orderbooks: dict[str, dict[str, Any]] = {}
        # Cache mémoire pour le dernier prix (pair → float)
        self.prices: dict[str, float] = {}
        self._ws_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Lance les streams WebSocket pour chaque paire."""
        await super().start()
        for pair in self.pairs:
            task = asyncio.create_task(self._run_kline_streams(pair))
            self._ws_tasks.append(task)
            task = asyncio.create_task(self._run_orderbook_stream(pair))
            self._ws_tasks.append(task)
        logger.info("DataCollector démarré — {} paires, {} intervalles", len(self.pairs), len(self.intervals))

    async def stop(self) -> None:
        """Annule tous les streams."""
        for task in self._ws_tasks:
            task.cancel()
        self._ws_tasks.clear()
        await super().stop()
        logger.info("DataCollector arrêté")

    # ─── WebSocket streams ────────────────────────────────────────────

    async def _run_kline_streams(self, pair: str) -> None:
        """Stream klines pour toutes les intervalles d'une paire, avec reconnexion."""
        backoff = 1
        while self.state == AgentState.RUNNING:
            try:
                streams = [f"{pair.lower()}@kline_{iv}" for iv in self.intervals]
                async with self.binance.bsm.multiplex_socket(streams) as stream:
                    backoff = 1  # reset on successful connect
                    logger.info("WS klines connecté — {} ({})", pair, self.intervals)
                    while True:
                        msg = await stream.recv()
                        if msg is None:
                            break
                        data = msg.get("data", msg)
                        if "k" in data:
                            await self._on_kline(pair, data["k"])
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("WS klines {} erreur: {} — reconnexion dans {}s", pair, e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _run_orderbook_stream(self, pair: str) -> None:
        """Stream order book pour une paire, avec reconnexion."""
        backoff = 1
        while self.state == AgentState.RUNNING:
            try:
                async with self.binance.bsm.depth_socket(pair, depth=20, interval=100) as stream:
                    backoff = 1
                    logger.info("WS orderbook connecté — {}", pair)
                    while True:
                        msg = await stream.recv()
                        if msg is None:
                            break
                        await self._on_orderbook(pair, msg)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("WS orderbook {} erreur: {} — reconnexion dans {}s", pair, e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ─── Handlers ─────────────────────────────────────────────────────

    async def _on_kline(self, pair: str, k: dict[str, Any]) -> None:
        """Traite un message kline. Insère dans SQLite si la candle est fermée."""
        self.prices[pair] = float(k["c"])

        if not k["x"]:  # candle pas encore fermée
            return

        interval = k["i"]
        candle = {
            "pair": pair,
            "interval": interval,
            "open_time": k["t"],
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "close_time": k["T"],
            "quote_volume": float(k["q"]),
            "trades_count": k["n"],
        }

        await self.db.execute(
            """INSERT OR IGNORE INTO candles
               (pair, interval, open_time, open, high, low, close, volume,
                close_time, quote_volume, trades_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candle["pair"], candle["interval"], candle["open_time"],
                candle["open"], candle["high"], candle["low"], candle["close"],
                candle["volume"], candle["close_time"], candle["quote_volume"],
                candle["trades_count"],
            ),
        )

        await self.publish("candle_closed", {"pair": pair, "interval": interval, **candle})
        logger.debug("Candle {} {} — close={}", pair, interval, candle["close"])

    async def _on_orderbook(self, pair: str, data: dict[str, Any]) -> None:
        """Met à jour le cache orderbook en mémoire."""
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        bids_vol = sum(float(b[1]) for b in bids) if bids else 0
        asks_vol = sum(float(a[1]) for a in asks) if asks else 0
        total = bids_vol + asks_vol

        best_bid = float(bids[0][0]) if bids else 0
        best_ask = float(asks[0][0]) if asks else 0
        mid = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 1

        self.orderbooks[pair] = {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_ask_spread": ((best_ask - best_bid) / mid) * 100 if mid else 0,
            "imbalance_ratio": bids_vol / total if total else 0.5,
            "bids_volume": bids_vol,
            "asks_volume": asks_vol,
        }

    # ─── Accesseurs ───────────────────────────────────────────────────

    async def get_recent_candles(
        self, pair: str, interval: str, limit: int = 100
    ) -> pd.DataFrame:
        """Retourne les N dernières candles depuis SQLite en DataFrame."""
        rows = await self.db.fetchall(
            """SELECT open_time, open, high, low, close, volume, quote_volume, trades_count
               FROM candles
               WHERE pair = ? AND interval = ?
               ORDER BY open_time DESC
               LIMIT ?""",
            (pair, interval, limit),
        )
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.sort_values("open_time").reset_index(drop=True)
        return df

    def get_orderbook(self, pair: str) -> dict[str, Any]:
        """Retourne le dernier orderbook caché pour une paire."""
        return self.orderbooks.get(pair, {
            "best_bid": 0, "best_ask": 0,
            "bid_ask_spread": 0, "imbalance_ratio": 0.5,
            "bids_volume": 0, "asks_volume": 0,
        })

    def get_price(self, pair: str) -> float:
        """Retourne le dernier prix connu."""
        return self.prices.get(pair, 0.0)
