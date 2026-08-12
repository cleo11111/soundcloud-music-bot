import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto, InputMediaAudio
from yt_dlp import YoutubeDL

from services.downloader import (
    async_download_song,
    cleanup_file,
    start_user_download,
    finish_user_download,
)
from services.db import async_add_history_record, async_get_user_language
from services.locales import format_cover_caption, get_text
from handlers.start import build_start_keyboard

import time
from services.logger import log_debug

router = Router()

# Хранилище результатов поиска в памяти (user_id -> {"query": str, "tracks": list, "timestamp": float})
SEARCH_CACHE = {}
CACHE_TTL = 1800  # 30 минут


def clean_old_search_cache():
    """Очищает результаты поиска в памяти старше 30 минут."""
    now = time.time()
    expired = [k for k, v in SEARCH_CACHE.items() if isinstance(v, dict) and now - v.get("timestamp", 0) > CACHE_TTL]
    for k in expired:
        SEARCH_CACHE.pop(k, None)
    if expired:
        log_debug(f"🧹 [Search Cache] Удалено {len(expired)} устаревших записей текстового поиска")


PER_PAGE = 5


def fetch_all_soundcloud(text: str, limit: int = 50):
    """Поиск треков на SoundCloud через yt-dlp."""
    search_query = f"scsearch{limit}:{text}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_query, download=False)
        return info.get("entries", []) if info else []


def build_search_keyboard(user_id: int, page: int = 0):
    """Строит клавиатуру с кнопками выбора треков и навигации по страницам."""
    tracks = SEARCH_CACHE.get(user_id, {}).get("tracks", [])
    total_tracks = len(tracks)
    max_pages = max(1, (total_tracks + PER_PAGE - 1) // PER_PAGE)

    start_idx = page * PER_PAGE
    end_idx = start_idx + PER_PAGE
    current_tracks = tracks[start_idx:end_idx]

    kb = []

    # Кнопки выбора конкретного трека (1..5)
    item_buttons = []
    for i in range(len(current_tracks)):
        global_idx = start_idx + i
        item_buttons.append(
            InlineKeyboardButton(text=str(i + 1), callback_data=f"dl_{global_idx}")
        )
    if item_buttons:
        kb.append(item_buttons)

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page - 1}")
        )

    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{max_pages}", callback_data="ignore")
    )

    if page < max_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page_{page + 1}")
        )

    kb.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=kb)


def format_page_text(query_text: str, tracks: list, page: int = 0):
    """Форматирует текст страницы с результатами поиска."""
    start_idx = page * PER_PAGE
    end_idx = start_idx + PER_PAGE
    current_tracks = tracks[start_idx:end_idx]

    text = f"🔍 Результаты по запросу: «{query_text}»\n"
    text += f"Найдено треков: {len(tracks)}\n\n"

    for i, track in enumerate(current_tracks, start=1):
        title = track.get("title", "Без названия")
        uploader = track.get("uploader", "SoundCloud")
        text += f"{i}. {title}\n   👤 {uploader}\n\n"

    text += "Нажмите на цифру, чтобы скачать трек:"
    return text


@router.message(F.text & ~F.text.startswith("http") & ~F.text.startswith("/"))
async def process_text_prompt(message: Message):
    """Если пользователь пишет обычный текст — просим скинуть ссылку или воспользоваться кнопками."""
    user_id = message.from_user.id
    lang = await async_get_user_language(user_id)
    text = get_text("text_prompt", lang)
    kb = build_start_keyboard(lang)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("page_"))
async def process_page_change(call: CallbackQuery):
    """Переключение страниц в результатах поиска."""
    page = int(call.data.split("_")[1])
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    cache = SEARCH_CACHE.get(user_id)

    if not cache or not cache.get("tracks"):
        await call.answer(get_text("data_expired", lang), show_alert=True)
        return

    tracks = cache["tracks"]
    query_text = cache.get("query", "")
    kb = build_search_keyboard(user_id, page=page)
    text = format_page_text(query_text, tracks, page=page)

    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "ignore")
async def process_ignore(call: CallbackQuery):
    """Игнорируем нажатие на кнопку-счётчик страниц."""
    await call.answer()


@router.callback_query(F.data.startswith("dl_"))
async def process_download_track(call: CallbackQuery):
    """Скачивание выбранного трека из результатов поиска."""
    track_idx = int(call.data.split("_")[1])
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    cache = SEARCH_CACHE.get(user_id)

    if not cache or not cache.get("tracks"):
        await call.answer(get_text("data_expired", lang), show_alert=True)
        return

    tracks = cache["tracks"]

    if track_idx >= len(tracks):
        await call.answer(get_text("err_track_not_found", lang), show_alert=True)
        return

    track = tracks[track_idx]
    url = track.get("url") or track.get("webpage_url")
    track_title = track.get("title", "Трек")

    if not start_user_download(user_id):
        await call.answer(get_text("err_already_downloading", lang), show_alert=True)
        return

    await call.answer(get_text("starting_download", lang))
    wait = await call.message.answer(get_text("downloading_track", lang, title=track_title))

    result = None
    try:
        result = await async_download_song(url)
        mp3_path = result["path"]

        if not mp3_path.exists():
            raise FileNotFoundError("MP3-файл не был создан.")

        file_size_mb = mp3_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 49.5:
            await call.message.answer(
                get_text("file_too_large", lang, title=result["title"], size=file_size_mb)
            )
            return

        audio = FSInputFile(mp3_path)
        cover_path = result.get("cover_path")
        thumb_path = result.get("thumb_path") or cover_path
        thumbnail = FSInputFile(thumb_path) if (thumb_path and thumb_path.exists()) else None

        # Если есть обложка — отправляем фото с инфой под ним
        if cover_path and cover_path.exists():
            caption = format_cover_caption(
                title=result["title"],
                artist=result["artist"],
                date=result.get("date"),
                lang=lang,
            )
            await call.message.answer_photo(FSInputFile(cover_path), caption=caption)

        # Отправляем аудио с 320x320 JPEG миниатюрой
        await call.message.answer_audio(
            audio,
            title=result["title"],
            performer=result["artist"],
            duration=result["duration"],
            thumbnail=thumbnail,
        )

        # Записываем в историю
        await async_add_history_record(
            user_id=user_id,
            title=result["title"],
            artist=result["artist"],
            platform="SoundCloud",
        )

    except RuntimeError as re:
        if "ERR_DISK_FULL" in str(re):
            await call.message.answer(get_text("err_disk_full", lang))
        else:
            await call.message.answer(get_text("err_generic", lang))
    except ValueError as ve:
        err_msg = str(ve)
        if err_msg.startswith("FILE_TOO_LARGE:"):
            parts = err_msg.split(":")
            title = parts[1] if len(parts) > 1 else "Трек"
            try:
                size_mb = float(parts[2])
            except Exception:
                size_mb = 50.0
            await call.message.answer(get_text("file_too_large", lang, title=title, size=size_mb))
        else:
            await call.message.answer(get_text("err_generic", lang))
    except Exception as e:
        log_error(f"⚠️ Ошибка в search.py: {e}", user_id=user_id)
        await call.message.answer(get_text("err_generic", lang))

    finally:
        finish_user_download(user_id)
        try:
            await wait.delete()
        except Exception:
            pass
        if result:
            cleanup_file(result.get("path"), result.get("cover_path"), result.get("thumb_path"))