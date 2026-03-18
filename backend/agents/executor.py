"""OrderExecutor — Passe les ordres (paper ou live)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.agents.base import BaseAgent
from backend.storage.database import Database
from backend.utils.binance_client import BinanceClient
from backend.utils.logger import logger


@dataclass
class ExecutionResult:
    success: bool
    trade_id: int | None = None
    entry_price: float = 0.0
    quantity: float = 0.0
    fees: float = 0.0
    error: str = ""


class OrderExecutor(BaseAgent):
    """Exécute les ordres — paper trading ou live.

    SPOT UNIQUEMENT — jamais de futures/margin/levier.
    """

    name = "executor"

    # Slippage différencié par liquidité
    SLIPPAGE_MAJOR = 0.0003   # 0.03% pour BTC/ETH/SOL
    SLIPPAGE_MINOR = 0.0005   # 0.05% pour LINK/AVAX
    MAJOR_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    # Frais simulés : 0.10% par côté (taker, sans BNB — worst case)
    # Aller-retour = 0.20%. Avec BNB discount = 0.15%.
    FEES_PCT = 0.001
    DEFAULT_TIMEOUT_S = 90 * 60  # 1h30 fallback si max_hold_minutes absent

    def _get_slippage(self, pair: str) -> float:
        """Retourne le slippage simulé selon la liquidité de la paire."""
        return self.SLIPPAGE_MAJOR if pair in self.MAJOR_PAIRS else self.SLIPPAGE_MINOR

    def __init__(
        self,
        binance: BinanceClient,
        db: Database,
        trading_mode: str = "paper",
        bus: asyncio.Queue | None = None,
        risk_guard: Any = None,
    ) -> None:
        super().__init__(bus=bus)
        self.binance = binance
        self.db = db
        self.trading_mode = trading_mode
        self.risk_guard = risk_guard
        self._monitor_task: asyncio.Task | None = None

    async def start(self) -> None:
        await super().start()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Executor démarré — mode {}", self.trading_mode)

    async def stop(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        await super().stop()

    # ─── Exécution ────────────────────────────────────────────────────

    async def execute(self, decision: dict[str, Any]) -> ExecutionResult:
        """Exécute un trade.

        Séquence :
        1. Log dans SQLite (status='pending')
        2. Paper → prix actuel + slippage, fees simulées
        3. Update SQLite (status='open')
        4. Publie 'order_executed' sur le bus
        """
        pair = decision["pair"]
        side = decision["action"]
        quantity = decision["quantity"]
        stop_loss = decision["stop_loss"]
        take_profit = decision["take_profit"]

        now = datetime.now(timezone.utc).isoformat()

        # 1. Log pending
        trade_mode = decision.get("trade_mode", "UNKNOWN")
        cursor = await self.db.execute(
            """INSERT INTO trades
               (pair, side, entry_price, quantity, entry_time, stop_loss, take_profit,
                status, signal_score, market_analysis, decision_reasoning,
                risk_evaluation, indicators_snapshot)
               VALUES (?, ?, 0, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
            (
                pair, side, quantity, now, stop_loss, take_profit,
                decision.get("signal_score"),
                trade_mode,  # Stocke le mode (SCALP_AUTO / MOMENTUM_IA) dans market_analysis
                decision.get("decision_reasoning"),
                decision.get("risk_evaluation"),
                json.dumps(decision.get("indicators_snapshot", {})),
            ),
        )
        trade_id = cursor.lastrowid

        try:
            if self.trading_mode == "paper":
                result = await self._execute_paper(trade_id, pair, side, quantity)
            else:
                result = await self._execute_live(trade_id, pair, side, quantity)
        except Exception as e:
            logger.error("Executor ERREUR trade #{}: {}", trade_id, e)
            await self.db.execute(
                "UPDATE trades SET status = 'error' WHERE id = ?", (trade_id,)
            )
            return ExecutionResult(success=False, trade_id=trade_id, error=str(e))

        # 3. Update open (+ highest_since_entry + max_hold_minutes)
        max_hold = decision.get("max_hold_minutes")
        await self.db.execute(
            """UPDATE trades SET entry_price = ?, quantity = ?, fees_paid = ?, status = 'open',
               highest_since_entry = ?, max_hold_minutes = ?
               WHERE id = ?""",
            (result.entry_price, result.quantity, result.fees,
             result.entry_price, max_hold, trade_id),
        )

        result.trade_id = trade_id

        # 4. Publish
        await self.publish("order_executed", {
            "trade_id": trade_id,
            "pair": pair,
            "side": side,
            "entry_price": result.entry_price,
            "quantity": result.quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        })

        logger.info(
            "Trade #{} OUVERT — {} {} {:.6f} @ {:.2f} (SL={:.2f} TP={:.2f}) [{}]",
            trade_id, side, pair, result.quantity, result.entry_price,
            stop_loss, take_profit, self.trading_mode,
        )
        return result

    async def _execute_paper(
        self, trade_id: int, pair: str, side: str, quantity: float
    ) -> ExecutionResult:
        """Paper trading : prix actuel + slippage simulé (différencié par paire)."""
        price = await self.binance.get_price(pair)
        slippage = self._get_slippage(pair)

        # Slippage : BUY → prix légèrement plus haut, SELL → plus bas
        if side == "BUY":
            entry_price = price * (1 + slippage)
        else:
            entry_price = price * (1 - slippage)

        fees = quantity * entry_price * self.FEES_PCT

        return ExecutionResult(
            success=True,
            entry_price=round(entry_price, 2),
            quantity=quantity,
            fees=round(fees, 4),
        )

    async def _execute_live(
        self, trade_id: int, pair: str, side: str, quantity: float
    ) -> ExecutionResult:
        """Live trading — placeholder pour Phase 8."""
        raise NotImplementedError("Live trading pas encore implémenté — utiliser mode paper")

    # ─── Monitoring des positions ouvertes ─────────────────────────────

    async def _monitor_loop(self) -> None:
        """Vérifie toutes les 5 secondes les SL/TP/trailing/timeout."""
        while True:
            try:
                await asyncio.sleep(5)
                await self.check_open_positions()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("Monitor erreur: {}", e)

    async def check_open_positions(self) -> list[int]:
        """Vérifie et ferme les positions qui doivent l'être.

        Retourne la liste des trade_ids fermés.
        """
        open_trades = await self.db.fetchall(
            "SELECT * FROM trades WHERE status = 'open'"
        )
        closed_ids = []

        for trade in open_trades:
            try:
                closed = await self._check_single_position(trade)
                if closed:
                    closed_ids.append(trade["id"])
            except Exception as e:
                logger.error("Monitor trade #{} erreur: {}", trade["id"], e)

        return closed_ids

    async def _check_single_position(self, trade: dict[str, Any]) -> bool:
        """Vérifie une position. Retourne True si fermée."""
        pair = trade["pair"]
        current_price = await self.binance.get_price(pair)
        side = trade["side"]
        entry_price = trade["entry_price"]
        stop_loss = trade["stop_loss"]
        take_profit = trade["take_profit"]

        # ── Mettre à jour highest_since_entry ──
        highest = trade.get("highest_since_entry") or entry_price
        if side == "BUY":
            new_highest = max(highest, current_price)
        else:
            new_highest = min(highest, current_price)

        if new_highest != highest:
            await self.db.execute(
                "UPDATE trades SET highest_since_entry = ? WHERE id = ?",
                (new_highest, trade["id"]),
            )

        close_reason: str | None = None

        # SL touché ?
        if side == "BUY" and current_price <= stop_loss:
            close_reason = "closed_sl"
        elif side == "SELL" and current_price >= stop_loss:
            close_reason = "closed_sl"

        # TP touché ?
        if not close_reason:
            if side == "BUY" and current_price >= take_profit:
                close_reason = "closed_tp"
            elif side == "SELL" and current_price <= take_profit:
                close_reason = "closed_tp"

        # Trailing stop
        if not close_reason and self.risk_guard:
            if self.risk_guard.check_trailing_stop(entry_price, side, current_price, new_highest):
                close_reason = "closed_trailing"
                logger.info(
                    "Trade #{} TRAILING STOP — {} highest={:.2f} current={:.2f}",
                    trade["id"], pair, new_highest, current_price,
                )

        # Timeout dynamique (max_hold_minutes du signal, sinon fallback)
        if not close_reason:
            entry_time = datetime.fromisoformat(trade["entry_time"].replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - entry_time).total_seconds()
            max_hold = trade.get("max_hold_minutes")
            timeout_s = max_hold * 60 if max_hold else self.DEFAULT_TIMEOUT_S
            if elapsed >= timeout_s:
                close_reason = "closed_timeout"

        if close_reason:
            await self._close_position(trade, current_price, close_reason)
            return True
        return False

    async def _close_position(
        self, trade: dict[str, Any], exit_price: float, reason: str
    ) -> None:
        """Ferme une position et calcule le P&L."""
        entry_price = trade["entry_price"]
        quantity = trade["quantity"]
        side = trade["side"]

        # Slippage de sortie (paper — différencié par paire)
        if self.trading_mode == "paper":
            slippage = self._get_slippage(trade["pair"])
            if side == "BUY":
                exit_price = exit_price * (1 - slippage)
            else:
                exit_price = exit_price * (1 + slippage)

        # P&L brut (avant frais)
        if side == "BUY":
            raw_pnl = (exit_price - entry_price) * quantity
        else:
            raw_pnl = (entry_price - exit_price) * quantity

        # Frais : entrée (déjà payées) + sortie
        fees_exit = quantity * exit_price * self.FEES_PCT
        total_fees = (trade.get("fees_paid", 0) or 0) + fees_exit

        # P&L net (après tous les frais aller-retour)
        pnl_net = raw_pnl - fees_exit
        notional = entry_price * quantity
        raw_pnl_pct = (raw_pnl / notional) * 100 if notional > 0 else 0
        pnl_pct = (pnl_net / notional) * 100 if notional > 0 else 0
        fee_pct = (total_fees / notional) * 100 if notional > 0 else 0

        now = datetime.now(timezone.utc).isoformat()

        await self.db.execute(
            """UPDATE trades SET exit_price = ?, exit_time = ?, status = ?,
               pnl = ?, pnl_pct = ?, fees_paid = ?
               WHERE id = ?""",
            (round(exit_price, 2), now, reason, round(pnl_net, 4), round(pnl_pct, 2), round(total_fees, 4), trade["id"]),
        )

        await self.publish("order_closed", {
            "trade_id": trade["id"],
            "pair": trade["pair"],
            "side": side,
            "entry_price": entry_price,
            "exit_price": round(exit_price, 2),
            "raw_pnl": round(raw_pnl, 4),
            "pnl": round(pnl_net, 4),
            "pnl_pct": round(pnl_pct, 2),
            "fees": round(total_fees, 4),
            "reason": reason,
        })

        # Enregistrer cooldown sur la paire si fermé par SL
        if reason == "closed_sl" and self.risk_guard:
            self.risk_guard.register_stop_loss(trade["pair"])

        logger.info(
            "Trade #{} FERMÉ — {} {} @ {:.2f} → {:.2f} | Brut={:+.2f}% Net={:+.2f}% (frais={:.2f}%) | {}",
            trade["id"], side, trade["pair"],
            entry_price, round(exit_price, 2),
            round(raw_pnl_pct, 2), round(pnl_pct, 2), round(fee_pct, 2), reason,
        )
