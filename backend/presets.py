"""Presets par régime de marché — codés en dur, NON modifiables par l'IA.

Chaque preset définit les paramètres de trading pour un régime donné.
Les TP/SL sont en multiples d'ATR 5min (pas en pourcentages fixes).
Seul le développeur modifie ce fichier.
"""

from __future__ import annotations

REGIME_PRESETS: dict[str, dict] = {
    # ─── RANGING : scalp mean reversion, pas de momentum ──────────
    "RANGING": {
        "scalp_enabled": True,
        "scalp_pairs": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "scalp_rsi_period": 9,
        "scalp_rsi_threshold": 28,
        "scalp_rsi_overbought": 72,
        "scalp_bb_threshold": 0.15,
        "scalp_bb_upper_threshold": 0.85,
        "scalp_min_volume_ratio": 0.8,
        "scalp_tp_atr_mult": 2.0,
        "scalp_sl_atr_mult": 1.0,
        "scalp_trailing_activation_atr": 1.5,
        "scalp_trailing_distance_atr": 1.0,
        "scalp_position_size_pct": 5.0,
        "scalp_max_hold_minutes": 30,
        "momentum_enabled": False,
    },

    # ─── TRENDING UP : momentum uniquement, pas de scalp ──────────
    "TRENDING_UP": {
        "scalp_enabled": False,
        "momentum_enabled": True,
        "momentum_pairs": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT"],
        "momentum_min_score": 0.45,
        "momentum_tp_atr_mult": 3.0,
        "momentum_sl_atr_mult": 1.5,
        "momentum_trailing_activation_atr": 2.0,
        "momentum_trailing_distance_atr": 1.0,
        "momentum_position_size_pct": 8.0,
        "momentum_max_hold_minutes": 240,
    },

    # ─── TRENDING DOWN : scalp ultra-strict pour collecter des données ─
    # En shadow trading : scalp activé pour apprendre
    # En live : passer scalp_enabled à False
    "TRENDING_DOWN": {
        "scalp_enabled": True,  # SHADOW MODE — passer à False en live
        "scalp_pairs": ["BTCUSDT", "ETHUSDT"],  # Seulement les plus liquides
        "scalp_rsi_period": 9,
        "scalp_rsi_threshold": 20,  # Ultra-strict : survente profonde uniquement
        "scalp_rsi_overbought": 80,
        "scalp_bb_threshold": 0.05,
        "scalp_bb_upper_threshold": 0.95,
        "scalp_min_volume_ratio": 1.5,  # Volume élevé requis
        "scalp_tp_atr_mult": 2.5,
        "scalp_sl_atr_mult": 1.0,
        "scalp_trailing_activation_atr": 2.0,
        "scalp_trailing_distance_atr": 1.0,
        "scalp_position_size_pct": 2.0,  # Petites positions
        "scalp_max_hold_minutes": 10,  # Sortie très rapide
        "momentum_enabled": False,
    },

    # ─── HIGH VOLATILITY : scalp avec seuils stricts et petites positions ─
    "HIGH_VOLATILITY": {
        "scalp_enabled": True,
        "scalp_pairs": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "scalp_rsi_period": 9,
        "scalp_rsi_threshold": 25,
        "scalp_rsi_overbought": 75,
        "scalp_bb_threshold": 0.05,
        "scalp_bb_upper_threshold": 0.95,
        "scalp_min_volume_ratio": 1.0,
        "scalp_tp_atr_mult": 2.5,
        "scalp_sl_atr_mult": 1.5,
        "scalp_trailing_activation_atr": 2.0,
        "scalp_trailing_distance_atr": 1.5,
        "scalp_position_size_pct": 3.0,
        "scalp_max_hold_minutes": 15,
        "momentum_enabled": False,
    },
}


def get_preset(regime: str) -> dict:
    """Retourne le preset pour un régime donné. Fallback sur RANGING."""
    return REGIME_PRESETS.get(regime, REGIME_PRESETS["RANGING"])
