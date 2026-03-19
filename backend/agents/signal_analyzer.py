"""SignalAnalyzer v4 — Indicateurs techniques + score composite + classification par preset.

Ne prend aucune décision. Détecte quand le marché est "intéressant",
classifie le signal (SCALP / MOMENTUM) selon le preset actif, et publie sur le bus.
TP/SL dynamiques basés sur ATR 5min (pas de % fixe).
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
        signal_threshold: float = 0.20,
        bus: asyncio.Queue | None = None,
    ) -> None:
        super().__init__(bus=bus)
        self.signal_threshold = signal_threshold

    # ─── Indicateurs techniques ───────────────────────────────────────

    def compute_indicators(self, df: pd.DataFrame) -> dict[str, float] | None:
        """Calcule tous les indicateurs sur un DataFrame de candles 5min.

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

        # ATR 14 (sur candles 5min — utilisé pour les TP/SL dynamiques)
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

        Pondérations : trend 30%, RSI 25%, MACD 20%, BB 15%, OB 10%.
        Utilise RSI 14 (pas RSI 9) — le score est pour le momentum.
        """
        # --- 1. Tendance (30%) ---
        trend_score = 0.0
        if indicators["ema_21"] > 0:
            ema_diff_pct = (indicators["ema_9"] - indicators["ema_21"]) / indicators["ema_21"]
            trend_score += _clamp(ema_diff_pct * 200, -1, 1) * 0.5
        if indicators["vwap"] > 0:
            vwap_diff_pct = (indicators["price"] - indicators["vwap"]) / indicators["vwap"]
            trend_score += _clamp(vwap_diff_pct * 200, -1, 1) * 0.5

        # --- 2. RSI 14 (25%) ---
        rsi = indicators["rsi_14"]
        if rsi <= 30:
            rsi_score = (30 - rsi) / 20
        elif rsi >= 70:
            rsi_score = (70 - rsi) / 20
        else:
            rsi_score = (50 - rsi) / 100
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

        # --- Combinaison pondérée ---
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

    # ─── Calcul dynamique TP/SL basé sur ATR ─────────────────────────

    @staticmethod
    def calculate_trade_levels(
        price: float, atr: float, preset: dict, mode: str = "scalp"
    ) -> dict[str, float]:
        """Calcule les niveaux TP/SL/trailing en fonction de l'ATR 5min et du preset.

        IMPORTANT : l'ATR utilisé est celui du timeframe 5min, pas 1H.
        Retourne les valeurs en pourcentage (ex: 0.008 = 0.8%).
        """
        if price <= 0:
            return {"take_profit_pct": 0.01, "stop_loss_pct": 0.005,
                    "trailing_activation_pct": 0.01, "trailing_distance_pct": 0.005,
                    "atr_5min_pct": 0.0}

        atr_pct = atr / price

        if mode == "scalp":
            tp_pct = atr_pct * preset.get("scalp_tp_atr_mult", 2.0)
            sl_pct = atr_pct * preset.get("scalp_sl_atr_mult", 1.0)
            trail_act = atr_pct * preset.get("scalp_trailing_activation_atr", 1.5)
            trail_dist = atr_pct * preset.get("scalp_trailing_distance_atr", 1.0)
        else:  # momentum
            tp_pct = atr_pct * preset.get("momentum_tp_atr_mult", 3.0)
            sl_pct = atr_pct * preset.get("momentum_sl_atr_mult", 1.5)
            trail_act = atr_pct * preset.get("momentum_trailing_activation_atr", 2.0)
            trail_dist = atr_pct * preset.get("momentum_trailing_distance_atr", 1.0)

        # Caps de sécurité (le Risk Guard vérifie aussi, mais double vérification)
        tp_pct = min(tp_pct, 0.03)   # Cap à 3% max
        sl_pct = min(sl_pct, 0.02)   # Cap à 2% max

        return {
            "take_profit_pct": tp_pct,
            "stop_loss_pct": sl_pct,
            "trailing_activation_pct": trail_act,
            "trailing_distance_pct": trail_dist,
            "atr_5min_pct": atr_pct,
        }

    # ─── Filtre anti-tendance 5min ────────────────────────────────────

    @staticmethod
    def scalp_entry_allowed(indicators: dict[str, float], side: str = "BUY") -> tuple[bool, str]:
        """Vérifie que le scalp n'est pas contre le micro-trend 5min.

        Même en RANGING sur 1H, un micro-trend violent sur 5min va casser le scalp.
        """
        ema_9 = indicators["ema_9"]
        ema_21 = indicators["ema_21"]

        if ema_21 == 0:
            return True, "OK"

        if side == "BUY" and ema_9 < ema_21 * 0.998:
            # EMA9 nettement sous EMA21 → micro-trend baissier → pas de long
            return False, "Micro-trend baissier 5min (EMA9 < EMA21), scalp long interdit"

        return True, "OK"

    # ─── Classification du signal (v4 — lit le preset) ────────────────

    # Seuil minimum d'ATR : en dessous, les frais fixes mangent tout le R:R
    MIN_ATR_PCT = 0.004  # 0.40% — en dessous, pas de trade

    def classify_signal(
        self, pair: str, indicators: dict[str, float], score: float,
        preset: dict,
    ) -> dict[str, Any]:
        """Classifie un signal selon le preset actif.

        Le preset définit les seuils RSI, BB, volume, et les paires autorisées.
        Les TP/SL sont calculés dynamiquement via calculate_trade_levels().
        """
        price = indicators["price"]
        atr = indicators["atr_14"]

        # Filtre ATR minimum : volatilité trop basse → frais > gains potentiels
        atr_pct = atr / price if price > 0 else 0
        if atr_pct < self.MIN_ATR_PCT:
            logger.debug(
                "Signal {} bloqué: ATR trop bas ({:.4f}% < {:.2f}%), frais mangeraient le R:R",
                pair, atr_pct * 100, self.MIN_ATR_PCT * 100,
            )
            return {"mode": "NO_SIGNAL"}

        # ─── SCALP ───
        if preset.get("scalp_enabled", False):
            scalp_pairs = preset.get("scalp_pairs", [])
            if pair in scalp_pairs:
                rsi_period = preset.get("scalp_rsi_period", 9)
                rsi_key = f"rsi_{rsi_period}" if f"rsi_{rsi_period}" in indicators else "rsi_9"
                rsi = indicators[rsi_key]
                bb_pct = indicators["bb_pct"]
                volume_ratio = indicators["volume_ratio"]

                rsi_threshold = preset.get("scalp_rsi_threshold", 28)
                bb_threshold = preset.get("scalp_bb_threshold", 0.15)
                min_volume = preset.get("scalp_min_volume_ratio", 0.8)
                rsi_overbought = preset.get("scalp_rsi_overbought", 72)
                bb_upper = preset.get("scalp_bb_upper_threshold", 0.85)

                # SCALP LONG
                if (rsi <= rsi_threshold or bb_pct <= bb_threshold) and volume_ratio >= min_volume:
                    # Filtre anti-tendance 5min
                    allowed, reason = self.scalp_entry_allowed(indicators, "BUY")
                    if not allowed:
                        logger.info("Scalp LONG {} bloqué: {}", pair, reason)
                        return {"mode": "NO_SIGNAL", "filter_reason": "micro_trend"}
                    else:
                        levels = self.calculate_trade_levels(price, atr, preset, "scalp")
                        return {
                            "mode": "SCALP_LONG",
                            "urgency": "HIGH",
                            "position_size_pct": preset.get("scalp_position_size_pct", 5.0),
                            "max_hold_minutes": preset.get("scalp_max_hold_minutes", 30),
                            **levels,
                        }

                # SCALP SHORT EXIT
                if (rsi >= rsi_overbought or bb_pct >= bb_upper) and volume_ratio >= min_volume:
                    return {
                        "mode": "SCALP_SHORT_EXIT",
                        "urgency": "HIGH",
                        "target_action": "SELL_IF_HOLDING",
                    }

        # ─── MOMENTUM ───
        if preset.get("momentum_enabled", False):
            momentum_pairs = preset.get("momentum_pairs", [])
            min_score = preset.get("momentum_min_score", 0.45)

            if pair in momentum_pairs and abs(score) >= min_score:
                direction = "LONG" if score > 0 else "EXIT"
                levels = self.calculate_trade_levels(price, atr, preset, "momentum")
                return {
                    "mode": f"MOMENTUM_{direction}",
                    "urgency": "MEDIUM",
                    "position_size_pct": preset.get("momentum_position_size_pct", 8.0),
                    "max_hold_minutes": preset.get("momentum_max_hold_minutes", 240),
                    **levels,
                }

        return {"mode": "NO_SIGNAL"}

    # ─── Analyse complète ─────────────────────────────────────────────

    async def analyze(
        self, pair: str, df: pd.DataFrame, orderbook: dict[str, Any],
        preset: dict | None = None,
    ) -> dict[str, Any] | None:
        """Analyse une paire et publie un signal si intéressant.

        preset : le preset actif du régime courant. Si None, utilise un preset RANGING par défaut.
        """
        from backend.presets import get_preset

        if preset is None:
            preset = get_preset("RANGING")

        indicators = self.compute_indicators(df)
        if indicators is None:
            return None

        score = self.compute_score(indicators, orderbook)

        classification = self.classify_signal(pair, indicators, score, preset)
        has_signal = classification["mode"] != "NO_SIGNAL"

        if has_signal or abs(score) >= self.signal_threshold:
            result = {
                "pair": pair,
                "score": round(score, 4),
                "indicators": indicators,
                "orderbook": orderbook,
            }
            await self.publish("signal", result)
            logger.info(
                "Signal {} — mode={} score={:.3f} (RSI9={:.0f} RSI14={:.0f} BB%={:.2f} ATR={:.2f})",
                pair, classification["mode"], score,
                indicators["rsi_9"],
                indicators["rsi_14"],
                indicators["bb_pct"],
                indicators["atr_14"],
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
