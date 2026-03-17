"""Test si les candles Binance arrivent et se ferment."""
import asyncio
from backend.utils.binance_client import BinanceClient
from backend.config import get_settings


async def test():
    s = get_settings()
    bc = BinanceClient(s.BINANCE_API_KEY, s.BINANCE_API_SECRET, s.BINANCE_TESTNET)
    await bc.connect()
    print("Connecte. En attente de 10 messages kline BTCUSDT 1m...")
    count = 0
    async with bc.bsm.kline_socket("BTCUSDT", interval="1m") as stream:
        while count < 10:
            msg = await stream.recv()
            k = msg.get("k", {})
            closed = k.get("x")
            close_price = k.get("c")
            interval = k.get("i")
            print(f"#{count} closed={closed} close={close_price} interval={interval}")
            count += 1
    await bc.close()
    print("Done")


asyncio.run(test())
