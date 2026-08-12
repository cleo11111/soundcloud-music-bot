"""
Обработчики плейлистов: инлайн-поиск, прямые ссылки, выбор формата отправки.
Отдельный файл, не затрагивающий основной inline.py.
"""
import asyncio
import time
import uuid

from aiogram import Router, F
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    InputMediaAudio,
)
from aiogram.exceptions import TelegramBadRequest
from yt_dlp import YoutubeDL

from services.downloader import (
    async_fetch_playlist_info,
    async_download_song,
    async_download_playlist_as_zip,
    cleanup_file,
    start_user_download,
    finish_user_download,
)
from services.db import (
    async_add_history_record,
    async_get_user_language,
    async_can_user_download_playlist,
    async_increment_user_playlist_count,
    save_playlist_cache,
    get_playlist_cache,
    delete_playlist_cache,
    clean_expired_playlist_cache,
)
from services.locales import format_cover_caption, get_text
from services.logger import log_debug, log_info, log_error

router = Router()

# ─── Кэши ────────────────────────────────────────────────────────────

# Кэш информации о плейлисте: cache_id → {url, title, uploader, entries, ...}
PLAYLIST_CACHE: dict[str, dict] = {}
CACHE_TTL = 1800  # 30 мин

# Кэш результатов инлайн-поиска плейлистов: запрос → {entries, timestamp}
SEARCH_CACHE: dict[str, dict] = {}
SEARCH_CACHE_TTL = 900  # 15 мин


def _clean_caches():
    """Удаляет устаревшие записи из памяти и базы данных."""
    now = time.time()
    for store, ttl in [(PLAYLIST_CACHE, CACHE_TTL), (SEARCH_CACHE, SEARCH_CACHE_TTL)]:
        expired = [k for k, v in store.items() if now - v.get("timestamp", 0) > ttl]
        for k in expired:
            del store[k]
    clean_expired_playlist_cache(CACHE_TTL)


def _store_playlist(
    url: str,
    title: str = "",
    uploader: str = "",
    track_count: int = 0,
    thumbnail: str | None = None,
) -> str:
    """Сохраняет метаданные плейлиста в память и SQLite БД."""
    cache_id = uuid.uuid4().hex[:8]
    data = {
        "url": url,
        "title": title,
        "uploader": uploader,
        "track_count": track_count,
        "thumbnail": thumbnail,
        "timestamp": time.time(),
    }
    PLAYLIST_CACHE[cache_id] = data
    save_playlist_cache(cache_id, data)
    return cache_id


def _get_cached_playlist(cache_id: str) -> dict | None:
    """Извлекает плейлист из оперативной памяти или SQLite БД."""
    data = PLAYLIST_CACHE.get(cache_id)
    if data:
        return data
    db_data = get_playlist_cache(cache_id)
    if db_data:
        PLAYLIST_CACHE[cache_id] = db_data
        return db_data
    return None


# ─── Поиск плейлистов через SoundCloud API v2 ────────────────────────

CLIENT_ID_CACHE = {"client_id": None, "timestamp": 0}


def _get_soundcloud_client_id() -> str | None:
    """Извлекает актуальный client_id с главной страницы SoundCloud."""
    import urllib.request
    import re

    now = time.time()
    if CLIENT_ID_CACHE["client_id"] and (now - CLIENT_ID_CACHE["timestamp"] < 3600):
        return CLIENT_ID_CACHE["client_id"]

    try:
        req = urllib.request.Request(
            "https://soundcloud.com",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")

        js_urls = re.findall(
            r'src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', html
        )
        for url in reversed(js_urls):
            try:
                req_js = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                )
                with urllib.request.urlopen(req_js, timeout=10) as resp_js:
                    js = resp_js.read().decode("utf-8")
                m = re.search(r'client_id[:=]"([a-zA-Z0-9]{32})"', js)
                if m:
                    cid = m.group(1)
                    CLIENT_ID_CACHE["client_id"] = cid
                    CLIENT_ID_CACHE["timestamp"] = now
                    return cid
            except Exception:
                pass
    except Exception as e:
        log_error(f"⚠️ Не удалось получить client_id SoundCloud: {e}")

    return None


