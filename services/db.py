import asyncio
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from services.logger import log_debug, log_info, log_error

load_dotenv()

DB_PATH = Path(__file__).resolve().parent.parent / "music_bot.db"
SECRET_SALT = os.getenv("SECRET_SALT")
if not SECRET_SALT:
    raise RuntimeError("🚨 Критическая ошибка безопасности: переменная SECRET_SALT отсутствует в файле .env!")


def hash_user_id(user_id: int) -> str:
    """Возвращает анонимизированный salted SHA256-хэш user_id."""
    if not user_id:
        return ""
    raw = f"{SECRET_SALT}_{user_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _get_connection() -> sqlite3.Connection:
    """Возвращает новое соединение с кодировкой UTF-8, поддержкой row_factory и WAL-режимом."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db():
    """Создаёт таблицы базы данных SQLite с полной анонимизацией (только user_hash)."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_hash TEXT PRIMARY KEY,
                language_code TEXT NOT NULL DEFAULT 'ru',
                is_premium INTEGER DEFAULT 0,
                premium_expires_at DATETIME,
                daily_tracks_count INTEGER DEFAULT 0,
                daily_playlists_count INTEGER DEFAULT 0,
                last_download_date TEXT,
                is_whitelisted INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_hash TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'SoundCloud',
                downloaded_at DATETIME NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS playlist_cache (
                cache_id TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )

        # Автоматическая миграция: удаление legacy сырого столбца user_id из таблицы users
        try:
            table_info = conn.execute("PRAGMA table_info(users)").fetchall()
            if any(col["name"] == "user_id" for col in table_info):
                conn.execute("ALTER TABLE users RENAME TO users_legacy")
                conn.execute(
                    """
                    CREATE TABLE users (
                        user_hash TEXT PRIMARY KEY,
                        language_code TEXT NOT NULL DEFAULT 'ru',
                        is_premium INTEGER DEFAULT 0,
                        premium_expires_at DATETIME,
                        daily_tracks_count INTEGER DEFAULT 0,
                        daily_playlists_count INTEGER DEFAULT 0,
                        last_download_date TEXT,
                        is_whitelisted INTEGER DEFAULT 0
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users (
                        user_hash, language_code, is_premium, premium_expires_at, 
                        daily_tracks_count, daily_playlists_count, last_download_date, is_whitelisted
                    )
                    SELECT 
                        user_hash, language_code, is_premium, premium_expires_at, 
                        daily_tracks_count, daily_playlists_count, last_download_date, is_whitelisted 
                    FROM users_legacy WHERE user_hash IS NOT NULL AND user_hash != ''
                    """
                )
                conn.execute("DROP TABLE users_legacy")
                log_info("✅ Legacy колонка user_id успешно удалена из таблицы users")
        except Exception as e:
            log_error(f"⚠️ Ошибка миграции таблицы users: {e}")

        # Автоматическая миграция: удаление legacy сырого столбца user_id из таблицы history
        try:
            hist_info = conn.execute("PRAGMA table_info(history)").fetchall()
            if any(col["name"] == "user_id" for col in hist_info):
                conn.execute("ALTER TABLE history RENAME TO history_legacy")
                conn.execute(
                    """
                    CREATE TABLE history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_hash TEXT NOT NULL,
                        title TEXT NOT NULL,
                        artist TEXT NOT NULL,
                        platform TEXT NOT NULL DEFAULT 'SoundCloud',
                        downloaded_at DATETIME NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO history (id, user_hash, title, artist, platform, downloaded_at)
                    SELECT id, user_hash, title, artist, platform, downloaded_at 
                    FROM history_legacy WHERE user_hash IS NOT NULL AND user_hash != ''
                    """
                )
                conn.execute("DROP TABLE history_legacy")
                log_info("✅ Legacy колонка user_id успешно удалена из таблицы history")
        except Exception as e:
            log_error(f"⚠️ Ошибка миграции таблицы history: {e}")

        # Миграция новых колонок если база была создана раньше
        for col_sql in (
            "ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN premium_expires_at DATETIME",
            "ALTER TABLE users ADD COLUMN daily_tracks_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN daily_playlists_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_download_date TEXT",
            "ALTER TABLE users ADD COLUMN is_whitelisted INTEGER DEFAULT 0",
        ):
            try:
                conn.execute(col_sql)
            except Exception:
                pass

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_hash_history 
            ON history (user_hash, id DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_history_downloaded_at 
            ON history (downloaded_at)
            """
        )
        conn.commit()
    log_info("✅ База данных SQLite инициализирована (с анонимизацией хэша)!")


async def async_init_db():
    """Асинхронный вызов инициализации БД."""
    await asyncio.to_thread(init_db)


def add_history_record(user_id: int, title: str, artist: str, platform: str = "SoundCloud"):
    """Записывает скачанный трек в историю (под анонимным user_hash)."""
    if not user_id:
        return

    ensure_user_exists(user_id)
    u_hash = hash_user_id(user_id)
    now_iso = datetime.now().isoformat()

    try:
        with _get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO history (user_hash, title, artist, platform, downloaded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (u_hash, title, artist, platform, now_iso),
                )
            except sqlite3.IntegrityError:
                # Запасной вариант для старых баз со строгим NOT NULL у legacy поля user_id
                conn.execute(
                    """
                    INSERT INTO history (user_hash, user_id, title, artist, platform, downloaded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (u_hash, user_id, title, artist, platform, now_iso),
                )
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] {e}", user_id=user_id)


