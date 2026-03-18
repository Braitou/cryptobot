"""CorrelationGuard — Limite l'exposition corrélée totale.

En crypto, toutes les paires majeures sont fortement corrélées.
On traite donc tous les longs ouverts comme un seul bloc de risque.
Si l'exposition totale dépasse le seuil → on bloque les nouvelles positions.

100% Python, aucun appel IA.
"""

from __future__ import annotations

from typing import Any

from backend.utils.logger import logger


class CorrelationGuard:
    """Vérifie que l'exposition corrélée ne dépasse pas le seuil."""

    MAX_CORRELATED_EXPOSURE_PCT = 15.0  # 15% du capital max en positions long

    def __init__(self, max_exposure_pct: float = 15.0) -> None:
        self.MAX_CORRELATED_EXPOSURE_PCT = max_exposure_pct

    def check(
        self, open_positions: list[dict[str, Any]], capital: float
    ) -> tuple[bool, str]:
        """Vérifie l'exposition corrélée.

        open_positions : liste de dicts avec au minimum 'side', 'entry_price', 'quantity'.
        capital : capital total en USDT.

        Retourne (True, "OK") si on peut ouvrir, (False, reason) sinon.
        """
        if capital <= 0:
            return False, "Capital <= 0"

        long_exposure = 0.0
        for pos in open_positions:
            if pos.get("side") == "BUY":
                entry_price = pos.get("entry_price", 0)
                quantity = pos.get("quantity", 0)
                long_exposure += entry_price * quantity

        exposure_pct = (long_exposure / capital) * 100

        if exposure_pct > self.MAX_CORRELATED_EXPOSURE_PCT:
            reason = (
                f"Exposition corrélée {exposure_pct:.1f}% > max {self.MAX_CORRELATED_EXPOSURE_PCT:.0f}%"
            )
            logger.warning("CorrelationGuard REJET: {}", reason)
            return False, reason

        logger.debug("CorrelationGuard OK: exposition {:.1f}%", exposure_pct)
        return True, "OK"
