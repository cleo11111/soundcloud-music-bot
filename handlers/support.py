import html
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID
from services.db import async_get_user_language, hash_user_id
from services.locales import get_text
from services.logger import log_info, log_error

router = Router()


class SupportStates(StatesGroup):
    waiting_for_user_message = State()
    waiting_for_admin_reply = State()


@router.message(Command("cancel"))
async def cancel_fsm(message: Message, state: FSMContext):
    """Отменяет текущий шаг ввода сообщений."""
    current_state = await state.get_state()
    if current_state is None:
        return

    user_id = message.from_user.id
    lang = await async_get_user_language(user_id)
    await state.clear()
    await message.answer(get_text("support_cancel", lang))


@router.message(Command("support"))
@router.message(Command("report"))
async def process_support_command(message: Message, state: FSMContext):
    """Обработчик команды /support или /report."""
    user_id = message.from_user.id
    lang = await async_get_user_language(user_id)
    await state.set_state(SupportStates.waiting_for_user_message)
    await message.answer(get_text("support_prompt", lang), parse_mode="HTML")


@router.callback_query(F.data == "cmd_support")
async def process_support_callback(call: CallbackQuery, state: FSMContext):
    """Нажатие на кнопку '💬 Поддержка / Отзыв'."""
    user_id = call.from_user.id
    lang = await async_get_user_language(user_id)
    await state.set_state(SupportStates.waiting_for_user_message)
    await call.message.answer(get_text("support_prompt", lang), parse_mode="HTML")
    await call.answer()


import time

SUPPORT_COOLDOWN = {}
SUPPORT_COOLDOWN_SEC = 60  # Лимит: 1 обращение в 60 секунд (для предотвращения спама)


@router.message(SupportStates.waiting_for_user_message)
async def process_user_support_message(message: Message, state: FSMContext):
    """Принимает сообщение от пользователя и отправляет администратору."""
    user_id = message.from_user.id
    lang = await async_get_user_language(user_id)
    u_hash = hash_user_id(user_id)[:8]
    text = message.text or message.caption or "(Вложение/Медиа)"

    await state.clear()

    # Защита от спама обращениями к администратору (Rate Limiting)
    now = time.time()
    last_sent = SUPPORT_COOLDOWN.get(user_id, 0)
    if user_id != ADMIN_ID and (now - last_sent < SUPPORT_COOLDOWN_SEC):
        wait_sec = int(SUPPORT_COOLDOWN_SEC - (now - last_sent))
        await message.answer(get_text("support_cooldown", lang, sec=wait_sec), parse_mode="HTML")
        return

    SUPPORT_COOLDOWN[user_id] = now

    if not ADMIN_ID:
        log_error("⚠️ ADMIN_ID не настроен в .env!")
        await message.answer(get_text("support_sent", lang), parse_mode="HTML")
        return

    import html
    safe_text = html.escape(text)

    # Клавиатура для администратора для ответа в 1 клик
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Ответить пользователю", callback_data=f"reply_to_{user_id}")]
        ]
    )

    ticket_text = (
        f"📬 <b>Новое обращение от пользователя <code>[user:{u_hash}]</code></b>:\n\n"
        f"{safe_text}"
    )

    try:
        await message.bot.send_message(
            chat_id=ADMIN_ID,
            text=ticket_text,
            reply_markup=kb,
            parse_mode="HTML",
        )
        log_info(f"📩 Обращение от [user:{u_hash}] доставлено админу", user_id=user_id)
    except Exception as e:
        log_error(f"⚠️ Ошибка отправки обращения админу: {e}", user_id=user_id)

    await message.answer(get_text("support_sent", lang), parse_mode="HTML")


@router.callback_query(F.data.startswith("reply_to_"))
async def process_admin_reply_callback(call: CallbackQuery, state: FSMContext):
    """Администратор нажимает '✉️ Ответить пользователю'."""
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Доступ запрещен.", show_alert=True)
        return

    try:
        target_user_id = int(call.data.split("reply_to_")[-1])
    except ValueError:
        await call.answer("❌ Ошибка: неверный ID пользователя.", show_alert=True)
        return

    u_hash = hash_user_id(target_user_id)[:8]

    await state.set_state(SupportStates.waiting_for_admin_reply)
    await state.update_data(target_user_id=target_user_id, u_hash=u_hash)

    await call.message.answer(
        f"✍️ <b>Напишите ответ для пользователя <code>[user:{u_hash}]</code></b>:\n<i>(Для отмены отправьте /cancel)</i>",
        parse_mode="HTML",
    )
    await call.answer()


@router.message(SupportStates.waiting_for_admin_reply)
async def process_admin_send_reply(message: Message, state: FSMContext):
    """Администратор отправляет текст ответа."""
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    u_hash = data.get("u_hash", "пользователь")

    if not target_user_id:
        await state.clear()
        return

    reply_text = message.text or message.caption or ""
    safe_reply_text = html.escape(reply_text)
    await state.clear()

    # Отправляем ответ пользователю АНОНИМНО от имени бота
    user_lang = await async_get_user_language(target_user_id)
    user_msg_text = get_text("user_received_reply", user_lang, text=safe_reply_text)

    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=user_msg_text,
            parse_mode="HTML",
        )
        await message.answer(f"✅ Ответ успешно отправлен пользователю <code>[user:{u_hash}]</code>!", parse_mode="HTML")
        log_info(f"✉️ Админ ответил пользователю [user:{u_hash}]")
    except Exception as e:
        await message.answer(f"❌ Не удалось доставить ответ пользователю: {e}")
        log_error(f"⚠️ Ошибка отправки ответа пользователю: {e}")