async def async_add_history_record(user_id: int, title: str, artist: str, platform: str = "SoundCloud"):
    """Асинхронная обёртка для записи в историю."""
    await asyncio.to_thread(add_history_record, user_id, title, artist, platform)


from services.locales import get_text


def format_history_datetime(dt_str: str, lang: str = "ru") -> str:
    """Форматирует строковую дату в красивое представление на нужном языке."""
    try:
        dt = datetime.fromisoformat(dt_str)
    except Exception:
        return dt_str

    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    record_date = dt.date()

    time_str = dt.strftime("%H:%M")

    if record_date == today:
        return get_text("today", lang, time=time_str)
    elif record_date == yesterday:
        return get_text("yesterday", lang, time=time_str)
    else:
        return dt.strftime("%d.%m.%Y")


def get_user_history(user_id: int, limit: int = 20, lang: str = "ru") -> list[dict]:
    """Возвращает до limit последних записей истории пользователя."""
    if not user_id:
        return []

    u_hash = hash_user_id(user_id)
    try:
        with _get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT title, artist, platform, downloaded_at
                FROM history
                WHERE user_hash = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (u_hash, limit),
            )
            rows = cursor.fetchall()
            return [
                {
                    "title": row["title"],
                    "artist": row["artist"],
                    "platform": row["platform"],
                    "date_formatted": format_history_datetime(row["downloaded_at"], lang),
                }
                for row in rows
            ]
    except Exception as e:
        print(f"⚠️ [DB Error] Ошибка чтения истории: {e}")
        return []


async def async_get_user_history(user_id: int, limit: int = 20, lang: str = "ru") -> list[dict]:
    """Асинхронная обёртка для получения истории пользователя."""
    return await asyncio.to_thread(get_user_history, user_id, limit, lang)


def clear_user_history(user_id: int) -> bool:
    """Удаляет всю историю скачиваний пользователя из базы данных."""
    if not user_id:
        return False
    u_hash = hash_user_id(user_id)
    try:
        with _get_connection() as conn:
            conn.execute("DELETE FROM history WHERE user_hash = ?", (u_hash,))
            conn.commit()
            return True
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка очистки истории: {e}")
        return False


def clear_user_history_days(user_id: int, days: int = 7) -> bool:
    """Удаляет историю скачиваний пользователя за последние N дней."""
    if not user_id:
        return False
    u_hash = hash_user_id(user_id)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    try:
        with _get_connection() as conn:
            conn.execute(
                "DELETE FROM history WHERE user_hash = ? AND downloaded_at >= ?",
                (u_hash, cutoff),
            )
            conn.commit()
            return True
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка очистки истории за {days} дней: {e}")
        return False


