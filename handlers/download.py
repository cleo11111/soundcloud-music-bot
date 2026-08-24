from pathlib import Path
import traceback

from aiogram import Router, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from services.downloader import (
    async_download_song,
    cleanup_file,
    start_user_download,
    finish_user_download,
)
from services.db import (
    async_add_history_record,
    async_get_user_language,
    async_can_user_download_track,
    async_increment_user_track_count,
)
from services.locales import format_cover_caption, get_text
from services.logger import log_info, log_error, log_debug

import urllib.parse

router = Router()


SYSTEM_PATHS = {"/discover", "/feed", "/you", "/upload", "/stream", "/search", "/terms-of-use", "/people", "/settings", "/pages", "/imprint"}


def is_valid_soundcloud_url(url: str) -> bool:
    """Строго проверяет домен адреса на принадлежность к публичному треку/плейлисту SoundCloud."""
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


import re


async def _process_download_url(message: Message, url: str):
    """Общий процессор скачивания одиночного трека по URL."""
    user_id = message.from_user.id
    lang = await async_get_user_language(user_id)

    if not is_valid_soundcloud_url(url):
        if message.chat.type == "private":
            await message.answer(get_text("only_soundcloud", lang))
        return

    if "/sets/" in url:
        return

    allowed, status_code = await async_can_user_download_track(user_id)
    if not allowed:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=get_text("btn_premium", lang), callback_data="cmd_premium")]
            ]
        )
        await message.answer(get_text("err_daily_tracks_limit", lang), reply_markup=kb, parse_mode="HTML")
        return

    if not start_user_download(user_id):
        await message.answer(get_text("err_already_downloading", lang))
        return

    wait = await message.answer(get_text("downloading_song", lang))

    result = None
    try:
        result = await async_download_song(url)
        mp3_path = result["path"]

        if not mp3_path.exists():
            raise FileNotFoundError("MP3-файл не был создан.")

        file_size_mb = mp3_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 49.5:
            await message.answer(
                get_text("file_too_large", lang, title=result["title"], size=file_size_mb)
            )
            return

        audio = FSInputFile(mp3_path)
        cover_path = result.get("cover_path")
        thumb_path = result.get("thumb_path") or cover_path
        thumbnail = FSInputFile(thumb_path) if (thumb_path and thumb_path.exists()) else None

        if cover_path and cover_path.exists():
            caption = format_cover_caption(
                title=result["title"],
                artist=result["artist"],
                date=result.get("date"),
                lang=lang,
            )
            await message.answer_photo(FSInputFile(cover_path), caption=caption)

        await message.answer_audio(
            audio,
            title=result["title"],
            performer=result["artist"],
            duration=result["duration"],
            thumbnail=thumbnail,
        )

        platform = "SoundCloud"

        await async_add_history_record(
            user_id=user_id,
            title=result["title"],
            artist=result["artist"],
            platform=platform,
        )
        await async_increment_user_track_count(user_id)

        try:
            await message.delete()
        except Exception:
            pass

    except RuntimeError as err_rt:
        if "ERR_DISK_FULL" in str(err_rt):
            await message.answer(get_text("err_disk_full", lang))
        else:
            await message.answer(get_text("err_generic", lang))
    except ValueError as ve:
        err_msg = str(ve)
        if err_msg.startswith("FILE_TOO_LARGE:"):
            parts = err_msg.split(":")
            title = parts[1] if len(parts) > 1 else "Трек"
            try:
                size_mb = float(parts[2])
            except Exception:
                size_mb = 50.0
            await message.answer(get_text("file_too_large", lang, title=title, size=size_mb))
        else:
            await message.answer(get_text("err_generic", lang))
    except Exception as e:
        log_error(f"Ошибка обработки ссылки: {e}", user_id=user_id)
        err = str(e).lower()
        if "drm" in err:
            await message.answer(get_text("err_drm", lang))
        elif "404" in err or "not found" in err:
            await message.answer(get_text("err_404", lang))
        elif "403" in err or "forbidden" in err:
            await message.answer(get_text("err_403", lang))
        elif "429" in err or "too many" in err:
            await message.answer(get_text("err_429", lang))
        else:
            await message.answer(get_text("err_generic", lang))

    finally:
        finish_user_download(user_id)
        try:
            await wait.delete()
        except Exception:
            pass
        if result:
            cleanup_file(result.get("path"), result.get("cover_path"), result.get("thumb_path"))


@router.message(F.text.contains("soundcloud.com") | F.text.startswith("http") | F.caption.contains("soundcloud.com"))
async def download(message: Message):
    raw_text = message.text or message.caption or ""
    match = re.search(r'https?://[^\s]+', raw_text)
    if not match:
        return
    url = match.group(0).strip()
    await _process_download_url(message, url)
