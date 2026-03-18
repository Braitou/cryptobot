"""RegimeDetector — Détecte le régime de marché via ADX + EMA slope sur candles 1H.

Tourne toutes les 15 minutes. Aucun appel IA. 100% Python.
4 régimes : RANGING, TRENDING_UP, TRENDING_DOWN, HIGH_VOLATILITY.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import ta

from backend.utils.logger import logger


class RegimeDetector:
    """Classifie le régime de marché à partir des candles 1H."""

    # Hystérésis ADX : entrer en trend à 28, revenir en range à 20
    ADX_TREND_ENTER = 28
    ADX_TREND_EXIT = 20

    # Seuil de haute volatilité : ATR actuel > 1.5× la moyenne
    HIGH_VOL_ATR_RATIO = 1.5

    # Cooldown : pas de changement de régime plus fréquent que 1h
    REGIME_COOLDOWN_MINUTES = 60

    def __init__(self) -> None:
        self.current_regime: str = "RANGING"
        self.last_change_time: datetime | None = None

    def detect(self, candles_1h: pd.DataFrame) -> str:
        """Analyse les candles 1H et retourne le régime actuel.

        candles_1h : DataFrame avec colonnes high, low, close (minimum 30 lignes).
        """
        if len(candles_1h) < 30:
            logger.warning("RegimeDetector: pas assez de candles 1H ({}/30)", len(candles_1h))
            return self.current_regime

        high = candles_1h["high"]
        low = candles_1h["low"]
        close = candles_1h["close"]

        # ADX 14
        adx_indicator = ta.trend.ADXIndicator(high, low, close, window=14)
        adx = adx_indicator.adx().iloc[-1]

        # EMA 20 slope (pente sur les 5 dernières valeurs)
        ema_20 = ta.trend.EMAIndicator(close, window=20).ema_indicator()
        ema_slope = self._ema_slope(ema_20)

        # ATR ratio : ATR actuel vs moyenne sur 168h (1 semaine)
        atr_indicator = ta.volatility.AverageTrueRange(high, low, close, window=14)
        atr_series = atr_indicator.average_true_range()
        atr_current = atr_series.iloc[-1]
        lookback = min(168, len(atr_series))
        atr_avg = atr_series.iloc[-lookback:].mean()
        atr_ratio = atr_current / atr_avg if atr_avg > 0 else 1.0

        # Remplacer NaN par des valeurs neutres
        if np.isnan(adx):
            adx = 15.0
        if np.isnan(ema_slope):
            ema_slope = 0.0
        if np.isnan(atr_ratio):
            atr_ratio = 1.0

        new_regime = self._classify(adx, ema_slope, atr_ratio)

        # Appliquer le changement uniquement si cooldown écoulé
        if new_regime != self.current_regime:
            if self._cooldown_elapsed():
                old = self.current_regime
                self.current_regime = new_regime
                self.last_change_time = datetime.now(timezone.utc)
                logger.info(
                    "RegimeDetector: {} -> {} (ADX={:.1f} EMA_slope={:.4f} ATR_ratio={:.2f})",
                    old, new_regime, adx, ema_slope, atr_ratio,
                )
            else:
                logger.debug(
                    "RegimeDetector: {} détecté mais cooldown actif (reste en {})",
                    new_regime, self.current_regime,
                )

        return self.current_regime

    def _classify(self, adx: float, ema_slope: float, atr_ratio: float) -> str:
        """Classifie le régime avec hystérésis sur l'ADX."""
        # Hystérésis : si déjà en trend, rester tant que ADX >= 20
        # Si pas en trend, entrer seulement si ADX > 28
        is_trending = (
            (self.current_regime.startswith("TRENDING") and adx >= self.ADX_TREND_EXIT)
            or (not self.current_regime.startswith("TRENDING") and adx > self.ADX_TREND_ENTER)
        )

        if is_trending:
            if ema_slope > 0:
                return "TRENDING_UP"
            else:
                return "TRENDING_DOWN"

        # Haute volatilité (vérifié APRÈS le trend pour gérer trend + high vol)
        if atr_ratio > self.HIGH_VOL_ATR_RATIO:
            return "HIGH_VOLATILITY"

        return "RANGING"

    def _cooldown_elapsed(self) -> bool:
        """Vérifie si le cooldown entre changements de régime est écoulé."""
        if self.last_change_time is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self.last_change_time).total_seconds() / 60
        return elapsed >= self.REGIME_COOLDOWN_MINUTES

    @staticmethod
    def _ema_slope(ema_series: pd.Series, lookback: int = 5) -> float:
        """Calcule la pente normalisée de l'EMA sur les N dernières valeurs."""
        if len(ema_series) < lookback:
            return 0.0
        recent = ema_series.iloc[-lookback:]
        first = recent.iloc[0]
        last = recent.iloc[-1]
        if first == 0:
            return 0.0
        return (last - first) / first

    @property
    def regime_info(self) -> dict[str, Any]:
        """Retourne les infos du régime pour le logging/dashboard."""
        return {
            "regime": self.current_regime,
            "last_change": self.last_change_time.isoformat() if self.last_change_time else None,
        }