async def async_clear_user_history_days(user_id: int, days: int = 7) -> bool:
    """Асинхронное удаление истории скачиваний за последние N дней."""
    return await asyncio.to_thread(clear_user_history_days, user_id, days)


def clean_expired_history(retention_days: int = 90):
    """Автоматически удаляет записи истории старше retention_days дней."""
    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
    try:
        with _get_connection() as conn:
            conn.execute("DELETE FROM history WHERE downloaded_at < ?", (cutoff,))
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка ротации старой истории: {e}")


async def async_clean_expired_history(retention_days: int = 90):
    """Асинхронный вызов автоматической ротации истории."""
    await asyncio.to_thread(clean_expired_history, retention_days)


async def async_clear_user_history(user_id: int) -> bool:
    """Асинхронная очистка истории пользователя."""
    return await asyncio.to_thread(clear_user_history, user_id)


def get_user_language(user_id: int) -> str:
    """Возвращает язык пользователя ('ru' или 'en'). По умолчанию 'ru'."""
    if not user_id:
        return "ru"
    u_hash = hash_user_id(user_id)
    try:
        with _get_connection() as conn:
            cursor = conn.execute(
                "SELECT language_code FROM users WHERE user_hash = ?", (u_hash,)
            )
            row = cursor.fetchone()
            if not row:
                try:
                    cursor = conn.execute(
                        "SELECT language_code FROM users WHERE user_id = ?", (user_id,)
                    )
                    row = cursor.fetchone()
                except Exception:
                    pass

            if row and row["language_code"]:
                return row["language_code"]
    except Exception as e:
        print(f"⚠️ [DB Error] Ошибка чтения языка пользователя: {e}")
    return "ru"


async def async_get_user_language(user_id: int) -> str:
    """Асинхронное получение языка пользователя."""
    return await asyncio.to_thread(get_user_language, user_id)


def set_user_language(user_id: int, lang_code: str):
    """Устанавливает язык пользователя."""
    if not user_id:
        return
    u_hash = hash_user_id(user_id)
    try:
        with _get_connection() as conn:
            cursor = conn.execute(
                "UPDATE users SET language_code = ? WHERE user_hash = ?",
                (lang_code, u_hash),
            )
            if cursor.rowcount == 0:
                try:
                    cursor = conn.execute(
                        "UPDATE users SET language_code = ?, user_hash = ? WHERE user_id = ?",
                        (lang_code, u_hash, user_id),
                    )
                except Exception:
                    pass

            if cursor.rowcount == 0:
                conn.execute(
                    "INSERT INTO users (user_hash, language_code) VALUES (?, ?)",
                    (u_hash, lang_code),
                )
            conn.commit()
    except Exception as e:
        print(f"⚠️ [DB Error] Ошибка сохранения языка пользователя: {e}")


async def async_set_user_language(user_id: int, lang_code: str):
    """Асинхронная установка языка пользователя."""
    await asyncio.to_thread(set_user_language, user_id, lang_code)


import json
import time


def save_playlist_cache(cache_id: str, data: dict):
    """Сохраняет кэш плейлиста в базу данных SQLite."""
    if not cache_id or not data:
        return
    data_str = json.dumps(data, ensure_ascii=False)
    now = time.time()
    try:
        with _get_connection() as conn:
            cursor = conn.execute(
                "UPDATE playlist_cache SET data_json = ?, created_at = ? WHERE cache_id = ?",
                (data_str, now, cache_id),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    "INSERT INTO playlist_cache (cache_id, data_json, created_at) VALUES (?, ?, ?)",
                    (cache_id, data_str, now),
                )
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка сохранения кэша плейлиста: {e}")


async def async_save_playlist_cache(cache_id: str, data: dict):
    """Асинхронное сохранение кэша плейлиста."""
    await asyncio.to_thread(save_playlist_cache, cache_id, data)


