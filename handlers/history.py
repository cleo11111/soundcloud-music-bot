from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from services.db import (
    async_get_user_history,
    async_get_user_language,
    async_clear_user_history,
    async_clear_user_history_days,
)
from services.locales import get_text

router = Router()


def build_history_keyboard(lang: str, page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с пагинацией (⬅️ Назад | Вперёд ➡️) и кнопкой '🗑 Очистить историю'."""
    kb = []
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"hist_page_{page-1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ▫️ ", callback_data="hist_noop"))

        nav_row.append(InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data="hist_noop"))

        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"hist_page_{page+1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ▫️ ", callback_data="hist_noop"))
        kb.append(nav_row)

    btn_text = get_text("btn_clear_history", lang)
    kb.append([InlineKeyboardButton(text=btn_text, callback_data="clear_hist_prompt")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def build_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора периода очистки истории."""
    kb = [
        [InlineKeyboardButton(text=get_text("btn_clear_7days", lang), callback_data="clear_hist_7days")],
        [InlineKeyboardButton(text=get_text("btn_clear_all", lang), callback_data="clear_hist_all")],
        [InlineKeyboardButton(text=get_text("btn_cancel_clear", lang), callback_data="clear_hist_cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


from services.db import (
    async_get_user_history,
    async_get_user_language,
    async_clear_user_history,
    async_clear_user_history_days,
    async_get_user_premium_status,
)

async def send_user_history(user_id: int, answer_func, page: int = 1):
    """Формирует и отправляет историю скачиваний пользователя с пагинацией (по 10 записей на страницу)."""
    lang = await async_get_user_language(user_id)
    status = await async_get_user_premium_status(user_id)
    limit = 50 if status["is_premium"] else 20
    history = await async_get_user_history(user_id, limit=limit, lang=lang)

    if not history:
        await answer_func(get_text("history_empty", lang))
        return

    items_per_page = 10
    total_items = len(history)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_items = history[start_idx:end_idx]

    lines = [get_text("history_title", lang)]

    for i, item in enumerate(page_items, start_idx + 1):
        title = item["title"]
        artist = item["artist"]
        platform = item["platform"]
        date_str = item["date_formatted"]

        # Динамический перевод префикса плейлиста в зависимости от активного языка
        if title.startswith("Плейлист: ") or title.startswith("Playlist: ") or title.startswith("[PL] "):
            clean_title = title.replace("Плейлист: ", "").replace("Playlist: ", "").replace("[PL] ", "")
            prefix = get_text("playlist_prefix", lang)
            title = f"{prefix}{clean_title}"

        lines.append(
            f"<b>{i}. {title} – {artist}</b>\n"
            f"   🎵 {platform}\n"
            f"   🕒 {date_str}\n"
        )

    text = "\n".join(lines)
    kb = build_history_keyboard(lang, page=page, total_pages=total_pages)
    await answer_func(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("history"))
async def process_history_command(message: Message):
    """Обработчик команды /history."""
    await send_user_history(message.from_user.id, message.answer, page=1)


@router.callback_query(F.data == "cmd_history")
async def process_history_callback(call: CallbackQuery):
    """Обработчик нажатия на кнопку '📄 История скачиваний'."""
    await send_user_history(call.from_user.id, call.message.answer, page=1)
    await call.answer()


@router.callback_query(F.data.startswith("hist_page_"))
async def process_history_page_callback(call: CallbackQuery):
    """Переключение страниц истории."""
    page_str = call.data.split("hist_page_")[-1]
    try:
        page = int(page_str)
    except ValueError:
        page = 1
    await send_user_history(call.from_user.id, call.message.edit_text, page=page)
    await call.answer()


@router.callback_query(F.data == "hist_noop")
async def process_hist_noop_callback(call: CallbackQuery):
    """Пустой клик по индикатору страницы."""
    await call.answer()


@router.message(Command("clear_history"))
async def process_clear_history_command(message: Message):
    """Обработчик команды /clear_history — запрашивает выбор периода."""
    lang = await async_get_user_language(message.from_user.id)
    kb = build_confirm_keyboard(lang)
    await message.answer(get_text("confirm_clear_history", lang), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "clear_hist_prompt")
async def process_clear_prompt_callback(call: CallbackQuery):
    """Запрос выбора периода очистки истории через инлайн-кнопку."""
    lang = await async_get_user_language(call.from_user.id)
    kb = build_confirm_keyboard(lang)
    await call.message.edit_text(get_text("confirm_clear_history", lang), reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "clear_hist_7days")
async def process_clear_7days_callback(call: CallbackQuery):
    """Удаление истории за последние 7 дней."""
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    await async_clear_user_history_days(user_id, days=7)

    await call.message.edit_text(get_text("history_cleared_7days", lang))
    await call.answer()


@router.callback_query(F.data.in_({"clear_hist_all", "clear_hist_confirm"}))
async def process_clear_all_callback(call: CallbackQuery):
    """Полное удаление всей истории."""
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    await async_clear_user_history(user_id)

    await call.message.edit_text(get_text("history_cleared_all", lang))
    await call.answer()


@router.callback_query(F.data == "clear_hist_cancel")
async def process_clear_cancel_callback(call: CallbackQuery):
    """Отмена очистки истории."""
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    await call.message.edit_text(get_text("action_cancelled", lang))
    await call.answer()
