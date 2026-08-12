import asyncio
import time
import uuid
from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.exceptions import TelegramBadRequest
from yt_dlp import YoutubeDL
from services.db import async_get_user_language
from services.locales import get_text
from services.logger import log_debug, log_info, log_error

router = Router()

PER_PAGE = 25
CACHE_TTL = 900  # 15 минут

SEARCH_CACHE = {}
BAN_UNTIL = 0.0

YDL_OPTS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": True,
    "skip_download": True,
    "ignoreerrors": True,
    "socket_timeout": 10,
}




def fetch_soundcloud(text: str, limit: int):
    """Поиск треков SoundCloud через yt-dlp (синхронный)."""
    search_query = f"scsearch{limit}:{text}"
    with YoutubeDL(YDL_OPTS_BASE) as ydl:
        info = ydl.extract_info(search_query, download=False)
        return info.get("entries", []) if info else []


def _get_entry_url(entry):
    """Извлекает URL трека для дедупликации."""
    return entry.get("url") or entry.get("webpage_url") or ""


def _merge_entries(existing: list, new_entries: list) -> list:
    """Объединяет результаты без дубликатов, сохраняя порядок."""
    seen_urls = set()
    merged = []

    for entry in existing:
        url = _get_entry_url(entry)
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(entry)

    for entry in new_entries:
        if not entry:
            continue
        url = _get_entry_url(entry)
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(entry)

    return merged


FETCH_SEMAPHORE = asyncio.Semaphore(5)
USER_LAST_QUERY = {}
USER_QUERY_TTL = 0.3  # Защита от спама инлайн-запросами


async def bg_fetch_pipeline(text: str):
    """Фоновый конвейер: подгружает треки шагами с подконтрольным лимитом (до 1000 треков)."""
    global BAN_UNTIL
    if text not in SEARCH_CACHE or SEARCH_CACHE[text]["fetching"]:
        return

    # Ограничение до 5 одновременных задач фонового конвейера
    if FETCH_SEMAPHORE.locked():
        log_debug(f"⚠️ [Конвейер] Сработало ограничение задач (max 5). Пропуск фоновой подгрузки для '{text}'")
        return

    async with FETCH_SEMAPHORE:
        if text not in SEARCH_CACHE or SEARCH_CACHE[text]["fetching"]:
            return

        SEARCH_CACHE[text]["fetching"] = True
        # Разумный потолок 1000 треков (вместо 10 000) для предотвращения перегрузки
        target_steps = [100, 200, 500, 1000]

        try:
            for limit in target_steps:
                if text not in SEARCH_CACHE:
                    break

                cache = SEARCH_CACHE[text]
                if cache.get("has_reached_end"):
                    break

                count_before = len(cache["entries"])
                if count_before >= limit:
                    continue

                log_debug(f"🔄 [Конвейер] scsearch{limit} для '{text}' (сейчас {count_before} треков)...")
                start_time = time.time()

                raw_entries = await asyncio.to_thread(fetch_soundcloud, text, limit)
                valid_new = [e for e in raw_entries if e and _get_entry_url(e)]
                elapsed = round(time.time() - start_time, 2)

                if text not in SEARCH_CACHE:
                    break

                merged = _merge_entries(cache["entries"], valid_new)
                SEARCH_CACHE[text]["entries"] = merged

                new_added = len(merged) - count_before
                log_debug(f"✅ [Конвейер] +{new_added} новых, итого {len(merged)} треков ({elapsed} сек).")

                if new_added == 0:
                    SEARCH_CACHE[text]["has_reached_end"] = True
                    log_debug(f"🏁 [Конвейер] Все результаты загружены для '{text}': {len(merged)} треков.")
                    break

                await asyncio.sleep(1.0)

        except Exception as e:
            err_str = str(e)
            log_error(f"❌ [Конвейер Error] {e}")
            if "429" in err_str or "Too Many Requests" in err_str:
                log_error("⛔ [SoundCloud Ban] Пауза 60 сек.")
                BAN_UNTIL = time.time() + 60.0
        finally:
            if text in SEARCH_CACHE:
                SEARCH_CACHE[text]["fetching"] = False


def clean_old_cache():
    """Удаляет устаревшие записи кэша."""
    now = time.time()
    expired = [k for k, v in SEARCH_CACHE.items() if now - v["timestamp"] > CACHE_TTL]
    for k in expired:
        del SEARCH_CACHE[k]


