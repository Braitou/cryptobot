"""NewsScraper — Collecte de données macro/sentiment. Python pur, pas d'IA.

Scrape toutes les 30 min :
- Fear & Greed Index (alternative.me)
- CryptoCompare top news
- Binance funding rates (futures, indicateur de sentiment)

Stocke dans la table SQLite news_cache.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import aiohttp

from backend.storage.database import Database
from backend.utils.logger import logger

NEWS_SOURCES = {
    "fear_greed": "https://api.alternative.me/fng/?limit=1",
    "cryptocompare": "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&limit=5",
}

# Binance funding rates pour les paires principales (indicateur de sentiment)
FUNDING_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


class NewsScraper:
    """Collecte de données macro/sentiment toutes les 30 minutes."""

    SCRAPE_INTERVAL_S = 1800  # 30 minutes

    def __init__(self, db: Database) -> None:
        self.db = db
        self._task: asyncio.Task | None = None
        self._latest: dict[str, Any] = {}

    async def start(self) -> None:
        """Démarre le scraper en tâche de fond."""
        self._task = asyncio.create_task(self._loop())
        logger.info("NewsScraper démarré (intervalle {}s)", self.SCRAPE_INTERVAL_S)

    async def stop(self) -> None:
        """Arrête le scraper."""
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        """Boucle principale : scrape toutes les 30 min."""
        # Premier scrape après 10s (laisser le temps au setup)
        await asyncio.sleep(10)

        while True:
            try:
                await self.scrape_all()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("NewsScraper erreur: {}", e)

            await asyncio.sleep(self.SCRAPE_INTERVAL_S)

    async def scrape_all(self) -> dict[str, Any]:
        """Scrape toutes les sources et stocke en DB."""
        now = datetime.now(timezone.utc).isoformat()
        results: dict[str, Any] = {}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            # Fear & Greed
            fg = await self._fetch_json(session, NEWS_SOURCES["fear_greed"])
            if fg:
                results["fear_greed"] = fg
                await self._store(now, "fear_greed", fg)

            # CryptoCompare news
            cc = await self._fetch_json(session, NEWS_SOURCES["cryptocompare"])
            if cc:
                results["cryptocompare"] = cc
                await self._store(now, "cryptocompare", cc)

            # Binance funding rates
            for pair in FUNDING_PAIRS:
                url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={pair}&limit=1"
                fr = await self._fetch_json(session, url)
                if fr:
                    key = f"funding_{pair}"
                    results[key] = fr
                    await self._store(now, key, fr)

        self._latest = results
        logger.info("NewsScraper: {} sources collectées", len(results))
        return results

    async def _fetch_json(self, session: aiohttp.ClientSession, url: str) -> Any | None:
        """Fetch une URL et retourne le JSON ou None si erreur."""
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning("NewsScraper: {} → HTTP {}", url, resp.status)
        except Exception as e:
            logger.warning("NewsScraper: {} → {}", url, e)
        return None

    async def _store(self, timestamp: str, source: str, data: Any) -> None:
        """Stocke les données dans news_cache."""
        try:
            await self.db.execute(
                "INSERT OR REPLACE INTO news_cache (timestamp, source, data) VALUES (?, ?, ?)",
                (timestamp, source, json.dumps(data)),
            )
        except Exception as e:
            logger.error("NewsScraper store erreur: {}", e)

    def get_latest(self) -> dict[str, Any]:
        """Retourne les dernières données scrapées (pour le Regime Advisor)."""
        return self._latest

    def get_fear_greed(self) -> int | None:
        """Retourne le Fear & Greed index actuel (0-100) ou None."""
        fg = self._latest.get("fear_greed", {})
        try:
            return int(fg["data"][0]["value"])
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def get_summary_for_advisor(self) -> str:
        """Retourne un résumé texte compact pour le Regime Advisor."""
        lines = []

        # Fear & Greed
        fg = self.get_fear_greed()
        if fg is not None:
            fg_raw = self._latest.get("fear_greed", {})
            fg_list = fg_raw.get("data") if isinstance(fg_raw, dict) else None
            fg_data = fg_list[0] if isinstance(fg_list, list) and fg_list else {}
            label = fg_data.get("value_classification", "?") if isinstance(fg_data, dict) else "?"
            lines.append(f"Fear & Greed: {fg}/100 ({label})")

        # Funding rates
        for pair in FUNDING_PAIRS:
            fr = self._latest.get(f"funding_{pair}")
            if fr and isinstance(fr, list) and len(fr) > 0:
                rate = float(fr[0].get("fundingRate", 0)) * 100
                lines.append(f"Funding {pair}: {rate:+.4f}%")

        # Top news headlines
        cc = self._latest.get("cryptocompare", {})
        if not isinstance(cc, dict):
            cc = {}
        articles_raw = cc.get("Data")
        articles = articles_raw[:3] if isinstance(articles_raw, list) else []
        if articles:
            lines.append("Top news:")
            for a in articles:
                title = a.get("title", "?") if isinstance(a, dict) else str(a)
                lines.append(f"  - {title[:80]}")

        return "\n".join(lines) if lines else "Aucune donnée disponible"