from services.db import async_set_user_premium


@router.message(F.chat.type == "private", Command("grant_premium"))
async def process_grant_premium_command(message: Message):
    """Админ-команда для ручной выдачи премиум подписки: /grant_premium USER_ID [дней]"""
    if message.from_user.id != ADMIN_ID or message.chat.type != "private":
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: <code>/grant_premium USER_ID [дней]</code>\nПример: <code>/grant_premium 123456789 30</code>", parse_mode="HTML")
        return

    try:
        target_uid = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else 30
        await async_set_user_premium(target_uid, days=days)
        await message.answer(f"✅ 💎 Премиум подписка на {days} дней успешно выдана пользователю <code>{target_uid}</code>!", parse_mode="HTML")

        # Уведомляем пользователя
        try:
            u_lang = await async_get_user_language(target_uid)
            msg_text = get_text("premium_activated", u_lang, days=days)
            await message.bot.send_message(target_uid, msg_text, parse_mode="HTML")
        except Exception:
            pass
    except ValueError:
        await message.answer("❌ Ошибка: USER_ID и количество дней должны быть числами.")


@router.message(F.chat.type == "private", Command("revoke_premium"))
async def process_revoke_premium_command(message: Message):
    """Админ-команда для снятия премиума и переключения на Бесплатный тариф: /revoke_premium [USER_ID]"""
    if message.from_user.id != ADMIN_ID or message.chat.type != "private":
        return

    parts = message.text.strip().split()
    target_uid = int(parts[1]) if len(parts) > 1 else message.from_user.id

    await async_set_user_premium(target_uid, days=0)
    await message.answer(f"✅ Для пользователя <code>{target_uid}</code> активирован <b>🆓 Бесплатный тариф</b>!", parse_mode="HTML")


@router.message(F.chat.type == "private", Command("add_whitelist"))
@router.message(F.chat.type == "private", Command("whitelist_add"))
async def process_add_whitelist_command(message: Message):
    """Админ-команда для добавления пользователя в вечный WhiteList: /add_whitelist USER_ID"""
    if message.from_user.id != ADMIN_ID or message.chat.type != "private":
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: <code>/add_whitelist USER_ID</code>\nПример: <code>/add_whitelist 123456789</code>", parse_mode="HTML")
        return

    try:
        target_uid = int(parts[1])
        from services.db import async_set_user_whitelist
        await async_set_user_whitelist(target_uid, is_whitelisted=True)
        await message.answer(f"⭐ Пользователь <code>{target_uid}</code> успешно добавлен в <b>WhiteList</b>!", parse_mode="HTML")

        # Уведомляем пользователя
        try:
            u_lang = await async_get_user_language(target_uid)
            await message.bot.send_message(
                target_uid,
                get_text("whitelist_activated", u_lang),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except ValueError:
        await message.answer("❌ Ошибка: USER_ID должен быть числом.")


@router.message(F.chat.type == "private", Command("remove_whitelist"))
@router.message(F.chat.type == "private", Command("whitelist_remove"))
async def process_remove_whitelist_command(message: Message):
    """Админ-команда для удаления пользователя из WhiteList: /remove_whitelist USER_ID"""
    if message.from_user.id != ADMIN_ID or message.chat.type != "private":
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: <code>/remove_whitelist USER_ID</code>", parse_mode="HTML")
        return

    try:
        target_uid = int(parts[1])
        from services.db import async_set_user_whitelist
        await async_set_user_whitelist(target_uid, is_whitelisted=False)
        await message.answer(f"❌ Пользователь <code>{target_uid}</code> удален из <b>WhiteList</b>!", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Ошибка: USER_ID должен быть числом.")


from services.downloader import finish_user_download


@router.message(F.chat.type == "private", Command("reset_lock"))
async def process_reset_lock_command(message: Message):
    """Админ-команда для сброса зависшей блокировки скачивания: /reset_lock [USER_ID]"""
    if message.from_user.id != ADMIN_ID or message.chat.type != "private":
        return

    parts = message.text.strip().split()
    target_uid = int(parts[1]) if len(parts) > 1 else message.from_user.id

    finish_user_download(target_uid)
    await message.answer(f"🔓 Блокировка скачивания для пользователя <code>{target_uid}</code> успешно сброшена!", parse_mode="HTML")


from services.db import async_get_bot_stats


@router.message(F.chat.type == "private", Command("stats"))
async def process_stats_command(message: Message):
    """Админ-команда для отображения статистики бота: /stats"""
    if message.from_user.id != ADMIN_ID or message.chat.type != "private":
        return

    stats = await async_get_bot_stats()
    stats_text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Всего пользователей:</b> {stats['total_users']}\n"
        f"💎 <b>Премиум:</b> {stats['premium_users']}\n"
        f"⭐ <b>WhiteList:</b> {stats['whitelisted_users']}\n"
        f"🎵 <b>Всего скачиваний:</b> {stats['total_downloads']}"
    )
    await message.answer(stats_text, parse_mode="HTML")

