"""Wrapper async SQLite — aiosqlite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from backend.storage.schemas import SCHEMA_SQL
from backend.utils.logger import logger

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cryptobot.db"


class Database:
    """Wrapper léger autour de aiosqlite."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else _DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Ouvre la connexion et crée les tables si nécessaire."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA_SQL)
        await self._migrate(self._db)
        await self._db.commit()
        logger.info("SQLite connectée — {}", self.path)

    @staticmethod
    async def _migrate(db: aiosqlite.Connection) -> None:
        """Migrations incrémentales — ajoute les colonnes manquantes."""
        cursor = await db.execute("PRAGMA table_info(trades)")
        columns = {row[1] for row in await cursor.fetchall()}

        if "highest_since_entry" not in columns:
            await db.execute("ALTER TABLE trades ADD COLUMN highest_since_entry REAL")
            logger.info("Migration: ajout colonne trades.highest_since_entry")

        if "max_hold_minutes" not in columns:
            await db.execute("ALTER TABLE trades ADD COLUMN max_hold_minutes INTEGER")
            logger.info("Migration: ajout colonne trades.max_hold_minutes")

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("SQLite fermée")

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database non connectée — appeler connect() d'abord")
        return self._db

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        cursor = await self.db.execute(sql, params)
        await self.db.commit()
        return cursor

    async def executemany(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        await self.db.executemany(sql, params_seq)
        await self.db.commit()

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cursor = await self.db.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor = await self.db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