def get_playlist_cache(cache_id: str, ttl_seconds: int = 1800) -> dict | None:
    """Извлекает кэш плейлиста из SQLite, если он не устарел."""
    if not cache_id:
        return None
    now = time.time()
    try:
        with _get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json, created_at FROM playlist_cache WHERE cache_id = ?",
                (cache_id,),
            )
            row = cursor.fetchone()
            if row:
                created_at = row["created_at"]
                if now - created_at <= ttl_seconds:
                    return json.loads(row["data_json"])
                else:
                    conn.execute("DELETE FROM playlist_cache WHERE cache_id = ?", (cache_id,))
                    conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка чтения кэша плейлиста: {e}")
    return None


async def async_get_playlist_cache(cache_id: str, ttl_seconds: int = 1800) -> dict | None:
    """Асинхронное получение кэша плейлиста."""
    return await asyncio.to_thread(get_playlist_cache, cache_id, ttl_seconds)


def delete_playlist_cache(cache_id: str):
    """Удаляет запись кэша плейлиста из БД."""
    if not cache_id:
        return
    try:
        with _get_connection() as conn:
            conn.execute("DELETE FROM playlist_cache WHERE cache_id = ?", (cache_id,))
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка удаления кэша плейлиста: {e}")


async def async_delete_playlist_cache(cache_id: str):
    """Асинхронное удаление кэша плейлиста."""
    await asyncio.to_thread(delete_playlist_cache, cache_id)


def clean_expired_playlist_cache(ttl_seconds: int = 1800):
    """Очищает все устаревшие записи кэша плейлистов из БД."""
    now = time.time()
    cutoff = now - ttl_seconds
    try:
        with _get_connection() as conn:
            conn.execute("DELETE FROM playlist_cache WHERE created_at < ?", (cutoff,))
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка очистки кэша плейлистов: {e}")


async def async_clean_expired_playlist_cache(ttl_seconds: int = 1800):
    """Асинхронная очистка устаревших кэшей плейлистов."""
    await asyncio.to_thread(clean_expired_playlist_cache, ttl_seconds)


# =====================================================================
#  ПРЕМИУМ И ДНЕВНЫЕ ЛИМИТЫ (FREE vs PREMIUM)
# =====================================================================

def get_user_premium_status(user_id: int) -> dict:
    """Возвращает статус подписки и текущие дневные лимиты пользователя."""
    if not user_id:
        return {"is_premium": False, "expires_at": None, "daily_tracks": 0, "daily_playlists": 0}

    u_hash = hash_user_id(user_id)
    today_str = datetime.now().strftime("%Y-%m-%d")

    try:
        with _get_connection() as conn:
            row = conn.execute(
                """
                SELECT is_premium, premium_expires_at, daily_tracks_count, daily_playlists_count, last_download_date, is_whitelisted
                FROM users WHERE user_hash = ?
                """,
                (u_hash,),
            ).fetchone()

            if not row:
                return {"is_premium": False, "expires_at": None, "is_whitelisted": False, "daily_tracks": 0, "daily_playlists": 0}

            is_whitelisted = bool(row["is_whitelisted"])
            if is_whitelisted:
                return {
                    "is_premium": True,
                    "expires_at": "Бессрочно",
                    "is_whitelisted": True,
                    "daily_tracks": row["daily_tracks_count"] or 0,
                    "daily_playlists": row["daily_playlists_count"] or 0,
                }

            # Авто-сброс суточных счетчиков
            if row["last_download_date"] != today_str:
                conn.execute(
                    """
                    UPDATE users 
                    SET daily_tracks_count = 0, daily_playlists_count = 0, last_download_date = ?
                    WHERE user_hash = ?
                    """,
                    (today_str, u_hash),
                )
                conn.commit()
                daily_tracks = 0
                daily_playlists = 0
            else:
                daily_tracks = row["daily_tracks_count"] or 0
                daily_playlists = row["daily_playlists_count"] or 0

            # Проверка срока действия подписки
            is_prem = bool(row["is_premium"])
            expires_at = row["premium_expires_at"]

            if is_prem and expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at)
                    if datetime.now() > exp_dt:
                        # Подписка истекла
                        conn.execute("UPDATE users SET is_premium = 0 WHERE user_hash = ?", (u_hash,))
                        conn.commit()
                        is_prem = False
                except Exception:
                    pass

            return {
                "is_premium": is_prem,
                "expires_at": expires_at,
                "is_whitelisted": False,
                "daily_tracks": daily_tracks,
                "daily_playlists": daily_playlists,
            }
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка получения статуса премиума: {e}", user_id=user_id)
        return {"is_premium": False, "expires_at": None, "daily_tracks": 0, "daily_playlists": 0}


