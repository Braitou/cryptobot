"""Configuration centralisée — charge .env via Pydantic Settings."""

from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Toutes les valeurs sont lues depuis .env (ou variables d'environnement)."""

    # --- Binance ---
    BINANCE_API_KEY: str
    BINANCE_API_SECRET: str
    BINANCE_TESTNET: bool = True

    # --- Trading ---
    PAIRS: str = "BTCUSDT,ETHUSDT,SOLUSDT,AVAXUSDT,LINKUSDT"
    CANDLE_INTERVALS: str = "1m,5m,15m"
    TRADING_MODE: Literal["paper", "live"] = "paper"
    INITIAL_CAPITAL: float = 500.0

    # --- Signal Analyzer ---
    SIGNAL_THRESHOLD: float = 0.20

    # --- Risk Guard (limites dures Python) ---
    MAX_POSITION_PCT: float = 0.10
    MAX_OPEN_POSITIONS: int = 5
    MAX_POSITIONS_PER_PAIR: int = 1
    MAX_DAILY_LOSS_PCT: float = 0.03
    MAX_TOTAL_DRAWDOWN_PCT: float = 0.15
    # Caps SL/TP par mode
    SCALP_MAX_SL_PCT: float = 0.5
    SCALP_MAX_TP_PCT: float = 1.0
    MOMENTUM_MAX_SL_PCT: float = 2.0
    MOMENTUM_MAX_TP_PCT: float = 3.0
    # Trailing stop (basé sur %) — v3 : élargi pour laisser le trade respirer
    # Bruit normal candle 5m BTC = 0.1-0.2%, trailing à 0.15% se fait sortir par le bruit
    TRAILING_STOP_ACTIVATION_PCT: float = 0.6
    TRAILING_STOP_DISTANCE_PCT: float = 0.3
    # Cooldown après SL
    PAIR_COOLDOWN_AFTER_SL_MINUTES: int = 15
    # Legacy ATR (backward compat)
    STOP_LOSS_ATR_MULT: float = 1.5
    TAKE_PROFIT_ATR_MULT: float = 2.0
    TRAILING_STOP_ATR_MULT: float = 1.0

    # --- Claude API ---
    ANTHROPIC_API_KEY: str
    AI_MODEL_FAST: str = "claude-haiku-4-5-20251001"
    AI_MODEL_DEEP: str = "claude-sonnet-4-6"
    AI_MAX_TOKENS: int = 1024
    AI_TEMPERATURE: float = 0.3

    # --- API Dashboard ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @cached_property
    def pairs_list(self) -> list[str]:
        return [s.strip() for s in self.PAIRS.split(",") if s.strip()]

    @cached_property
    def candle_intervals_list(self) -> list[str]:
        return [s.strip() for s in self.CANDLE_INTERVALS.split(",") if s.strip()]


def get_settings() -> Settings:
    """Factory — appeler une seule fois au démarrage, puis réutiliser l'instance."""
    return Settings()  # type: ignore[call-arg]