@router.inline_query()
async def inline_search(query: InlineQuery):
    global BAN_UNTIL
    text = query.query.strip().lower()

    if not text or len(text) < 2 or text.startswith("/playlist"):
        return

    # Если в инлайн-поиск вставили прямую ссылку — предлагаем 1 клик для отправки и скачивания
    if text.startswith("http://") or text.startswith("https://") or "soundcloud.com" in text:
        raw_url = query.query.strip()
        if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
            raw_url = "https://" + raw_url
        msg_content = f"🎶DL::{raw_url}"
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id="direct_link_inline",
                    title="📥 Нажмите, чтобы скачать трек по ссылке",
                    description=raw_url,
                    input_message_content=InputTextMessageContent(
                        message_text=msg_content
                    )
                )
            ],
            cache_time=1,
            is_personal=False
        )
        return

    offset = int(query.offset) if query.offset else 0

    try:
        clean_old_cache()

        # Защита от rate-limit SoundCloud
        if time.time() < BAN_UNTIL:
            left_sec = int(BAN_UNTIL - time.time())
            lang = await async_get_user_language(query.from_user.id)
            await query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="ban_info",
                        title=get_text("ban_title", lang),
                        description=get_text("ban_desc", lang, sec=left_sec),
                        input_message_content=InputTextMessageContent(
                            message_text=get_text("ban_message", lang)
                        )
                    )
                ],
                cache_time=1,
                is_personal=False
            )
            return

        # Первая выгрузка — берем 50 треков для быстрого ответа
        if text not in SEARCH_CACHE:
            start_time = time.time()
            try:
                raw_entries = await asyncio.to_thread(fetch_soundcloud, text, 50)
                valid_entries = [e for e in raw_entries if e and _get_entry_url(e)]
                elapsed = round(time.time() - start_time, 2)
                log_debug(f"✅ [Inline] Найдено {len(valid_entries)} треков за {elapsed} сек.")

                SEARCH_CACHE[text] = {
                    "timestamp": time.time(),
                    "entries": valid_entries,
                    "fetching": False,
                    "has_reached_end": False,  # Всегда пробуем подгрузить ещё
                }

                # Запуск фоновой дозагрузки
                asyncio.create_task(bg_fetch_pipeline(text))
            except Exception as e:
                err_str = str(e)
                print(f"❌ [Inline Fetch Error] {e}")
                if "429" in err_str or "Too Many Requests" in err_str:
                    BAN_UNTIL = time.time() + 60.0
                SEARCH_CACHE[text] = {
                    "timestamp": time.time(),
                    "entries": [],
                    "fetching": False,
                    "has_reached_end": True,
                }

        cache_info = SEARCH_CACHE[text]

        # Ждём дозагрузки если скролл обогнал конвейер (до 20 сек)
        if offset >= len(cache_info["entries"]) and (cache_info["fetching"] or not cache_info["has_reached_end"]):
            for _ in range(80):
                await asyncio.sleep(0.25)
                if len(cache_info["entries"]) > offset:
                    break

        all_entries = cache_info["entries"]
        page_entries = all_entries[offset:offset + PER_PAGE]

        results = []
        for index, entry in enumerate(page_entries):
            video_url = _get_entry_url(entry)
            if not video_url:
                continue

            title = entry.get("title", "Неизвестный трек")
            uploader = entry.get("uploader", "SoundCloud")

            # Обложка в высоком разрешении
            thumbnails = entry.get("thumbnails", [])
            thumb_url = None
            if thumbnails:
                thumb_url = thumbnails[-1].get("url")
                if thumb_url:
                    for mini_tag in ["-large", "-t50x50", "-small", "-badge"]:
                        if mini_tag in thumb_url:
                            thumb_url = thumb_url.replace(mini_tag, "-t500x500")
                            break

            global_id = uuid.uuid4().hex[:12]

            results.append(
                InlineQueryResultArticle(
                    id=global_id,
                    title=title,
                    description=uploader,
                    thumbnail_url=thumb_url,
                    thumbnail_width=500,
                    thumbnail_height=500,
                    input_message_content=InputTextMessageContent(
                        message_text=video_url
                    )
                )
            )

        # Пагинация — продолжаем пока есть данные или конвейер работает
        has_more_in_memory = (offset + len(page_entries)) < len(all_entries)
        not_end = not cache_info["has_reached_end"]
        still_fetching = cache_info["fetching"]

        if has_more_in_memory or not_end or still_fetching:
            next_offset = str(offset + len(page_entries))
        else:
            next_offset = ""

        await query.answer(
            results,
            next_offset=next_offset,
            cache_time=2,
            is_personal=False
        )

    except TelegramBadRequest:
        pass
    except Exception as e:
        print(f"💥 [Inline Error] {e}")