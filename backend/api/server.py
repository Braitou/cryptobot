"""FastAPI server — REST + WebSocket pour le dashboard."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.agents.base import AgentMessage
from backend.api.routes import create_router
from backend.config import get_settings
from backend.main import Orchestrator
from backend.utils.logger import logger


class WebSocketManager:
    """Gère les connexions WebSocket actives."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS client connecté — {} actifs", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)
        logger.info("WS client déconnecté — {} actifs", len(self._connections))

    async def broadcast(self, msg: AgentMessage) -> None:
        """Envoie un message à tous les clients connectés."""
        if not self._connections:
            return
        payload = json.dumps({"type": msg.type, "data": msg.data, "source": msg.source, "timestamp": msg.timestamp})
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


# Singletons
_orchestrator: Orchestrator | None = None
_ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown du bot."""
    global _orchestrator
    settings = get_settings()
    _orchestrator = Orchestrator(settings)
    await _orchestrator.setup()
    _orchestrator._ws_broadcast = _ws_manager.broadcast

    # Lancer le bot en tâche de fond
    bot_task = asyncio.create_task(_orchestrator.run())
    logger.info("API + Bot démarrés")
    yield

    _orchestrator._running = False
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass
    await _orchestrator.shutdown()


def create_app() -> FastAPI:
    """Factory de l'application FastAPI."""
    app = FastAPI(
        title="CryptoBot API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes REST
    router = create_router(lambda: _orchestrator)
    app.include_router(router, prefix="/api")

    # WebSocket
    @app.websocket("/ws/live")
    async def websocket_live(ws: WebSocket):
        await _ws_manager.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            _ws_manager.disconnect(ws)

    # Servir le dashboard React (build statique) en production
    # Doit être monté APRÈS les routes API pour ne pas les masquer
    dist_dir = Path(__file__).resolve().parent.parent.parent / "dashboard" / "dist"
    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="dashboard")
        logger.info("Dashboard servi depuis {}", dist_dir)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.api.server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,
    )
