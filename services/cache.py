import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from config import BASE_DIR

logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "bot_cache.db"

TRACKING_PARAMS = {
    "si", "feature", "igsh", "utm_source", "utm_medium",
    "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"
}


def normalize_url(raw_url: str) -> str:
    """Очищає URL від трекінгових параметрів (si, igsh, feature тощо) для точного пошуку в кеші."""
    try:
        parsed = urlparse(raw_url.strip())
        query_params = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_query = [
            (k, v) for k, v in query_params if k.lower() not in TRACKING_PARAMS
        ]
        clean_query = urlencode(filtered_query)
        # Прибираємо зайвий слеш наприкінці шляху
        clean_path = parsed.path.rstrip("/")
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path,
            parsed.params,
            clean_query,
            ""  # fragment
        ))
        return normalized
    except Exception:
        return raw_url.strip()


@dataclass
class CachedItem:
    media_type: str  # 'video', 'photo', 'audio'
    file_id: str
    caption: Optional[str] = None
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class CachedMedia:
    url: str
    title: str
    items: List[CachedItem]


def init_db():
    """Ініціалізує таблиці бази даних SQLite для кешування."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cached_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cached_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id INTEGER,
                media_type TEXT,
                file_id TEXT,
                caption TEXT,
                duration INTEGER,
                width INTEGER,
                height INTEGER,
                FOREIGN KEY(media_id) REFERENCES cached_media(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cached_url ON cached_media(url)")
        conn.commit()


def get_cached_media(raw_url: str) -> Optional[CachedMedia]:
    """Шукає медіа за нормалізованим посиланням."""
    url = normalize_url(raw_url)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title FROM cached_media WHERE url = ?", (url,))
            row = cursor.fetchone()
            if not row:
                return None

            media_id, title = row
            cursor.execute(
                "SELECT media_type, file_id, caption, duration, width, height FROM cached_items WHERE media_id = ?",
                (media_id,)
            )
            item_rows = cursor.fetchall()
            if not item_rows:
                return None

            items = [
                CachedItem(
                    media_type=r[0],
                    file_id=r[1],
                    caption=r[2],
                    duration=r[3],
                    width=r[4],
                    height=r[5]
                )
                for r in item_rows
            ]
            logger.info(f"Знайдено кеш для {url} ({len(items)} елементів)")
            return CachedMedia(url=url, title=title, items=items)
    except Exception as e:
        logger.error(f"Помилка при читанні з кешу: {e}")
        return None


def save_cached_media(raw_url: str, title: str, items: List[CachedItem]) -> None:
    """Зберігає надіслані file_id в кеш для миттєвої відправки в майбутньому."""
    if not items:
        return
    url = normalize_url(raw_url)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO cached_media (url, title) VALUES (?, ?) ON CONFLICT(url) DO UPDATE SET title = excluded.title",
                (url, title)
            )
            cursor.execute("SELECT id FROM cached_media WHERE url = ?", (url,))
            media_id = cursor.fetchone()[0]

            # Видаляємо старі елементи, якщо були
            cursor.execute("DELETE FROM cached_items WHERE media_id = ?", (media_id,))

            for item in items:
                cursor.execute(
                    """
                    INSERT INTO cached_items (media_id, media_type, file_id, caption, duration, width, height)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (media_id, item.media_type, item.file_id, item.caption, item.duration, item.width, item.height)
                )
            conn.commit()
            logger.info(f"Збережено {len(items)} елементів у кеш для {url}")
    except Exception as e:
        logger.error(f"Помилка при збереженні в кеш: {e}")