def can_user_download_track(user_id: int) -> tuple[bool, str]:
    """Проверяет возможность скачивания отдельного трека (Бесплатно: 40 треков в день)."""
    status = get_user_premium_status(user_id)
    if status["is_premium"]:
        return True, "premium"
    if status["daily_tracks"] < 40:
        return True, "free"
    return False, "limit_reached"


def can_user_download_playlist(user_id: int, track_count: int) -> tuple[bool, str]:
    """Проверяет возможность скачивания плейлиста (Бесплатно: 3 плейлиста в день до 50 треков)."""
    status = get_user_premium_status(user_id)
    if status["is_premium"]:
        return True, "premium"

    if track_count > 50:
        return False, "playlist_tracks_over_limit"

    if status["daily_playlists"] >= 3:
        return False, "daily_playlists_limit_reached"

    return True, "free"


def increment_user_track_count(user_id: int):
    """Инкрементирует дневной счетчик скачанных треков."""
    if not user_id:
        return
    u_hash = hash_user_id(user_id)
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        with _get_connection() as conn:
            conn.execute(
                """
                UPDATE users 
                SET daily_tracks_count = COALESCE(daily_tracks_count, 0) + 1, last_download_date = ?
                WHERE user_hash = ?
                """,
                (today_str, u_hash),
            )
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка увлечения треков: {e}", user_id=user_id)


def increment_user_playlist_count(user_id: int):
    """Инкрементирует дневной счетчик скачанных плейлистов."""
    if not user_id:
        return
    u_hash = hash_user_id(user_id)
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        with _get_connection() as conn:
            conn.execute(
                """
                UPDATE users 
                SET daily_playlists_count = COALESCE(daily_playlists_count, 0) + 1, last_download_date = ?
                WHERE user_hash = ?
                """,
                (today_str, u_hash),
            )
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка увеличения плейлистов: {e}", user_id=user_id)


def set_user_premium(user_id: int, days: int = 30):
    """Выдает пользователю премиум подписку на указанное число дней."""
    if not user_id:
        return
    u_hash = hash_user_id(user_id)
    now = datetime.now()
    expires_dt = now + timedelta(days=days)
    expires_iso = expires_dt.isoformat()

    try:
        with _get_connection() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE user_hash = ?", (u_hash,)).fetchone()
            if days > 0:
                if exists:
                    conn.execute(
                        "UPDATE users SET is_premium = 1, premium_expires_at = ? WHERE user_hash = ?",
                        (expires_iso, u_hash),
                    )
                else:
                    conn.execute(
                        "INSERT INTO users (user_hash, is_premium, premium_expires_at) VALUES (?, 1, ?)",
                        (u_hash, expires_iso),
                    )
                log_info(f"💎 Выдана подписка на {days} дней пользователю [user:{u_hash[:8]}]")
            else:
                if exists:
                    conn.execute(
                        "UPDATE users SET is_premium = 0, premium_expires_at = NULL WHERE user_hash = ?",
                        (u_hash,),
                    )
                else:
                    conn.execute(
                        "INSERT INTO users (user_hash, is_premium, premium_expires_at) VALUES (?, 0, NULL)",
                        (u_hash,),
                    )
                log_info(f"🆓 Пользователь [user:{u_hash[:8]}] переведен на Бесплатный тариф")
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка изменения премиума: {e}", user_id=user_id)


