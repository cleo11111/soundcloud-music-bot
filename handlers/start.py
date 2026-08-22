from datetime import datetime
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID
from services.db import (
    async_get_user_language,
    async_set_user_language,
    async_get_user_premium_status,
    async_set_user_premium,
    async_ensure_user_exists,
    hash_user_id,
)
from services.locales import get_text
from services.payment import async_get_tribute_pay_url, async_check_tribute_payment
from services.logger import log_info, log_error

router = Router()


def build_start_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Строит инлайн-клавиатуру для главного меню."""
    kb = [
        [
            InlineKeyboardButton(
                text=get_text("btn_search_track", lang),
                switch_inline_query_current_chat="",
            ),
            InlineKeyboardButton(
                text=get_text("btn_search_playlist", lang),
                switch_inline_query_current_chat="/playlist ",
            ),
        ],
        [
            InlineKeyboardButton(
                text=get_text("btn_premium", lang),
                callback_data="cmd_premium",
            ),
            InlineKeyboardButton(
                text=get_text("btn_history", lang),
                callback_data="cmd_history",
            ),
        ],
        [
            InlineKeyboardButton(
                text=get_text("btn_support", lang),
                callback_data="cmd_support",
            ),
            InlineKeyboardButton(
                text=get_text("btn_language", lang),
                callback_data="cmd_lang_select",
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    # Сбрасываем любое активное состояние FSM (например, ожидание сообщения
    # для поддержки), чтобы /start всегда возвращал пользователя в чистое
    # состояние, а не "застревал" в предыдущем сценарии.
    await state.clear()

    user_id = message.from_user.id
    await async_ensure_user_exists(user_id)
    lang = await async_get_user_language(user_id)
    me = await message.bot.get_me()
    bot_username = me.username or "bot"
    text = get_text("welcome", lang, bot_username=bot_username)
    kb = build_start_keyboard(lang)
    await message.answer(text, reply_markup=kb)


@router.message(Command("help"))
async def process_help_command(message: Message, state: FSMContext):
    """Обработчик команды /help — выводит справку по поиску и командам."""
    # Аналогично /start — сбрасываем FSM-состояние, чтобы /help тоже
    # выводил пользователя из "застрявших" сценариев (например, поддержки).
    await state.clear()

    user_id = message.from_user.id
    lang = await async_get_user_language(user_id)
    me = await message.bot.get_me()
    bot_username = me.username or "bot"
    text = get_text("help_text", lang, bot_username=bot_username)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("premium"))
@router.callback_query(F.data == "cmd_premium")
async def process_premium_command(event: Message | CallbackQuery):
    """Показывает меню с информацией о премиуме и кнопкой оплаты через Tribute."""
    user_id = event.from_user.id
    lang = await async_get_user_language(user_id)
    status = await async_get_user_premium_status(user_id)

    if status.get("is_whitelisted"):
        text = get_text("premium_active_whitelisted", lang)
        kb = None
    elif status["is_premium"]:
        expires_at = status["expires_at"] or "Активна"
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            expires_formatted = exp_dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            expires_formatted = str(expires_at)

        text = get_text("premium_active_status", lang, expires_at=expires_formatted)
        kb = None
    else:
        text = get_text("premium_info", lang)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=get_text("btn_buy_tribute", lang), callback_data="create_tribute_invoice")]
            ]
        )

    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "create_tribute_invoice")
async def process_create_tribute_invoice(call: CallbackQuery):
    """Формирует ссылку на оплату через Tribute."""
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)

    pay_url = await async_get_tribute_pay_url(user_id)
    if not pay_url:
        await call.answer(get_text("err_token_missing", lang), show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_text("btn_buy_tribute", lang), url=pay_url)],
            [InlineKeyboardButton(text=get_text("btn_check_pay", lang), callback_data=f"check_tribute_pay_{user_id}")],
        ]
    )

    await call.message.answer(get_text("invoice_created", lang), reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("check_tribute_pay_"))
async def process_check_tribute_pay(call: CallbackQuery):
    """Проверяет статус оплаты в Tribute."""
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)

    is_paid = await async_check_tribute_payment(user_id)

    if is_paid:
        await async_set_user_premium(user_id, days=30)
        u_hash = hash_user_id(user_id)[:8]

        await call.answer(get_text("pay_success_alert", lang), show_alert=True)

        prem_status = await async_get_user_premium_status(user_id)
        exp_dt = datetime.fromisoformat(prem_status["expires_at"])
        expires_formatted = exp_dt.strftime("%d.%m.%Y %H:%M")

        await call.message.edit_text(
            get_text("premium_active_status", lang, expires_at=expires_formatted),
            parse_mode="HTML",
        )

        if ADMIN_ID:
            try:
                await call.bot.send_message(
                    ADMIN_ID,
                    f"💰 <b>Новая оплата подписки!</b>\nПользователь <code>[user:{u_hash}]</code> успешно оплатил подписку через Tribute!",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    else:
        if ADMIN_ID:
            try:
                u_hash = hash_user_id(user_id)[:8]
                adm_kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Подтвердить и выдать премиум ($1)", callback_data=f"admin_grant_prem_{user_id}")]
                    ]
                )
                await call.bot.send_message(
                    ADMIN_ID,
                    f"💳 <b>Пользователь нажал «Проверить оплату» (Tribute)!</b>\n"
                    f"Пользователь: <code>[user:{u_hash}]</code> (ID: <code>{user_id}</code>)\n\n"
                    f"Проверьте уведомление в @tribute и нажмите кнопку ниже для мгновенной активации:",
                    reply_markup=adm_kb,
                    parse_mode="HTML",
                )
            except Exception:
                pass
        await call.answer(get_text("pay_checking_notice", lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_grant_prem_"))
async def process_admin_grant_prem(call: CallbackQuery):
    """Ручное подтверждение оплаты администратором из уведомления в 1 клик."""
    if call.from_user.id != ADMIN_ID:
        return

    target_uid_str = call.data.split("admin_grant_prem_")[-1]
    try:
        target_uid = int(target_uid_str)
        await async_set_user_premium(target_uid, days=30)
        u_hash = hash_user_id(target_uid)[:8]

        await call.message.edit_text(
            f"✅ <b>Подписка успешно активирована!</b>\nПользователю <code>[user:{u_hash}]</code> выдан 💎 премиум на 30 дней.",
            parse_mode="HTML",
        )

        try:
            u_lang = await async_get_user_language(target_uid)
            await call.bot.send_message(
                target_uid,
                get_text("pay_success_alert", u_lang),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except ValueError:
        await call.answer("❌ Ошибка ID.", show_alert=True)


def build_lang_keyboard() -> InlineKeyboardMarkup:
    """Строит клавиатуру выбора языка."""
    kb = [
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.callback_query(F.data == "cmd_lang_select")
async def process_lang_select(call: CallbackQuery):
    """Показывает меню выбора языка."""
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    text = get_text("select_language", lang)
    await call.message.edit_text(text, reply_markup=build_lang_keyboard())
    await call.answer()


@router.callback_query(F.data.startswith("set_lang_"))
async def process_set_language(call: CallbackQuery):
    """Сохраняет выбранный язык и обновляет главное меню."""
    new_lang = call.data.split("_")[-1]
    if new_lang not in ("ru", "en"):
        new_lang = "ru"

    user_id = call.from_user.id
    await async_set_user_language(user_id, new_lang)

    me = await call.bot.get_me()
    bot_username = me.username or "bot"
    text = get_text("welcome", new_lang, bot_username=bot_username)
    kb = build_start_keyboard(new_lang)

    await call.message.edit_text(text, reply_markup=kb)
    await call.answer(get_text("lang_changed", new_lang))
