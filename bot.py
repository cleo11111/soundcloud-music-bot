import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand


async def setup_bot_commands(bot: Bot):
    """Регистрирует список команд в меню Telegram."""
    commands = [
        BotCommand(command="start", description="Главное меню / Main menu"),
        BotCommand(command="history", description="История скачиваний / Download history"),
        BotCommand(command="clear_history", description="Очистить историю / Clear history"),
        BotCommand(command="support", description="Написать разработчику / Support"),
        BotCommand(command="help", description="Справка / Help"),
    ]
    await bot.set_my_commands(commands)

from config import BOT_TOKEN
from services.db import async_init_db, async_clean_expired_history
from handlers.start import router as start_router
from handlers.inline import router as inline_router
from handlers.inline_playlist import router as inline_playlist_router
from handlers.search import router as search_router
from handlers.download import router as download_router
from handlers.history import router as history_router
from handlers.support import router as support_router


from handlers.inline import clean_old_cache as clean_inline_cache
from handlers.inline_playlist import _clean_caches as clean_playlist_caches
from handlers.search import clean_old_search_cache
from services.downloader import sweep_stale_job_dirs
from services.logger import log_info, log_error


async def periodic_cache_cleanup():
    """Фоновая задача: каждые 10 минут очищает оперативные кэши, устаревшие папки и ротирует историю."""
    while True:
        await asyncio.sleep(600)  # 10 минут
        try:
            clean_inline_cache()
            clean_playlist_caches()
            clean_old_search_cache()
            sweep_stale_job_dirs(max_age_hours=6)
            await async_clean_expired_history(90)
        except Exception as e:
            log_error(f"⚠️ Ошибка фоновой очистки кэша: {e}")


from services.downloader import check_ffmpeg_installed

async def main():
    await async_init_db()
    check_ffmpeg_installed()

    # Запуск фоновой периодической очистки кэша оперативной памяти
    asyncio.create_task(periodic_cache_cleanup())

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    await setup_bot_commands(bot)

    # Порядок важен:
    #   inline_playlist (фильтр /playlist) → inline (catch-all) →
    #   start → history → search → inline_playlist (сообщения/callback) →
    #   download (catch-all для ссылок)
    dp.include_router(inline_playlist_router)
    dp.include_router(inline_router)
    dp.include_router(start_router)
    dp.include_router(history_router)
    dp.include_router(support_router)
    dp.include_router(search_router)
    dp.include_router(download_router)

    from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
    from aiogram.types import ErrorEvent

    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        exception = event.exception
        if isinstance(exception, TelegramForbiddenError):
            log_info("ℹ️ Игнорирование: пользователь заблокировал бота или остановил чат.")
            return True
        if isinstance(exception, TelegramBadRequest):
            log_info(f"ℹ️ Игнорирование Telegram BadRequest: {exception}")
            return True
        return False

    log_info("🚀 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())