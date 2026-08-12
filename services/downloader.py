import asyncio
import shutil
import urllib.request
from pathlib import Path

from services.logger import log_debug, log_info, log_error
import uuid

from yt_dlp import YoutubeDL

# Абсолютный путь, не зависит от рабочей директории запуска
DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True, mode=0o700)

ACTIVE_DOWNLOADS: set[int] = set()


def check_disk_space(min_free_mb: int = 500) -> bool:
    """Проверяет наличие свободного места на диске (минимум min_free_mb МБ)."""
    try:
        total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
        free_mb = free / (1024 * 1024)
        if free_mb < min_free_mb:
            log_error(f"⚠️ [КРИТИЧЕСКИ] Мало свободного места на сервере: {free_mb:.1f} MB (требуется {min_free_mb} MB)!")
            return False
        return True
    except Exception:
        return True


def check_ffmpeg_installed() -> bool:
    """Проверяет наличие утилиты ffmpeg в системе на старте."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        log_error("⚠️ [ВНИМАНИЕ] FFmpeg не найден на сервере! Скачивание и конвертация в MP3 не будут работать. Установите ffmpeg (например: sudo apt install ffmpeg).")
        return False
    log_info("✅ FFmpeg найден в системе!")
    return True


def start_user_download(user_id: int) -> bool:
    """Пытается зафиксировать активное скачивание для пользователя. Возвращает False, если скачивание уже идет."""
    if not user_id:
        return True
    if user_id in ACTIVE_DOWNLOADS:
        return False
    ACTIVE_DOWNLOADS.add(user_id)
    return True


def finish_user_download(user_id: int):
    """Освобождает статус скачивания для пользователя."""
    if user_id:
        ACTIVE_DOWNLOADS.discard(user_id)


def _get_best_thumbnail_url(info: dict) -> str | None:
    """Извлекает URL обложки максимального качества из info yt-dlp."""
    # Пробуем получить из thumbnail напрямую
    thumb = info.get("thumbnail")

    # Или из списка thumbnails — берём последний (обычно наибольший)
    thumbnails = info.get("thumbnails", [])
    if thumbnails:
        thumb = thumbnails[-1].get("url") or thumb

    if not thumb:
        return None

    # SoundCloud: заменяем размер на максимальный (t500x500)
    for mini_tag in ["-large", "-t50x50", "-small", "-badge", "-t120x120", "-t200x200"]:
        if mini_tag in thumb:
            thumb = thumb.replace(mini_tag, "-t500x500")
            break

    return thumb


def _download_thumbnail(url: str, save_path: Path) -> tuple[Path | None, Path | None]:
    """
    Скачивает обложку по URL, конвертирует в гарантированный JPEG через PIL.
    Возвращает (cover_path, thumb_path):
    - cover_path: полноразмерная обложка (JPEG) для фото и MP3 ID3
    - thumb_path: обжатая обложка 320x320 JPEG (<= 200KB) для аудиоплеера Telegram
    """
    import io
    from PIL import Image

    data = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            if len(data) < 100:
                return None, None

        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 1. Полноразмерная обложка (JPEG)
        img.save(save_path, "JPEG", quality=95)

        # 2. Обжатая миниатюра 320x320 JPEG для кружка Telegram audio player
        thumb_path = save_path.parent / f"{save_path.stem}_thumb.jpg"
        thumb_img = img.copy()
        thumb_img.thumbnail((320, 320), Image.Resampling.LANCZOS)
        thumb_img.save(thumb_path, "JPEG", quality=85)

        return save_path, thumb_path
    except Exception as e:
        log_error(f"⚠️ Ошибка обработки обложки PIL: {e}")
        try:
            if data:
                save_path.write_bytes(data)
                return save_path, None
        except Exception:
            pass
        return None, None


def _embed_cover_in_mp3(mp3_path: Path, cover_path: Path, title: str, artist: str):
    """Встраивает обложку и метаданные в MP3 через ID3-теги."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC, TIT2, TPE1, ID3NoHeaderError

        try:
            tags = ID3(str(mp3_path))
        except ID3NoHeaderError:
            tags = ID3()

        # Название и исполнитель
        tags.delall("TIT2")
        tags.delall("TPE1")
        tags.add(TIT2(encoding=3, text=title))
        tags.add(TPE1(encoding=3, text=artist))

        # Обложка
        cover_data = cover_path.read_bytes()
        suffix = cover_path.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"

        tags.delall("APIC")
        tags.add(APIC(
            encoding=3,
            mime=mime,
            type=3,  # Cover (front)
            desc="Cover",
            data=cover_data,
        ))

        tags.save(str(mp3_path))
        log_debug(f"✅ Обложка встроена в {mp3_path.name}")
    except Exception as e:
        log_error(f"⚠️ Не удалось встроить обложку в MP3: {e}")


def _cleanup_intermediates(base_path: Path):
    """Удаляет все промежуточные файлы с тем же именем (кроме .mp3)."""
    stem = base_path.stem
    parent = base_path.parent
    for f in parent.glob(f"{stem}.*"):
        if f.suffix != ".mp3":
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass


