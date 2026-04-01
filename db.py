"""SQLite storage for bot snapshots and detected trade events."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class BotDatabase:
    """Small wrapper around SQLite used by the Telegram bot."""

    def __init__(self, db_path: str = "bot_data.sqlite3") -> None:
        self.db_path = Path(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    position_key TEXT PRIMARY KEY,
                    market_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    pnl REAL NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_key TEXT NOT NULL,
                    market_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_events (
                    activity_id TEXT PRIMARY KEY,
                    market_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    side TEXT NOT NULL,
                    activity_time TEXT NOT NULL,
                    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS news_events (
                    news_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    volume REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    url TEXT NOT NULL,
                    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def get_positions_map(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT position_key, market_name, price, amount, pnl FROM positions"
            ).fetchall()
        return {
            row["position_key"]: {
                "position_key": row["position_key"],
                "market_name": row["market_name"],
                "price": row["price"],
                "amount": row["amount"],
                "pnl": row["pnl"],
            }
            for row in rows
        }

    def replace_positions(self, positions: list[dict[str, Any]]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM positions")
            connection.executemany(
                """
                INSERT INTO positions (position_key, market_name, price, amount, pnl)
                VALUES (:position_key, :market_name, :price, :amount, :pnl)
                """,
                positions,
            )
            connection.commit()

    def add_trade_event(self, position: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trade_events (position_key, market_name, price, amount)
                VALUES (:position_key, :market_name, :price, :amount)
                """,
                position,
            )
            connection.commit()

    def get_stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            summary_row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(pnl), 0) AS total_pnl,
                    COUNT(*) AS open_positions
                FROM positions
                """
            ).fetchone()
            trade_row = connection.execute(
                "SELECT COUNT(*) AS trade_count FROM trade_events"
            ).fetchone()

        return {
            "total_pnl": float(summary_row["total_pnl"]),
            "open_positions": int(summary_row["open_positions"]),
            "trade_count": int(trade_row["trade_count"]),
        }

    def get_recent_trade_events(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT market_name, price, amount, detected_at
                FROM trade_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "market_name": row["market_name"],
                "price": row["price"],
                "amount": row["amount"],
                "detected_at": row["detected_at"],
            }
            for row in rows
        ]

    def has_activity_event(self, activity_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM activity_events WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()
        return row is not None

    def add_activity_event(self, activity: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO activity_events (
                    activity_id, market_name, price, amount, side, activity_time
                )
                VALUES (
                    :activity_id, :market_name, :price, :amount, :side, :timestamp
                )
                """,
                activity,
            )
            connection.commit()

    def get_recent_activity_events(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT market_name, price, amount, side, activity_time
                FROM activity_events
                ORDER BY detected_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "market_name": row["market_name"],
                "price": row["price"],
                "amount": row["amount"],
                "side": row["side"],
                "timestamp": row["activity_time"],
            }
            for row in rows
        ]

    def has_news_event(self, news_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM news_events WHERE news_id = ?",
                (news_id,),
            ).fetchone()
        return row is not None

    def add_news_event(self, news: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO news_events (
                    news_id, title, category, volume, created_at, url
                )
                VALUES (
                    :news_id, :title, :category, :volume, :created_at, :url
                )
                """,
                news,
            )
            connection.commit()

    def get_recent_news_events(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT title, category, volume, created_at, url
                FROM news_events
                ORDER BY detected_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "title": row["title"],
                "category": row["category"],
                "volume": row["volume"],
                "created_at": row["created_at"],
                "url": row["url"],
            }
            for row in rows
        ]
