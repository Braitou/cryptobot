"""RiskGuard — Filet de sécurité Python pur. INVIOLABLE.

Aucun agent IA ne peut contourner ces limites.
Si une règle est violée → rejet immédiat, pas de discussion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.utils.logger import logger


@dataclass
class RiskCheckResult:
    """Résultat d'un check du Risk Guard."""

    approved: bool
    reason: str = ""
    violations: list[str] = field(default_factory=list)


class RiskGuard:
    """Vérifications binaires. Pas de raisonnement, pas d'IA."""

    def __init__(
        self,
        max_position_pct: float = 0.10,
        stop_loss_atr_mult: float = 1.5,
        take_profit_atr_mult: float = 2.0,
        trailing_stop_atr_mult: float = 1.0,
        max_open_positions: int = 3,
        max_positions_per_pair: int = 2,
        max_daily_loss_pct: float = 0.03,
        max_total_drawdown_pct: float = 0.15,
    ) -> None:
        self.max_position_pct = max_position_pct
        self.stop_loss_atr_mult = stop_loss_atr_mult
        self.take_profit_atr_mult = take_profit_atr_mult
        self.trailing_stop_atr_mult = trailing_stop_atr_mult
        self.max_open_positions = max_open_positions
        self.max_positions_per_pair = max_positions_per_pair
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_total_drawdown_pct = max_total_drawdown_pct

        # Kill switches
        self._daily_kill: bool = False
        self._total_kill: bool = False

    # ─── Check principal ──────────────────────────────────────────────

    def check(self, decision: dict[str, Any], portfolio: dict[str, Any]) -> RiskCheckResult:
        """Séquence de vérification (court-circuit au premier refus).

        decision: action, position_size_pct, stop_loss, take_profit, quantity
        portfolio: capital, open_positions, daily_pnl_pct, drawdown_pct
        """
        violations: list[str] = []

        # 1. Kill switch total
        if self._total_kill:
            return RiskCheckResult(False, "KILL SWITCH TOTAL actif — trading arrêté", ["kill_switch_total"])

        # 2. Kill switch journalier
        if self._daily_kill:
            return RiskCheckResult(False, "KILL SWITCH JOUR actif — reprend demain", ["kill_switch_daily"])

        capital = portfolio.get("capital", 0)
        open_pos = portfolio.get("open_positions", 0)
        daily_pnl_pct = portfolio.get("daily_pnl_pct", 0)
        drawdown_pct = portfolio.get("drawdown_pct", 0)
        position_size_pct = decision.get("position_size_pct", 0)

        # 3. Position size > MAX_POSITION_PCT
        if position_size_pct > self.max_position_pct:
            violations.append(
                f"Position {position_size_pct:.1%} > max {self.max_position_pct:.1%}"
            )

        # 4. Trop de positions ouvertes (total)
        if open_pos >= self.max_open_positions:
            violations.append(
                f"Positions ouvertes ({open_pos}) >= max ({self.max_open_positions})"
            )

        # 4b. Trop de positions sur cette paire
        pair_positions = portfolio.get("pair_positions", 0)
        pair = decision.get("pair", "")
        if pair_positions >= self.max_positions_per_pair:
            violations.append(
                f"Positions sur {pair} ({pair_positions}) >= max par paire ({self.max_positions_per_pair})"
            )

        # 5. Perte journalière
        if abs(daily_pnl_pct) >= self.max_daily_loss_pct and daily_pnl_pct < 0:
            self._daily_kill = True
            violations.append(
                f"Perte jour ({daily_pnl_pct:.1%}) >= max ({self.max_daily_loss_pct:.1%}) — KILL SWITCH JOUR activé"
            )

        # 6. Drawdown total
        if drawdown_pct >= self.max_total_drawdown_pct:
            self._total_kill = True
            violations.append(
                f"Drawdown ({drawdown_pct:.1%}) >= max ({self.max_total_drawdown_pct:.1%}) — KILL SWITCH TOTAL activé"
            )

        # 7. Stop-loss obligatoire
        if not decision.get("stop_loss"):
            violations.append("Stop-loss absent — OBLIGATOIRE")

        # 8. Take-profit obligatoire
        if not decision.get("take_profit"):
            violations.append("Take-profit absent — OBLIGATOIRE")

        # 9. Montant minimum Binance (~5 USDT)
        quantity = decision.get("quantity", 0)
        price = decision.get("entry_price", 0)
        notional = quantity * price if quantity and price else position_size_pct * capital
        if notional < 5.0:
            violations.append(f"Montant ({notional:.2f} USDT) < minimum Binance (5 USDT)")

        if violations:
            for v in violations:
                logger.warning("RiskGuard REJET : {}", v)
            return RiskCheckResult(False, violations[0], violations)

        logger.info("RiskGuard APPROUVÉ — position {:.1%} du capital", position_size_pct)
        return RiskCheckResult(True)

    # ─── Calculs SL/TP ────────────────────────────────────────────────

    def _cap_atr(self, atr: float, price: float, max_pct: float = 0.03) -> float:
        """Cap l'ATR à max_pct du prix pour éviter les outliers testnet."""
        max_atr = price * max_pct
        if atr > max_atr:
            return max_atr
        return atr

    def compute_stop_loss(self, entry_price: float, side: str, atr: float) -> float:
        """BUY → entry - 1.5 × ATR | SELL → entry + 1.5 × ATR"""
        atr = self._cap_atr(atr, entry_price)
        offset = self.stop_loss_atr_mult * atr
        if side == "BUY":
            return round(entry_price - offset, 2)
        return round(entry_price + offset, 2)

    def compute_take_profit(self, entry_price: float, side: str, atr: float) -> float:
        """BUY → entry + 2.0 × ATR | SELL → entry - 2.0 × ATR"""
        atr = self._cap_atr(atr, entry_price)
        offset = self.take_profit_atr_mult * atr
        if side == "BUY":
            return round(entry_price + offset, 2)
        return round(entry_price - offset, 2)

    def compute_quantity(self, capital: float, position_size_pct: float, price: float) -> float:
        """Calcule la quantité à acheter/vendre."""
        if price <= 0:
            return 0.0
        usdt_amount = capital * position_size_pct
        return round(usdt_amount / price, 6)

    def check_trailing_stop(
        self, entry_price: float, side: str, current_price: float, atr: float, highest_since_entry: float
    ) -> bool:
        """Vérifie si le trailing stop doit déclencher la fermeture.

        Le trailing s'active quand le profit atteint 1 × ATR.
        Le stop suit à 1 × ATR du plus haut atteint.
        Retourne True si on doit fermer.
        """
        trailing_activation = self.trailing_stop_atr_mult * atr
        trailing_offset = self.trailing_stop_atr_mult * atr

        if side == "BUY":
            max_profit = highest_since_entry - entry_price
            if max_profit < trailing_activation:
                return False  # trailing jamais activé
            trailing_stop = highest_since_entry - trailing_offset
            return current_price <= trailing_stop
        else:  # SELL
            # highest_since_entry = lowest price since entry for SELL
            max_profit = entry_price - highest_since_entry
            if max_profit < trailing_activation:
                return False
            trailing_stop = highest_since_entry + trailing_offset
            return current_price >= trailing_stop

    # ─── Kill switch management ───────────────────────────────────────

    def reset_daily_kill(self) -> None:
        """Reset le kill switch journalier (appelé à minuit UTC)."""
        if self._daily_kill:
            logger.info("RiskGuard — kill switch jour reset")
        self._daily_kill = False

    def reset_total_kill(self) -> None:
        """Reset le kill switch total (action manuelle)."""
        if self._total_kill:
            logger.warning("RiskGuard — kill switch TOTAL reset manuellement")
        self._total_kill = False

    @property
    def is_killed(self) -> bool:
        return self._daily_kill or self._total_kill

    @property
    def kill_status(self) -> dict[str, bool]:
        return {"daily_kill": self._daily_kill, "total_kill": self._total_kill}
