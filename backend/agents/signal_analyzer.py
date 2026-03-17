"""SignalAnalyzer — Indicateurs techniques + score composite.

Ne prend aucune décision. Détecte quand le marché est "intéressant"
et publie un signal sur le bus pour réveiller les agents IA.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd
import ta

from backend.agents.base import BaseAgent
from backend.utils.logger import logger


class SignalAnalyzer(BaseAgent):
    """Calcule les indicateurs techniques et produit un score -1 à +1."""

    name = "signal_analyzer"

    def __init__(
        self,
        signal_threshold: float = 0.25,
        bus: asyncio.Queue | None = None,
    ) -> None:
        super().__init__(bus=bus)
        self.signal_threshold = signal_threshold

    # ─── Indicateurs techniques ───────────────────────────────────────

    def compute_indicators(self, df: pd.DataFrame) -> dict[str, float] | None:
        """Calcule tous les indicateurs sur un DataFrame de candles.

        Retourne None si pas assez de données (< 30 candles).
        """
        if len(df) < 30:
            return None

        # Filtrer les candles aberrantes (testnet) — range > 10% du close
        df = df.copy()
        candle_range = (df["high"] - df["low"]) / df["close"]
        df.loc[candle_range > 0.10, "high"] = df["close"]
        df.loc[candle_range > 0.10, "low"] = df["close"]

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # RSI
        rsi = ta.momentum.RSIIndicator(close, window=14)
        rsi_val = rsi.rsi().iloc[-1]

        # MACD
        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = macd.macd().iloc[-1]
        macd_signal = macd.macd_signal().iloc[-1]
        macd_hist = macd.macd_diff().iloc[-1]

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_middle = bb.bollinger_mavg().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_range = bb_upper - bb_lower
        bb_pct = (close.iloc[-1] - bb_lower) / bb_range if bb_range > 0 else 0.5

        # EMA 9 / 21
        ema_9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
        ema_21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]

        # ATR
        atr = ta.volatility.AverageTrueRange(high, low, close, window=14)
        atr_val = atr.average_true_range().iloc[-1]

        # VWAP (approximation intraday via cumul)
        typical = (high + low + close) / 3
        vwap = (typical * volume).cumsum() / volume.cumsum()
        vwap_val = vwap.iloc[-1]

        # Volume ratio (vs SMA 20)
        vol_sma = volume.rolling(20).mean().iloc[-1]
        volume_ratio = volume.iloc[-1] / vol_sma if vol_sma > 0 else 1.0

        # Price changes
        price_now = close.iloc[-1]
        price_change_5m = _pct_change(close, 5)
        price_change_15m = _pct_change(close, 15)
        price_change_1h = _pct_change(close, 60)

        indicators = {
            "rsi_14": float(rsi_val),
            "macd_line": float(macd_line),
            "macd_signal": float(macd_signal),
            "macd_histogram": float(macd_hist),
            "bb_upper": float(bb_upper),
            "bb_middle": float(bb_middle),
            "bb_lower": float(bb_lower),
            "bb_pct": float(bb_pct),
            "vwap": float(vwap_val),
            "ema_9": float(ema_9),
            "ema_21": float(ema_21),
            "atr_14": float(atr_val),
            "volume_ratio": float(volume_ratio),
            "price_change_5m": float(price_change_5m),
            "price_change_15m": float(price_change_15m),
            "price_change_1h": float(price_change_1h),
            "price": float(price_now),
        }

        # Remplacer NaN par 0
        for k, v in indicators.items():
            if np.isnan(v):
                indicators[k] = 0.0

        return indicators

    # ─── Score composite ──────────────────────────────────────────────

    def compute_score(self, indicators: dict[str, float], orderbook: dict[str, Any]) -> float:
        """Score composite -1.0 à +1.0.

        Approche par confluence : chaque composant vote indépendamment,
        puis un bonus de confluence amplifie le score quand plusieurs
        composants sont d'accord.

        Composants (chacun donne un score -1 à +1) :
        - Tendance (EMA9 vs EMA21 + prix vs VWAP)
        - Momentum (RSI + MACD histogram)
        - Volatilité (Bollinger %B)
        - Volume (volume ratio)
        - Order book (imbalance)
        """
        # --- 1. Tendance ---
        trend_score = 0.0
        if indicators["ema_21"] > 0:
            ema_diff_pct = (indicators["ema_9"] - indicators["ema_21"]) / indicators["ema_21"]
            trend_score += _clamp(ema_diff_pct * 200, -1, 1) * 0.5
        if indicators["vwap"] > 0:
            vwap_diff_pct = (indicators["price"] - indicators["vwap"]) / indicators["vwap"]
            trend_score += _clamp(vwap_diff_pct * 200, -1, 1) * 0.5

        # --- 2. RSI ---
        rsi = indicators["rsi_14"]
        if rsi <= 30:
            rsi_score = (30 - rsi) / 20  # 30→0, 10→+1
        elif rsi >= 70:
            rsi_score = (70 - rsi) / 20  # 70→0, 90→-1
        else:
            # Zone neutre avec léger signal graduel
            rsi_score = (50 - rsi) / 100  # -0.2 à +0.2

        rsi_score = _clamp(rsi_score, -1, 1)

        # --- 3. MACD ---
        macd_hist = indicators["macd_histogram"]
        price = indicators["price"]
        macd_norm = (macd_hist / price * 10000) if price > 0 else 0
        macd_score = _clamp(macd_norm / 3, -1, 1)

        # --- 4. Bollinger %B ---
        bb_pct = indicators["bb_pct"]
        if bb_pct <= 0.15:
            bb_score = (0.15 - bb_pct) / 0.15  # near/below lower → bullish
        elif bb_pct >= 0.85:
            bb_score = (0.85 - bb_pct) / 0.15  # near/above upper → bearish
        else:
            bb_score = (0.5 - bb_pct) / 2  # léger gradient au milieu
        bb_score = _clamp(bb_score, -1, 1)

        # --- 5. Volume ---
        vol_ratio = indicators["volume_ratio"]
        # Volume élevé amplifie la conviction, volume faible la réduit
        vol_multiplier = _clamp(vol_ratio / 2, 0.3, 2.0)

        # --- 6. Order book ---
        imbalance = orderbook.get("imbalance_ratio", 0.5)
        ob_score = _clamp((imbalance - 0.5) * 3, -1, 1)

        # --- Combinaison pondérée ---
        raw = (
            trend_score * 0.25
            + rsi_score * 0.20
            + macd_score * 0.25
            + bb_score * 0.15
            + ob_score * 0.15
        )

        # --- Bonus de confluence ---
        # Compter combien de composants sont d'accord (même signe)
        components = [trend_score, rsi_score, macd_score, bb_score, ob_score]
        bullish = sum(1 for c in components if c > 0.1)
        bearish = sum(1 for c in components if c < -0.1)
        agreement = max(bullish, bearish)

        # 4+ composants d'accord → bonus ×1.5, 5 d'accord → ×2.0
        if agreement >= 5:
            confluence = 2.0
        elif agreement >= 4:
            confluence = 1.5
        elif agreement >= 3:
            confluence = 1.2
        else:
            confluence = 1.0

        # Appliquer volume comme multiplicateur + confluence
        total = raw * vol_multiplier * confluence
        return _clamp(total, -1, 1)

    # ─── Analyse complète ─────────────────────────────────────────────

    async def analyze(
        self, pair: str, df: pd.DataFrame, orderbook: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Analyse une paire et publie un signal si le score est significatif.

        Retourne le dict {indicators, score} ou None si pas assez de données.
        """
        indicators = self.compute_indicators(df)
        if indicators is None:
            return None

        score = self.compute_score(indicators, orderbook)

        result = {
            "pair": pair,
            "score": round(score, 4),
            "indicators": indicators,
            "orderbook": orderbook,
        }

        if abs(score) >= self.signal_threshold:
            await self.publish("signal", result)
            logger.info(
                "Signal {} — score={:.3f} (RSI={:.0f} MACD_h={:.4f} BB%={:.2f})",
                pair, score,
                indicators["rsi_14"],
                indicators["macd_histogram"],
                indicators["bb_pct"],
            )

        return result


def _pct_change(series: pd.Series, periods: int) -> float:
    """% de changement sur N périodes. Retourne 0 si pas assez de données."""
    if len(series) <= periods:
        return 0.0
    old = series.iloc[-periods - 1]
    if old == 0:
        return 0.0
    return ((series.iloc[-1] - old) / old) * 100


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