def set_user_whitelist(user_id: int, is_whitelisted: bool = True):
    """Добавляет или удаляет пользователя из вечного WhiteList."""
    if not user_id:
        return
    u_hash = hash_user_id(user_id)
    val = 1 if is_whitelisted else 0
    try:
        with _get_connection() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE user_hash = ?", (u_hash,)).fetchone()
            if exists:
                conn.execute("UPDATE users SET is_whitelisted = ? WHERE user_hash = ?", (val, u_hash))
            else:
                conn.execute("INSERT INTO users (user_hash, is_whitelisted) VALUES (?, ?)", (u_hash, val))
            conn.commit()
            log_info(f"⭐ Пользователь [user:{u_hash[:8]}] {'добавлен в' if is_whitelisted else 'удален из'} WhiteList")
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка изменения WhiteList: {e}", user_id=user_id)


def get_whitelisted_users() -> list[str]:
    """Возвращает список хешей всех пользователей из WhiteList."""
    try:
        with _get_connection() as conn:
            rows = conn.execute("SELECT user_hash FROM users WHERE is_whitelisted = 1").fetchall()
            return [row["user_hash"] for row in rows]
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка получения WhiteList: {e}")
        return []


async def async_set_user_whitelist(user_id: int, is_whitelisted: bool = True):
    await asyncio.to_thread(set_user_whitelist, user_id, is_whitelisted)


async def async_get_user_premium_status(user_id: int) -> dict:
    return await asyncio.to_thread(get_user_premium_status, user_id)

async def async_can_user_download_track(user_id: int) -> tuple[bool, str]:
    return await asyncio.to_thread(can_user_download_track, user_id)

async def async_can_user_download_playlist(user_id: int, track_count: int) -> tuple[bool, str]:
    return await asyncio.to_thread(can_user_download_playlist, user_id, track_count)

async def async_increment_user_track_count(user_id: int):
    await asyncio.to_thread(increment_user_track_count, user_id)

async def async_increment_user_playlist_count(user_id: int):
    await asyncio.to_thread(increment_user_playlist_count, user_id)

async def async_set_user_premium(user_id: int, days: int = 30):
    await asyncio.to_thread(set_user_premium, user_id, days)


def ensure_user_exists(user_id: int, lang_code: str = "ru"):
    """Создаёт пользователя в таблице users, если его ещё нет."""
    if not user_id:
        return
    u_hash = hash_user_id(user_id)
    try:
        with _get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_hash, language_code) VALUES (?, ?)",
                (u_hash, lang_code),
            )
            conn.commit()
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка создания пользователя: {e}")


async def async_ensure_user_exists(user_id: int, lang_code: str = "ru"):
    """Асинхронная регистрация пользователя в БД."""
    await asyncio.to_thread(ensure_user_exists, user_id, lang_code)


def get_bot_stats() -> dict:
    """Возвращает общую статистику бота из базы данных."""
    try:
        with _get_connection() as conn:
            total_users = conn.execute(
                """
                SELECT COUNT(DISTINCT user_hash) FROM (
                    SELECT user_hash FROM users WHERE user_hash IS NOT NULL AND user_hash != ''
                    UNION
                    SELECT user_hash FROM history WHERE user_hash IS NOT NULL AND user_hash != ''
                )
                """
            ).fetchone()[0] or 0
            premium_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1 OR is_whitelisted = 1").fetchone()[0] or 0
            whitelisted_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_whitelisted = 1").fetchone()[0] or 0
            total_downloads = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] or 0

            return {
                "total_users": total_users,
                "premium_users": premium_users,
                "whitelisted_users": whitelisted_users,
                "total_downloads": total_downloads,
            }
    except Exception as e:
        log_error(f"⚠️ [DB Error] Ошибка получения статистики бота: {e}")
        return {
            "total_users": 0,
            "premium_users": 0,
            "whitelisted_users": 0,
            "total_downloads": 0,
        }


async def async_get_bot_stats() -> dict:
    """Асинхронное получение статистики бота."""
    return await asyncio.to_thread(get_bot_stats)

