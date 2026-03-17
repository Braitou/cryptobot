"""Loguru configuration — utilisé par tous les modules."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

# Supprimer le handler par défaut (stderr basique)
logger.remove()

# --- Console (coloré, lisible) ---
logger.add(
    sys.stderr,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    ),
    level="DEBUG",
    colorize=True,
)

# --- Fichier rotatif (logs/cryptobot.log) ---
_log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)

logger.add(
    str(_log_dir / "cryptobot.log"),
    rotation="10 MB",
    retention="7 days",
    compression="gz",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} — {message}",
    level="DEBUG",
)

# --- Fichier erreurs séparé ---
logger.add(
    str(_log_dir / "errors.log"),
    rotation="5 MB",
    retention="30 days",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} — {message}",
)

__all__ = ["logger"]