def _search_playlists_sc(query: str, max_items: int = 200) -> list:
    """
    Ищет плейлисты на SoundCloud через API v2 с пагинацией (next_href).
    Возвращает список всех найденных плейлистов (до max_items).
    """
    import urllib.request
    import urllib.parse
    import json

    cid = _get_soundcloud_client_id()
    if not cid:
        log_error("❌ Нет client_id SoundCloud для поиска плейлистов")
        return []

    encoded_q = urllib.parse.quote(query)
    api_url = f"https://api-v2.soundcloud.com/search/playlists?q={encoded_q}&client_id={cid}&limit=50"
    entries = []
    seen_urls = set()

    next_url = api_url

    try:
        while next_url and len(entries) < max_items:
            url_to_fetch = next_url
            if "&client_id=" not in url_to_fetch:
                url_to_fetch += f"&client_id={cid}"

            req = urllib.request.Request(
                url_to_fetch,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                collection = data.get("collection", [])
                next_url = data.get("next_href")

            for p in collection:
                pl_url = p.get("permalink_url")
                if not pl_url or pl_url in seen_urls:
                    continue

                seen_urls.add(pl_url)
                title = p.get("title") or "Без названия"
                user_info = p.get("user") or {}
                uploader = user_info.get("username") or "SoundCloud"
                track_count = p.get("track_count") or 0

                artwork = p.get("artwork_url") or user_info.get("avatar_url")
                if artwork and "-large" in artwork:
                    artwork = artwork.replace("-large", "-t500x500")

                entries.append(
                    {
                        "url": pl_url,
                        "title": title,
                        "uploader": uploader,
                        "playlist_count": track_count,
                        "thumbnails": [{"url": artwork}] if artwork else [],
                    }
                )

                if len(entries) >= max_items:
                    break

            if next_url and len(entries) < max_items:
                time.sleep(0.2)

        log_debug(f"✅ [API v2] Итого найдено {len(entries)} плейлистов")
        return entries
    except Exception as e:
        log_error(f"❌ [API v2 Error] Ошибка поиска плейлистов: {e}")
        return entries


def pluralize_tracks(count: int, lang: str = "ru") -> str:
    """Возвращает число и правильно просклоненное слово 'трек'."""
    if lang == "en":
        return f"{count} track" if count == 1 else f"{count} tracks"

    n = abs(count) % 100
    n1 = n % 10
    if 10 < n < 20:
        form = "треков"
    elif 1 < n1 < 5:
        form = "трека"
    elif n1 == 1:
        form = "трек"
    else:
        form = "треков"
    return f"{count} {form}"


# =====================================================================
#  INLINE QUERY — @бот /playlist <запрос>
# =====================================================================


@router.inline_query(F.query.startswith("/playlist "))
async def inline_playlist_search(query: InlineQuery):
    """Инлайн-поиск плейлистов SoundCloud."""
    text = query.query[len("/playlist "):].strip().lower()

    if len(text) < 2:
        return

    offset = int(query.offset) if query.offset else 0
    user_id = query.from_user.id
    lang = await async_get_user_language(user_id)

    try:
        _clean_caches()

        # Первый запрос — ищем
        if text not in SEARCH_CACHE:
            raw = await asyncio.to_thread(_search_playlists_sc, text, 200)
            SEARCH_CACHE[text] = {"entries": raw, "timestamp": time.time()}

        entries = SEARCH_CACHE[text]["entries"]

        # Ничего не нашли
        if not entries:
            await query.answer([], cache_time=5, is_personal=False)
            return

        # Пагинация
        per_page = 25
        page = entries[offset : offset + per_page]

        results = []
        for i, entry in enumerate(page):
            pl_url = entry.get("url", "")
            title = entry.get("title", "Без названия")
            uploader = entry.get("uploader", "SoundCloud")
            count = entry.get("playlist_count") or 0

            # Обложка
            thumbnails = entry.get("thumbnails", [])
            thumb_url = thumbnails[-1].get("url") if thumbnails else None

            # Запоминаем, чтобы не запрашивать повторно при выборе
            cache_id = _store_playlist(
                url=pl_url,
                title=title,
                uploader=uploader,
                track_count=int(count) if count else 0,
                thumbnail=thumb_url,
            )

            desc = f"👤 {uploader}"
            if count:
                desc += f"  •  🎵 {pluralize_tracks(int(count), lang)}"

            results.append(
                InlineQueryResultArticle(
                    id=uuid.uuid4().hex[:12],
                    title=f"📂 {title}",
                    description=desc,
                    thumbnail_url=thumb_url,
                    thumbnail_width=500,
                    thumbnail_height=500,
                    input_message_content=InputTextMessageContent(
                        message_text=f"🎶PLAYLIST::{cache_id}::{pl_url}"
                    ),
                )
            )

        next_off = (
            str(offset + len(page))
            if (offset + len(page)) < len(entries)
            else ""
        )

        await query.answer(
            results,
            next_offset=next_off,
            cache_time=5,
            is_personal=False,
        )

    except TelegramBadRequest:
        pass
    except Exception as e:
        print(f"💥 [Inline Playlist Error] {e}")


# =====================================================================
#  ВЫБОР ИЗ ИНЛАЙНА — ловим сообщение 🎶PLAYLIST::id::url
# =====================================================================


async def _show_playlist_choice(message: Message, pl_url: str, cache_id: str):
    """
    Загружает полную информацию о плейлисте и показывает
    клавиатуру «Архивом / По отдельности».
    """
    user_id = message.from_user.id
    lang = await async_get_user_language(user_id)

    cached = _get_cached_playlist(cache_id) or {}
    fallback_title = cached.get("title", "Плейлист")

    wait = await message.answer(get_text("loading_playlist_info", lang))

    try:
        info = await async_fetch_playlist_info(pl_url)

        if not info or not info.get("entries"):
            await wait.edit_text(get_text("err_playlist_empty", lang))
            return

        title = info.get("title", fallback_title)
        uploader = info.get("uploader", "SoundCloud")
        track_count = info.get("track_count", 0)

        # Обновляем кэш полной информацией в памяти и в SQLite БД
        playlist_data = {
            **cached,
            "url": pl_url,
            "title": title,
            "uploader": uploader,
            "track_count": track_count,
            "entries": info["entries"],
            "timestamp": time.time(),
        }
        PLAYLIST_CACHE[cache_id] = playlist_data
        save_playlist_cache(cache_id, playlist_data)

        entries_count = len(info["entries"])
        is_over_limit = entries_count > 50 or track_count > 50

        btn_zip_text = get_text("btn_pl_zip", lang)
        btn_sep_text = get_text("btn_pl_sep", lang)

        buttons = [
            InlineKeyboardButton(
                text=btn_zip_text,
                callback_data=f"pl_zip_{cache_id}",
            )
        ]

        if not is_over_limit:
            buttons.append(
                InlineKeyboardButton(
                    text=btn_sep_text,
                    callback_data=f"pl_sep_{cache_id}",
                )
            )

        kb = InlineKeyboardMarkup(inline_keyboard=[buttons])

        prompt_text = (
            get_text("playlist_over_limit", lang, count=pluralize_tracks(track_count, lang))
            if is_over_limit
            else get_text("playlist_choice", lang)
        )

        await wait.edit_text(
            f"📂 <b>{title}</b>\n"
            f"👤 {uploader}\n"
            f"🎵 {pluralize_tracks(track_count, lang)}\n\n"
            f"{prompt_text}",
            reply_markup=kb,
            parse_mode="HTML",
        )

        # Удаляем техническое сообщение с PLAYLIST:: текстом
        try:
            await message.delete()
        except Exception:
            pass

    except Exception as e:
        log_error(f"⚠️ Ошибка в обработчике плейлиста: {e}")
        await wait.edit_text(get_text("err_generic", lang))


@router.message(F.text.startswith("🎶PLAYLIST::"))
async def handle_playlist_from_inline(message: Message):
    """Перехватывает выбор плейлиста из инлайн-режима."""
    parts = message.text.split("::", 2)
    if len(parts) < 3:
        return
    cache_id = parts[1]
    pl_url = parts[2]
    await _show_playlist_choice(message, pl_url, cache_id)


import urllib.parse


SYSTEM_PATHS = {"/discover", "/feed", "/you", "/upload", "/stream", "/search", "/terms-of-use", "/people", "/settings", "/pages", "/imprint"}


def is_valid_soundcloud_url(url: str) -> bool:
    """Строго проверяет домен и путь адреса на принадлежность к публичному плейлисту SoundCloud."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if not (host == "soundcloud.com" or host.endswith(".soundcloud.com") or host == "on.soundcloud.com"):
            return False
        path = (parsed.path or "").lower().strip()
        if any(path == sys_p or path.startswith(sys_p + "/") for sys_p in SYSTEM_PATHS):
            return False
        return True
    except Exception:
        return False


# =====================================================================
#  ПРЯМАЯ ССЫЛКА НА ПЛЕЙЛИСТ — soundcloud.com/.../sets/...
# =====================================================================


import re


@router.message(
    F.text.contains("/sets/") | F.caption.contains("/sets/"),
)
async def handle_playlist_direct_link(message: Message):
    """Обрабатывает прямую ссылку на плейлист SoundCloud."""
    raw_text = message.text or message.caption or ""

    match = re.search(r'https?://[^\s]+', raw_text)
    if not match:
        return
    url = match.group(0).strip()

    if not is_valid_soundcloud_url(url):
        return

    cache_id = uuid.uuid4().hex[:8]
    data = {"url": url, "timestamp": time.time()}
    PLAYLIST_CACHE[cache_id] = data
    save_playlist_cache(cache_id, data)
    await _show_playlist_choice(message, url, cache_id)


# =====================================================================
#  CALLBACK — скачать архивом (ZIP)
# =====================================================================


@router.callback_query(F.data.startswith("pl_zip_"))
async def handle_playlist_zip(call: CallbackQuery):
    """Скачивает все треки плейлиста и отправляет ZIP-архивом."""
    cache_id = call.data[len("pl_zip_"):]
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    cached = _get_cached_playlist(cache_id)

    if not cached or not cached.get("entries"):
        await call.answer(get_text("data_expired", lang), show_alert=True)
        return

    entries = cached["entries"]
    title = cached.get("title", "Плейлист")
    total = len(entries)

    # Проверка лимитов бесплатного тарифа на плейлисты
    allowed, status_code = await async_can_user_download_playlist(user_id, total)
    if not allowed:
        if status_code == "playlist_tracks_over_limit":
            msg = get_text("err_playlist_tracks_over_limit", lang, count=total)
        else:
            msg = get_text("err_daily_playlists_limit", lang)
        await call.answer(msg, show_alert=True)
        return

    if not start_user_download(user_id):
        await call.answer(get_text("err_already_downloading", lang), show_alert=True)
        return

    await call.answer(get_text("starting_download", lang))
    await call.message.edit_text(
        get_text("downloading_playlist_zip", lang, count=pluralize_tracks(total, lang), title=title)
    )

    result = None
    try:
        result = await async_download_playlist_as_zip(entries, title)

        zip_paths = result.get("zip_paths") or [result["zip_path"]]
        downloaded = result["track_count"]
        total_parts = len(zip_paths)

        safe = (
            "".join(c for c in title if c.isalnum() or c in " -_()").strip()
            or "playlist"
        )

        for idx, zp in enumerate(zip_paths, 1):
            if not zp or not zp.exists():
                continue

            part_suffix = f" (Часть {idx}/{total_parts})" if total_parts > 1 else ""
            part_filename = f"{safe}_part{idx}.zip" if total_parts > 1 else f"{safe}.zip"

            await call.message.answer_document(
                FSInputFile(zp, filename=part_filename),
                caption=f"📂 {title}{part_suffix}\n🎵 {pluralize_tracks(downloaded, lang)}",
            )

        # Записываем одну запись плейлиста в историю и инкрементируем счетчик
        uploader = cached.get("uploader") or "SoundCloud"
        await async_add_history_record(
            user_id=call.from_user.id,
            title=f"[PL] {title}",
            artist=uploader,
            platform="SoundCloud",
        )
        await async_increment_user_playlist_count(call.from_user.id)

        await call.message.delete()

    except Exception as e:
        err = str(e)
        if "ERR_DISK_FULL" in err:
            await call.message.edit_text(get_text("err_disk_full", lang))
        else:
            log_error(f"⚠️ Ошибка скачивания плейлиста: {e}")
            await call.message.edit_text(get_text("err_generic", lang))

    finally:
        finish_user_download(user_id)
        if result and result.get("job_dir"):
            cleanup_file(result["job_dir"])
        elif result and result.get("zip_paths"):
            cleanup_file(*result["zip_paths"])
        PLAYLIST_CACHE.pop(cache_id, None)
        delete_playlist_cache(cache_id)


# =====================================================================
#  CALLBACK — отправить по отдельности
# =====================================================================


@router.callback_query(F.data.startswith("pl_sep_"))
async def handle_playlist_separate(call: CallbackQuery):
    """Скачивает и отправляет каждый трек по отдельности."""
    import hashlib

    cache_id = call.data[len("pl_sep_"):]
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    cached = _get_cached_playlist(cache_id)

    if not cached or not cached.get("entries"):
        await call.answer(get_text("data_expired", lang), show_alert=True)
        return

    entries = cached["entries"]
    title = cached.get("title", "Плейлист")
    total = len(entries)

    # Проверка лимитов бесплатного тарифа на плейлисты
    allowed, status_code = await async_can_user_download_playlist(user_id, total)
    if not allowed:
        if status_code == "playlist_tracks_over_limit":
            msg = get_text("err_playlist_tracks_over_limit", lang, count=total)
        else:
            msg = get_text("err_daily_playlists_limit", lang)
        await call.answer(msg, show_alert=True)
        return

    # Проверка на ограничение > 50 треков
    if total > 50 or cached.get("track_count", 0) > 50:
        alert_msg = get_text("playlist_over_limit_alert", lang)
        await call.answer(alert_msg, show_alert=True)
        return

    if not start_user_download(user_id):
        await call.answer(get_text("err_already_downloading", lang), show_alert=True)
        return

    await call.answer(get_text("starting_download", lang))
    progress = await call.message.edit_text(
        get_text("downloading_playlist_sep", lang, title=title, current=0, total=total)
    )

    downloaded_results = []
    try:
        # 1. Скачиваем все треки
        for i, entry in enumerate(entries):
            url = entry.get("url") or entry.get("webpage_url")
            if not url:
                continue

            try:
                res = await async_download_song(url)
                if res and res.get("path") and res["path"].exists():
                    downloaded_results.append(res)
            except Exception as e:
                print(f"⚠️ [Playlist sep] Ошибка скачивания трека {i + 1}: {e}")

            # Обновляем прогресс каждые 2 трека или в конце
            if (i + 1) % 2 == 0 or i == total - 1:
                try:
                    await progress.edit_text(
                        get_text(
                            "downloading_playlist_sep",
                            lang,
                            title=title,
                            current=len(downloaded_results),
                            total=total,
                        )
                    )
                except Exception:
                    pass

        if not downloaded_results:
            await progress.edit_text(get_text("err_playlist_sep_failed", lang, title=title))
            return

        # 2. Отправляем ОДНУ общую обложку плейлиста в самом начале
        uploader = cached.get("uploader") or "SoundCloud"
        playlist_cover = None
        for res in downloaded_results:
            cp = res.get("cover_path")
            if cp and cp.exists():
                playlist_cover = cp
                break

        if playlist_cover:
            try:
                caption = f"📂 <b>{title}</b>\n👤 {uploader}\n🎵 {pluralize_tracks(len(downloaded_results), lang)}"
                await call.message.answer_photo(FSInputFile(playlist_cover), caption=caption, parse_mode="HTML")
            except Exception as e:
                log_error(f"⚠️ Ошибка отправки обложки плейлиста: {e}")

        # 3. Отправляем все треки вместе (медиагруппами альбомов Telegram по 10 штук)
        chunk_size = 10
        for chunk_idx in range(0, len(downloaded_results), chunk_size):
            chunk = downloaded_results[chunk_idx : chunk_idx + chunk_size]
            media_group = []

            for res in chunk:
                mp3_path = res["path"]
                if not mp3_path.exists() or mp3_path.stat().st_size / (1024 * 1024) > 49.5:
                    continue

                audio_file = FSInputFile(mp3_path)
                thumb_path = res.get("thumb_path") or res.get("cover_path")
                thumbnail = FSInputFile(thumb_path) if (thumb_path and thumb_path.exists()) else None

                media = InputMediaAudio(
                    media=audio_file,
                    title=res["title"],
                    performer=res["artist"],
                    duration=res["duration"],
                    thumbnail=thumbnail,
                )
                media_group.append(media)

            if media_group:
                try:
                    await call.message.answer_media_group(media=media_group)
                except Exception as e:
                    log_error(f"⚠️ Ошибка отправки медиагруппы: {e}, fallback к отправке по одному")
                    for res in chunk:
                        mp3_path = res["path"]
                        if not mp3_path.exists() or mp3_path.stat().st_size / (1024 * 1024) > 49.5:
                            continue
                        thumb_path = res.get("thumb_path") or res.get("cover_path")
                        thumbnail = FSInputFile(thumb_path) if (thumb_path and thumb_path.exists()) else None
                        try:
                            await call.message.answer_audio(
                                FSInputFile(mp3_path),
                                title=res["title"],
                                performer=res["artist"],
                                duration=res["duration"],
                                thumbnail=thumbnail,
                            )
                        except Exception:
                            pass

        # 4. Записываем одну запись плейлиста в историю и инкрементируем счетчик
        uploader = cached.get("uploader") or "SoundCloud"
        await async_add_history_record(
            user_id=user_id,
            title=f"[PL] {title}",
            artist=uploader,
            platform="SoundCloud",
        )
        await async_increment_user_playlist_count(user_id)

        try:
            await progress.edit_text(
                get_text(
                    "playlist_sep_done",
                    lang,
                    sent=len(downloaded_results),
                    total=pluralize_tracks(total, lang),
                    title=title,
                )
            )
        except Exception:
            pass

    finally:
        finish_user_download(user_id)
        # Гарантированная очистка временных файлов
        for res in downloaded_results:
            if res and res.get("path"):
                cleanup_file(res["path"])

    PLAYLIST_CACHE.pop(cache_id, None)
    delete_playlist_cache(cache_id)
