"""RiskGuard v2 — Filet de sécurité Python pur. INVIOLABLE.

Aucun agent IA ne peut contourner ces limites.
Si une règle est violée → rejet immédiat, pas de discussion.
Calibré pour du scalping (petites positions, SL/TP serrés).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
        max_open_positions: int = 5,
        max_positions_per_pair: int = 1,
        max_daily_loss_pct: float = 0.03,
        max_total_drawdown_pct: float = 0.15,
        # Caps SL/TP par mode
        scalp_max_sl_pct: float = 0.5,
        scalp_max_tp_pct: float = 1.0,
        momentum_max_sl_pct: float = 2.0,
        momentum_max_tp_pct: float = 3.0,
        # Trailing stop (basé sur %)
        trailing_stop_activation_pct: float = 0.3,
        trailing_stop_distance_pct: float = 0.15,
        # Cooldown après SL
        pair_cooldown_after_sl_minutes: int = 15,
        # Legacy ATR params (gardés pour compute_quantity)
        stop_loss_atr_mult: float = 1.5,
        take_profit_atr_mult: float = 2.0,
        trailing_stop_atr_mult: float = 1.0,
    ) -> None:
        self.max_position_pct = max_position_pct
        self.max_open_positions = max_open_positions
        self.max_positions_per_pair = max_positions_per_pair
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_total_drawdown_pct = max_total_drawdown_pct

        # Caps SL/TP
        self.scalp_max_sl_pct = scalp_max_sl_pct
        self.scalp_max_tp_pct = scalp_max_tp_pct
        self.momentum_max_sl_pct = momentum_max_sl_pct
        self.momentum_max_tp_pct = momentum_max_tp_pct

        # Trailing stop
        self.trailing_stop_activation_pct = trailing_stop_activation_pct
        self.trailing_stop_distance_pct = trailing_stop_distance_pct

        # Cooldown
        self.pair_cooldown_after_sl_minutes = pair_cooldown_after_sl_minutes
        self._pair_cooldowns: dict[str, datetime] = {}

        # Legacy (keep for backward compat)
        self.stop_loss_atr_mult = stop_loss_atr_mult
        self.take_profit_atr_mult = take_profit_atr_mult
        self.trailing_stop_atr_mult = trailing_stop_atr_mult

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

        # 3. Cooldown par paire après SL
        pair = decision.get("pair", "")
        if pair in self._pair_cooldowns:
            cooldown_until = self._pair_cooldowns[pair]
            now = datetime.now(timezone.utc)
            if now < cooldown_until:
                remaining = (cooldown_until - now).total_seconds() / 60
                violations.append(
                    f"Cooldown actif sur {pair} — encore {remaining:.0f}min après SL"
                )

        # 4. Position size > MAX_POSITION_PCT
        if position_size_pct > self.max_position_pct:
            violations.append(
                f"Position {position_size_pct:.1%} > max {self.max_position_pct:.1%}"
            )

        # 5. Trop de positions ouvertes (total)
        if open_pos >= self.max_open_positions:
            violations.append(
                f"Positions ouvertes ({open_pos}) >= max ({self.max_open_positions})"
            )

        # 5b. Trop de positions sur cette paire
        pair_positions = portfolio.get("pair_positions", 0)
        if pair_positions >= self.max_positions_per_pair:
            violations.append(
                f"Positions sur {pair} ({pair_positions}) >= max par paire ({self.max_positions_per_pair})"
            )

        # 6. Perte journalière
        if abs(daily_pnl_pct) >= self.max_daily_loss_pct and daily_pnl_pct < 0:
            self._daily_kill = True
            violations.append(
                f"Perte jour ({daily_pnl_pct:.1%}) >= max ({self.max_daily_loss_pct:.1%}) — KILL SWITCH JOUR activé"
            )

        # 7. Drawdown total
        if drawdown_pct >= self.max_total_drawdown_pct:
            self._total_kill = True
            violations.append(
                f"Drawdown ({drawdown_pct:.1%}) >= max ({self.max_total_drawdown_pct:.1%}) — KILL SWITCH TOTAL activé"
            )

        # 8. Stop-loss obligatoire
        if not decision.get("stop_loss"):
            violations.append("Stop-loss absent — OBLIGATOIRE")

        # 9. Take-profit obligatoire
        if not decision.get("take_profit"):
            violations.append("Take-profit absent — OBLIGATOIRE")

        # 10. Montant minimum Binance (~5 USDT)
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

    # ─── Cooldown management ─────────────────────────────────────────

    def register_stop_loss(self, pair: str) -> None:
        """Enregistre un cooldown sur une paire après un stop-loss."""
        from datetime import timedelta
        cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=self.pair_cooldown_after_sl_minutes)
        self._pair_cooldowns[pair] = cooldown_until
        logger.info("RiskGuard — cooldown {} actif jusqu'à {}", pair, cooldown_until.isoformat())

    def clear_expired_cooldowns(self) -> None:
        """Nettoie les cooldowns expirés."""
        now = datetime.now(timezone.utc)
        expired = [p for p, until in self._pair_cooldowns.items() if now >= until]
        for p in expired:
            del self._pair_cooldowns[p]

    # ─── Calculs SL/TP ────────────────────────────────────────────────

    def compute_quantity(self, capital: float, position_size_pct: float, price: float) -> float:
        """Calcule la quantité à acheter/vendre."""
        if price <= 0:
            return 0.0
        usdt_amount = capital * position_size_pct
        return round(usdt_amount / price, 6)

    def check_trailing_stop(
        self, entry_price: float, side: str, current_price: float, highest_since_entry: float
    ) -> bool:
        """Vérifie si le trailing stop doit déclencher la fermeture.

        Basé sur % (v3) : activation à +0.6% de profit, suit à 0.3% du high.
        Retourne True si on doit fermer.
        """
        activation = entry_price * self.trailing_stop_activation_pct / 100
        distance = highest_since_entry * self.trailing_stop_distance_pct / 100

        if side == "BUY":
            max_profit = highest_since_entry - entry_price
            if max_profit < activation:
                return False
            trailing_stop = highest_since_entry - distance
            return current_price <= trailing_stop
        else:  # SELL
            max_profit = entry_price - highest_since_entry
            if max_profit < activation:
                return False
            trailing_stop = highest_since_entry + distance
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
