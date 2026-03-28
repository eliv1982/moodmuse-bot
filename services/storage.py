"""
SQLite persistence: daily generation limits, user language, last card for regen, admin flags.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


_lock = threading.Lock()


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class LastCardContext:
    occasion: str
    image_description: str
    holiday: str
    image_style: str
    text_style: str
    lang: str
    image_prompt_en: str
    """Telegram file_id of last sent photo (for regen caption without new image)."""
    photo_file_id: str = ""
    """Caption HTML as sent to Telegram (for repeat without API)."""
    caption_html: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "occasion": self.occasion,
            "image_description": self.image_description,
            "holiday": self.holiday,
            "image_style": self.image_style,
            "text_style": self.text_style,
            "lang": self.lang,
            "image_prompt_en": self.image_prompt_en,
            "photo_file_id": self.photo_file_id,
            "caption_html": self.caption_html,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Optional["LastCardContext"]:
        try:
            return cls(
                occasion=str(d.get("occasion", "")),
                image_description=str(d.get("image_description", "")),
                holiday=str(d.get("holiday", "")),
                image_style=str(d.get("image_style", "style_realistic")),
                text_style=str(d.get("text_style", "text_warm")),
                lang=str(d.get("lang", "ru")),
                image_prompt_en=str(d.get("image_prompt_en", "")),
                photo_file_id=str(d.get("photo_file_id", "")),
                caption_html=str(d.get("caption_html", "")),
            )
        except (TypeError, ValueError):
            return None


class BotStorage:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Any:
        with _lock:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS user_prefs (
                    user_id INTEGER PRIMARY KEY,
                    lang TEXT NOT NULL DEFAULT 'ru'
                );
                CREATE TABLE IF NOT EXISTS daily_counts (
                    user_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, day)
                );
                CREATE TABLE IF NOT EXISTS generation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    ts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS last_card (
                    user_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gen_log_ts ON generation_log(ts);
                """
            )

    def get_user_lang(self, user_id: int) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT lang FROM user_prefs WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row:
            return str(row["lang"])
        return None

    def set_user_lang(self, user_id: int, lang: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO user_prefs (user_id, lang) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET lang = excluded.lang
                """,
                (user_id, lang),
            )

    def get_daily_count(self, user_id: int, day: Optional[str] = None) -> int:
        d = day or utc_today()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT count FROM daily_counts WHERE user_id = ? AND day = ?",
                (user_id, d),
            ).fetchone()
        return int(row["count"]) if row else 0

    def increment_generation(self, user_id: int, day: Optional[str] = None) -> int:
        d = day or utc_today()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO daily_counts (user_id, day, count) VALUES (?, ?, 1)
                ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1
                """,
                (user_id, d),
            )
            row = conn.execute(
                "SELECT count FROM daily_counts WHERE user_id = ? AND day = ?",
                (user_id, d),
            ).fetchone()
            now = int(datetime.now(timezone.utc).timestamp())
            conn.execute(
                "INSERT INTO generation_log (user_id, ts) VALUES (?, ?)",
                (user_id, now),
            )
        return int(row["count"]) if row else 1

    def save_last_card(self, user_id: int, ctx: LastCardContext) -> None:
        payload = json.dumps(ctx.to_dict(), ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO last_card (user_id, payload) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload
                """,
                (user_id, payload),
            )

    def get_last_card(self, user_id: int) -> Optional[LastCardContext]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM last_card WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        try:
            d = json.loads(row["payload"])
            if not isinstance(d, dict):
                return None
            return LastCardContext.from_dict(d)
        except (json.JSONDecodeError, TypeError):
            return None

    def kv_get(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def kv_set(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO kv (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def is_small_talk_enabled(self) -> bool:
        return self.kv_get("small_talk_enabled", "1") != "0"

    def set_small_talk_enabled(self, enabled: bool) -> None:
        self.kv_set("small_talk_enabled", "1" if enabled else "0")

    def get_maintenance_message(self) -> str:
        return self.kv_get("maintenance_message", "")

    def set_maintenance_message(self, text: str) -> None:
        self.kv_set("maintenance_message", text.strip())

    def stats_today(self) -> tuple[int, int]:
        """(total_generations_today, unique_users_today) in UTC day."""
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        ts0 = int(start.timestamp())
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM generation_log WHERE ts >= ?",
                (ts0,),
            ).fetchone()["c"]
            unique = conn.execute(
                "SELECT COUNT(DISTINCT user_id) AS c FROM generation_log WHERE ts >= ?",
                (ts0,),
            ).fetchone()["c"]
        return int(total), int(unique)

    def stats_total(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM generation_log").fetchone()
        return int(row["c"])


_storage: Optional[BotStorage] = None


def init_storage(db_path: Path) -> BotStorage:
    """Call once at startup with path from settings."""
    global _storage
    _storage = BotStorage(db_path)
    return _storage


def get_storage() -> BotStorage:
    global _storage
    if _storage is None:
        _storage = BotStorage(Path("data") / "bot.db")
    return _storage


def reset_storage_for_tests() -> None:
    global _storage
    _storage = None
