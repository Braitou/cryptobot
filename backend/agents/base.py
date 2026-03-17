"""BaseAgent et AgentMessage — socle commun à tous les agents."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AgentMessage:
    """Message circulant sur le bus interne (asyncio.Queue)."""

    type: str  # ex: "candle_closed", "signal", "order_executed"
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""  # nom de l'agent émetteur
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BaseAgent:
    """Classe de base pour tous les agents (Python ou IA)."""

    name: str = "base"

    def __init__(self, bus: asyncio.Queue[AgentMessage] | None = None) -> None:
        self.bus = bus
        self.state = AgentState.IDLE
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Lancement de l'agent — à surcharger si boucle continue."""
        self.state = AgentState.RUNNING

    async def stop(self) -> None:
        """Arrêt propre."""
        self.state = AgentState.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()

    async def publish(self, msg_type: str, data: dict[str, Any] | None = None) -> None:
        """Publie un message sur le bus."""
        if self.bus is None:
            return
        msg = AgentMessage(type=msg_type, data=data or {}, source=self.name)
        await self.bus.put(msg)
