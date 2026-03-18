"""SignalAnalyzer v2 — Indicateurs techniques + score composite + classification.

Ne prend aucune décision. Détecte quand le marché est "intéressant",
classifie le signal (SCALP / MOMENTUM) et publie sur le bus.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd
import ta

from backend.agents.base import BaseAgent
from backend.utils.logger import logger

# ─── Seuils de classification ──────────────────────────────────────
# Scalp utilise RSI 9 (plus réactif)
SCALP_RSI_OVERSOLD = 28
SCALP_RSI_OVERBOUGHT = 72
SCALP_BB_LOWER = 0.10
SCALP_BB_UPPER = 0.90
SCALP_MIN_VOLUME = 0.8
MOMENTUM_THRESHOLD = 0.45

# Paires autorisées par mode
SCALP_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
MOMENTUM_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT"]

# Scalp R:R après frais (0.15% A/R avec BNB, 0.20% sans) :
# Gain net : 1.0% - 0.15% = +0.85%  (ou 1.0% - 0.20% = +0.80% sans BNB)
# Perte nette : 0.5% + 0.15% = -0.65% (ou 0.5% + 0.20% = -0.70% sans BNB)
# R:R réel : 0.85/0.65 = 1.31 (avec BNB) ou 0.80/0.70 = 1.14 (sans BNB)
# Win rate minimum requis : 43% (avec BNB) ou 47% (sans BNB)
SCALP_CONFIG = {
    "take_profit_pct": 1.0,
    "stop_loss_pct": 0.5,
    "position_size_pct": 5.0,
    "max_hold_minutes": 30,
}
MOMENTUM_CONFIG = {
    "take_profit_pct": 1.5,
    "stop_loss_pct": 1.0,
    "position_size_pct": 8.0,
    "max_hold_minutes": 240,
}


class SignalAnalyzer(BaseAgent):
    """Calcule les indicateurs techniques et produit un score -1 à +1."""

    name = "signal_analyzer"

    def __init__(
        self,
        signal_threshold: float = 0.20,
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

        # RSI 14 (momentum / score composite) + RSI 9 (scalp, plus réactif)
        rsi = ta.momentum.RSIIndicator(close, window=14)
        rsi_val = rsi.rsi().iloc[-1]
        rsi_9 = ta.momentum.RSIIndicator(close, window=9)
        rsi_9_val = rsi_9.rsi().iloc[-1]

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
            "rsi_9": float(rsi_9_val),
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

        Pondérations v2 : trend 30%, RSI 25%, MACD 20%, BB 15%, OB 10%.
        """
        # --- 1. Tendance (30%) ---
        trend_score = 0.0
        if indicators["ema_21"] > 0:
            ema_diff_pct = (indicators["ema_9"] - indicators["ema_21"]) / indicators["ema_21"]
            trend_score += _clamp(ema_diff_pct * 200, -1, 1) * 0.5
        if indicators["vwap"] > 0:
            vwap_diff_pct = (indicators["price"] - indicators["vwap"]) / indicators["vwap"]
            trend_score += _clamp(vwap_diff_pct * 200, -1, 1) * 0.5

        # --- 2. RSI (25%) ---
        rsi = indicators["rsi_14"]
        if rsi <= 30:
            rsi_score = (30 - rsi) / 20  # 30→0, 10→+1
        elif rsi >= 70:
            rsi_score = (70 - rsi) / 20  # 70→0, 90→-1
        else:
            rsi_score = (50 - rsi) / 100  # -0.2 à +0.2
        rsi_score = _clamp(rsi_score, -1, 1)

        # --- 3. MACD (20%) ---
        macd_hist = indicators["macd_histogram"]
        price = indicators["price"]
        macd_norm = (macd_hist / price * 10000) if price > 0 else 0
        macd_score = _clamp(macd_norm / 3, -1, 1)

        # --- 4. Bollinger %B (15%) ---
        bb_pct = indicators["bb_pct"]
        if bb_pct <= 0.15:
            bb_score = (0.15 - bb_pct) / 0.15
        elif bb_pct >= 0.85:
            bb_score = (0.85 - bb_pct) / 0.15
        else:
            bb_score = (0.5 - bb_pct) / 2
        bb_score = _clamp(bb_score, -1, 1)

        # --- 5. Volume ---
        vol_ratio = indicators["volume_ratio"]
        vol_multiplier = _clamp(vol_ratio / 2, 0.3, 2.0)

        # --- 6. Order book (10%) ---
        imbalance = orderbook.get("imbalance_ratio", 0.5)
        ob_score = _clamp((imbalance - 0.5) * 3, -1, 1)

        # --- Combinaison pondérée (v2) ---
        raw = (
            trend_score * 0.30
            + rsi_score * 0.25
            + macd_score * 0.20
            + bb_score * 0.15
            + ob_score * 0.10
        )

        # --- Bonus de confluence ---
        components = [trend_score, rsi_score, macd_score, bb_score, ob_score]
        bullish = sum(1 for c in components if c > 0.1)
        bearish = sum(1 for c in components if c < -0.1)
        agreement = max(bullish, bearish)

        if agreement >= 5:
            confluence = 2.0
        elif agreement >= 4:
            confluence = 1.5
        elif agreement >= 3:
            confluence = 1.2
        else:
            confluence = 1.0

        total = raw * vol_multiplier * confluence
        return _clamp(total, -1, 1)

    # ─── Classification du signal ─────────────────────────────────────

    def classify_signal(
        self, pair: str, indicators: dict[str, float], score: float
    ) -> dict[str, Any]:
        """Classifie un signal en SCALP / MOMENTUM / NO_SIGNAL.

        - SCALP utilise RSI 9 (réactif) et est limité à BTC/ETH/SOL.
        - MOMENTUM utilise le score composite (basé sur RSI 14) sur toutes les paires.
        """
        rsi_9 = indicators["rsi_9"]
        bb_pct = indicators["bb_pct"]
        volume_ratio = indicators["volume_ratio"]

        # Mode SCALP : uniquement sur les paires liquides
        if pair in SCALP_PAIRS:
            # SCALP LONG : RSI 9 oversold ou prix sous Bollinger basse
            if (rsi_9 <= SCALP_RSI_OVERSOLD or bb_pct <= SCALP_BB_LOWER) and volume_ratio >= SCALP_MIN_VOLUME:
                return {
                    "mode": "SCALP_LONG",
                    "urgency": "HIGH",
                    **SCALP_CONFIG,
                }

            # SCALP SHORT EXIT : RSI 9 overbought ou prix au-dessus Bollinger haute
            if (rsi_9 >= SCALP_RSI_OVERBOUGHT or bb_pct >= SCALP_BB_UPPER) and volume_ratio >= SCALP_MIN_VOLUME:
                return {
                    "mode": "SCALP_SHORT_EXIT",
                    "urgency": "HIGH",
                    "target_action": "SELL_IF_HOLDING",
                }

        # Mode MOMENTUM : score composite fort (toutes paires)
        if pair in MOMENTUM_PAIRS and abs(score) >= MOMENTUM_THRESHOLD:
            direction = "LONG" if score > 0 else "EXIT"
            return {
                "mode": f"MOMENTUM_{direction}",
                "urgency": "MEDIUM",
                **MOMENTUM_CONFIG,
            }

        return {"mode": "NO_SIGNAL"}

    # ─── Analyse complète ─────────────────────────────────────────────

    async def analyze(
        self, pair: str, df: pd.DataFrame, orderbook: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Analyse une paire et publie un signal si intéressant.

        Publie si : conditions SCALP remplies OU |score| >= signal_threshold.
        """
        indicators = self.compute_indicators(df)
        if indicators is None:
            return None

        score = self.compute_score(indicators, orderbook)

        # Vérifier si un signal SCALP ou MOMENTUM est possible
        classification = self.classify_signal(pair, indicators, score)
        has_signal = classification["mode"] != "NO_SIGNAL"

        # Publier aussi sur seuil bas pour ne pas rater les scalps
        if has_signal or abs(score) >= self.signal_threshold:
            result = {
                "pair": pair,
                "score": round(score, 4),
                "indicators": indicators,
                "orderbook": orderbook,
            }
            await self.publish("signal", result)
            logger.info(
                "Signal {} — mode={} score={:.3f} (RSI9={:.0f} RSI14={:.0f} MACD_h={:.4f} BB%={:.2f})",
                pair, classification["mode"], score,
                indicators["rsi_9"],
                indicators["rsi_14"],
                indicators["macd_histogram"],
                indicators["bb_pct"],
            )
            return result

        return {"pair": pair, "score": round(score, 4), "indicators": indicators, "orderbook": orderbook}


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
