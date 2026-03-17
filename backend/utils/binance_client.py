"""Wrapper async python-binance — spot uniquement."""

from __future__ import annotations

from binance import AsyncClient, BinanceSocketManager

from backend.utils.logger import logger


class BinanceClient:
    """Wrapper autour de python-binance AsyncClient.

    Gère la connexion/déconnexion et expose les méthodes utilisées par le bot.
    SPOT UNIQUEMENT — jamais de futures/margin/levier.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._client: AsyncClient | None = None
        self._bsm: BinanceSocketManager | None = None

    async def connect(self) -> None:
        """Crée le client async et vérifie la connexion."""
        self._client = await AsyncClient.create(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
        )
        self._bsm = BinanceSocketManager(self._client)
        try:
            status = await self._client.get_system_status()
            status_msg = status.get("msg", status)
        except Exception:
            status_msg = "ok"
        logger.info(
            "Binance {} connecté — status: {}",
            "testnet" if self.testnet else "PRODUCTION (paper mode)",
            status_msg,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close_connection()
            self._client = None
            self._bsm = None
            logger.info("Binance déconnecté")

    @property
    def client(self) -> AsyncClient:
        if self._client is None:
            raise RuntimeError("BinanceClient non connecté — appeler connect() d'abord")
        return self._client

    @property
    def bsm(self) -> BinanceSocketManager:
        if self._bsm is None:
            raise RuntimeError("BinanceClient non connecté — appeler connect() d'abord")
        return self._bsm

    # --- Méthodes de lecture ---

    async def get_price(self, symbol: str) -> float:
        """Prix actuel d'une paire."""
        ticker = await self.client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[dict]:
        """Récupère les N dernières candles."""
        raw = await self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
        return [
            {
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
                "quote_volume": float(k[7]),
                "trades_count": k[8],
            }
            for k in raw
        ]

    async def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        """Order book avec spread et imbalance."""
        book = await self.client.get_order_book(symbol=symbol, limit=limit)
        bids_vol = sum(float(b[1]) for b in book["bids"])
        asks_vol = sum(float(a[1]) for a in book["asks"])
        total = bids_vol + asks_vol
        best_bid = float(book["bids"][0][0]) if book["bids"] else 0
        best_ask = float(book["asks"][0][0]) if book["asks"] else 0
        mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 1
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_ask_spread": ((best_ask - best_bid) / mid) * 100 if mid else 0,
            "imbalance_ratio": bids_vol / total if total else 0.5,
            "bids_volume": bids_vol,
            "asks_volume": asks_vol,
        }

    async def get_account(self) -> dict:
        """Infos du compte (balances)."""
        return await self.client.get_account()