def download_song(url: str) -> dict:
    """
    Скачивает трек, конвертирует в mp3, встраивает обложку.
    Перед скачиванием проверяет доступное дисковое пространство и метаданные.
    """
    if not check_disk_space(300):
        raise RuntimeError("ERR_DISK_FULL")

    job_id = uuid.uuid4().hex[:10]
    job_dir = DOWNLOAD_DIR / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    filename = "track"

    # Предварительная проверка размера и длительности без скачивания байтов
    try:
        check_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
        }
        with YoutubeDL(check_opts) as ydl_check:
            info_check = ydl_check.extract_info(url, download=False)
            if info_check:
                duration = info_check.get("duration") or 0
                filesize = info_check.get("filesize") or info_check.get("filesize_approx") or 0
                title = info_check.get("title", "Трек")

                if filesize and filesize > 51904512:
                    raise ValueError(f"FILE_TOO_LARGE:{title}:{filesize / (1024 * 1024):.1f}")

                if duration and duration > 3300:
                    approx_mb = (duration * 128000 / 8) / (1024 * 1024)
                    raise ValueError(f"FILE_TOO_LARGE:{title}:{approx_mb:.1f}")
    except ValueError:
        raise
    except Exception:
        pass

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(job_dir / f"{filename}.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    metadata = {"title": "Неизвестный трек", "artist": "Неизвестен", "duration": None}
    mp3_path = job_dir / f"{filename}.mp3"
    cover_path = None
    thumb_path = None

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                metadata["title"] = info.get("title", "Неизвестный трек")
                metadata["artist"] = (
                    info.get("uploader")
                    or info.get("artist")
                    or info.get("creator")
                    or "Неизвестен"
                )
                raw_dur = info.get("duration")
                metadata["duration"] = int(raw_dur) if raw_dur is not None else None

                # Извлекаем дату публикации с SoundCloud
                raw_date = (
                    info.get("release_date")
                    or info.get("upload_date")
                    or info.get("created_at")
                    or info.get("date")
                )
                formatted_date = None

                if raw_date:
                    s = str(raw_date).strip()
                    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                        formatted_date = s[:10]
                    elif len(s) == 8 and s.isdigit():
                        formatted_date = f"{s[:4]}-{s[4:6]}-{s[6:]}"

                if not formatted_date:
                    ts = info.get("timestamp")
                    if ts:
                        try:
                            from datetime import datetime
                            formatted_date = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
                        except Exception:
                            pass

                metadata["date"] = formatted_date

                # Скачиваем и генерируем 320x320 JPEG миниатюру
                thumb_url = _get_best_thumbnail_url(info)
                if thumb_url:
                    cover_target = job_dir / f"{filename}_cover.jpg"
                    cover_path, thumb_path = _download_thumbnail(thumb_url, cover_target)

                # Проверка 3: Проверяем целостность сгенерированного MP3 файла (существование и размер > 1 КБ)
                if not mp3_path.exists() or mp3_path.stat().st_size < 1024:
                    _cleanup_intermediates(mp3_path)
                    raise FileNotFoundError("Сгенерированный MP3-файл отсутствует или поврежден (размер < 1 КБ).")

                # Встраиваем обложку и метаданные в MP3
                if cover_path and cover_path.exists():
                    _embed_cover_in_mp3(mp3_path, cover_path, metadata["title"], metadata["artist"])
    finally:
        _cleanup_intermediates(mp3_path)

    return {
        "path": mp3_path,
        "title": metadata["title"],
        "artist": metadata["artist"],
        "duration": metadata["duration"],
        "date": metadata.get("date"),
        "cover_path": cover_path,
        "thumb_path": thumb_path,
    }


async def async_download_song(url: str) -> dict:
    """Асинхронная обёртка — не блокирует event loop."""
    return await asyncio.to_thread(download_song, url)


import time


def cleanup_file(*file_paths: Path | None):
    """Безопасно удаляет mp3 файлы, обложки, миниатюры и директории скачиваний внутри DOWNLOAD_DIR."""
    for file_path in file_paths:
        if not file_path:
            continue

        try:
            resolved_target = file_path.resolve()
            resolved_download_dir = DOWNLOAD_DIR.resolve()
            # Запрет удаления/открытия любых файлов за пределами downloads/
            if not resolved_target.is_relative_to(resolved_download_dir):
                log_error(f"⚠️ Попытка доступа к недопустимому пути вне downloads: {file_path}")
                continue
        except Exception:
            pass

        # Если передан путь к директории задания (job_* / pl_job_*)
        if file_path.is_dir():
            try:
                shutil.rmtree(file_path, ignore_errors=True)
            except Exception:
                pass
            continue

        stem = file_path.stem
        parent = file_path.parent
        # Удаляем все связанные файлы трека (mp3, cover, thumb) в downloads/
        for f in parent.glob(f"{stem}*"):
            try:
                if f.is_file():
                    f.unlink(missing_ok=True)
            except OSError:
                pass

        # Если родительская папка является временной директорией задания (job_* / pl_job_*)
        try:
            if parent != DOWNLOAD_DIR and parent.name.startswith(("job_", "pl_job_")):
                if not any(parent.iterdir()):
                    shutil.rmtree(parent, ignore_errors=True)
        except Exception:
            pass


def sweep_stale_job_dirs(max_age_hours: int = 6):
    """Очищает устаревшие временные папки скачиваний (job_* / pl_job_*) старше max_age_hours часов."""
    now = time.time()
    max_age_sec = max_age_hours * 3600
    cleaned_count = 0

    try:
        if not DOWNLOAD_DIR.exists():
            return
        for p in DOWNLOAD_DIR.glob("*"):
            if p.is_dir() and p.name.startswith(("job_", "pl_job_")):
                try:
                    mtime = p.stat().st_mtime
                    if (now - mtime > max_age_sec) or not any(p.iterdir()):
                        shutil.rmtree(p, ignore_errors=True)
                        cleaned_count += 1
                except Exception:
                    pass
    except Exception as e:
        log_error(f"⚠️ Ошибка очистки устаревших папок скачиваний: {e}")

    if cleaned_count > 0:
        log_debug(f"🧹 [Cleanup] Удалено {cleaned_count} устаревших/пустых папок скачивания в downloads/")


# ─── Плейлисты ───────────────────────────────────────────────────────


def fetch_playlist_info(url: str) -> dict:
    """
    Извлекает метаданные плейлиста (название, автор, список треков)
    через yt-dlp с extract_flat=True (не скачивая аудио).
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
        "socket_timeout": 15,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return {}

        entries = info.get("entries", [])
        valid = [e for e in entries if e and (e.get("url") or e.get("webpage_url"))]

        return {
            "title": info.get("title", "Плейлист"),
            "uploader": info.get("uploader", "SoundCloud"),
            "track_count": len(valid),
            "entries": valid,
            "url": url,
            "thumbnail": info.get("thumbnail"),
        }


async def async_fetch_playlist_info(url: str) -> dict:
    """Асинхронная обёртка для fetch_playlist_info."""
    return await asyncio.to_thread(fetch_playlist_info, url)


def download_playlist_as_zip(entries: list, playlist_title: str) -> dict:
    """
    Скачивает все треки из entries и упаковывает в ZIP-архив(ы).
    Если общий размер превышает 45 МБ, разбивает на части.
    Использует изолированную рабочую папку.
    """
    import zipfile

    if not check_disk_space(500):
        raise RuntimeError("ERR_DISK_FULL")

    job_id = uuid.uuid4().hex[:10]
    pl_job_dir = DOWNLOAD_DIR / f"pl_job_{job_id}"
    pl_job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    MAX_PART_BYTES = 45 * 1024 * 1024  # 45 MB
    downloaded = []
    zip_paths = []

    try:
        for entry in entries:
            url = entry.get("url") or entry.get("webpage_url")
            if not url:
                continue
            try:
                result = download_song(url)
                downloaded.append(result)
            except Exception as e:
                log_error(f"⚠️ [ZIP] Не удалось скачать трек: {e}")

        if not downloaded:
            raise Exception("Не удалось скачать ни одного трека из плейлиста.")

        current_part = 1
        current_zip_path = pl_job_dir / f"playlist_part{current_part}.zip"
        current_zf = zipfile.ZipFile(current_zip_path, "w", zipfile.ZIP_DEFLATED)
        current_size = 0

        for i, res in enumerate(downloaded, 1):
            mp3 = res["path"]
            if not mp3.exists():
                continue
            file_size = mp3.stat().st_size

            if current_size > 0 and (current_size + file_size) > MAX_PART_BYTES:
                current_zf.close()
                zip_paths.append(current_zip_path)

                current_part += 1
                current_zip_path = pl_job_dir / f"playlist_part{current_part}.zip"
                current_zf = zipfile.ZipFile(current_zip_path, "w", zipfile.ZIP_DEFLATED)
                current_size = 0

            safe = "".join(
                c for c in res["title"]
                if c.isalnum() or c in " -_()"
            ).strip() or f"track_{i}"

            current_zf.write(mp3, f"{i:02d}. {safe}.mp3")
            current_size += file_size

        current_zf.close()
        if current_zip_path.exists() and current_zip_path.stat().st_size > 0:
            zip_paths.append(current_zip_path)

        return {
            "zip_paths": zip_paths,
            "zip_path": zip_paths[0] if zip_paths else None,
            "track_count": len(downloaded),
            "tracks": [{"title": r["title"], "artist": r["artist"]} for r in downloaded],
            "job_dir": pl_job_dir,
        }

    except Exception:
        for zp in zip_paths:
            if zp and zp.exists():
                zp.unlink(missing_ok=True)
        cleanup_file(pl_job_dir)
        raise

    finally:
        # Чистим отдельные mp3 и вложенные файлы после упаковки
        for res in downloaded:
            cleanup_file(res["path"], res.get("cover_path"), res.get("thumb_path"))


async def async_download_playlist_as_zip(entries: list, playlist_title: str) -> dict:
    """Асинхронная обёртка для download_playlist_as_zip."""
    return await asyncio.to_thread(download_playlist_as_zip, entries, playlist_title)