"""
Локализация текстовых сообщений и кнопок (Русский / Английский).
"""

MESSAGES = {
    "ru": {
        "welcome": (
            "Добро пожаловать в @{bot_username}!\n\n"
            "Скиньте боту ссылку на плейлист или песню в SoundCloud или воспользуйтесь поиском в боте.\n\n"
            "Нажмите /help для получения справки."
        ),
        "btn_search_track": "🎧 Искать трек",
        "btn_search_playlist": "📂 Искать плейлист",
        "btn_history": "📄 История скачиваний",
        "btn_support": "💬 Поддержка / Отзыв",
        "btn_premium": "💎 Премиум подписка",
        "btn_language": "🌐 Язык / Language",
        "btn_buy_tribute": "💳 Оплатить $1 (Tribute)",
        "btn_check_pay": "🔄 Проверить оплату",
        "playlist_prefix": "Плейлист: ",
        "invoice_created": "💎 <b>Ссылка на оплату подписки через Tribute!</b>\n\n1. Нажмите кнопку <b>«Оплатить $1 (Tribute)»</b> ниже.\n2. Завершите оплату банковской картой или Apple Pay.\n3. После оплаты нажмите <b>«🔄 Проверить оплату»</b> ниже.",
        "pay_not_found": "⏳ Платёж ещё не поступил. Пожалуйста, завершите оплату в Tribute и нажмите кнопку ещё раз.",
        "pay_checking_notice": "⏳ Запрос отправлен! Подписка автоматически активируется в ближайшие минуты.",
        "pay_success_alert": "🎉 Поздравляем! Ваша 💎 премиум подписка на 30 дней успешно активирована!",
        "err_token_missing": "⚠️ Ссылка на оплату настраивается администратором. Напишите в техподдержку.",
        "premium_info": (
            "💎 <b>Премиум подписка ($1 / месяц)</b>\n\n"
            "<b>🆓 Бесплатный план:</b>\n"
            "• До 40 треков в день\n"
            "• 3 плейлиста в день (до 50 треков)\n"
            "• История последних 20 скачиваний\n"
            "• Стандартная живая очередь\n\n"
            "<b>💎 Премиум план ($1 / месяц):</b>\n"
            "• ♾️ Безлимитное скачивание треков\n"
            "• ♾️ Безлимитные плейлисты любого размера\n"
            "• ♾️ Неограниченная история скачиваний\n"
            "• 🕒 Без ожидания в очереди"
        ),
        "premium_active_status": "💎 <b>У вас активна премиум подписка!</b>\nДействует до: <code>{expires_at}</code>",
        "premium_active_whitelisted": "💎 <b>У вас активен бессрочный премиум доступ!</b>",
        "whitelist_activated": "🎉 Поздравляем! Вам предоставлен 💎 <b>бессрочный премиум доступ</b>!",
        "err_daily_tracks_limit": "⚠️ <b>Достигнут дневной лимит скачивания треков!</b>\nВы исчерпали лимит в 40 треков на сегодня.\n\nПерейдите на <b>💎 премиум подписку ($1/мес)</b> для снятия ограничений!",
        "err_daily_playlists_limit": "⚠️ Достигнут дневной лимит скачивания плейлистов!\nВ бесплатной версии доступно скачивание лишь 3 плейлистов в день.\n\nПерейдите на 💎 премиум подписку ($1/мес) для снятия ограничений!",
        "err_playlist_tracks_over_limit": "⚠️ Лимит треков в плейлисте!\nБесплатная версия поддерживает до 50 треков в плейлисте (у вас — {count}).\n\nПерейдите на 💎 премиум подписку ($1/мес) для снятия ограничений!",
        "support_prompt": "✍️ <b>Напишите ваше сообщение или жалобу администратору:</b>\n\n<i>(Опишите проблему или вставьте ссылку, вызвавшую ошибку. Для отмены отправьте /cancel)</i>",
        "support_sent": "✅ <b>Ваше сообщение успешно отправлено администратору!</b>\nСпасибо за обратную связь.",
        "support_cooldown": "⚠️ <b>Слишком частые обращения!</b>\nВы сможете отправить следующее сообщение через {sec} сек.",
        "support_cancel": "❌ Отправка обращения отменена.",
        "btn_reply_user": "✉️ Ответить",
        "reply_prompt": "✍️ <b>Напишите ответ для пользователя {user_hash}:</b>\n<i>(Для отмены отправьте /cancel)</i>",
        "reply_sent": "✅ Ответ успешно доставлен пользователю!",
        "user_received_reply": "📩 <b>Ответ от администратора:</b>\n\n{text}",
        "select_language": "🌐 Выберите язык / Select language:",
        "lang_changed": "✅ Язык изменён на Русский!",
        "history_empty": "📄 Ваша история скачиваний пуста.",
        "history_title": "📄 <b>Последние скачивания</b>\n",
        "today": "Сегодня {time}",
        "yesterday": "Вчера {time}",
        "cover_track": "🎧 Трек: {title}",
        "cover_artist": "👤 Исполнитель: {artist}",
        "cover_date": "📅 Дата: {date}",
        "btn_clear_history": "🗑 Очистить историю",
        "confirm_clear_history": "🗑 <b>Выберите период для очистки истории скачиваний:</b>",
        "btn_clear_7days": "🗓 За последние 7 дней",
        "btn_clear_all": "🔥 Удалить всё",
        "btn_confirm_clear": "✅ Да, очистить",
        "btn_cancel_clear": "❌ Отмена",
        "history_cleared_7days": "🗓 История скачиваний за последние 7 дней успешно очищена!",
        "history_cleared_all": "🔥 Вся ваша история скачиваний успешно очищена!",
        "history_cleared": "🗑 Ваша история скачиваний успешно очищена!",
        "action_cancelled": "Действие отменено.",
        "help_text": (
            "📖 <b>Справка и команды бота @{bot_username}</b>\n\n"
            "<b>Поиск через инлайн-режим (в любом чате):</b>\n"
            "• <code>@{bot_username} название_трека</code> — искать трек на SoundCloud\n"
            "• <code>@{bot_username} /playlist название_плейлиста</code> — искать плейлист на SoundCloud\n"
            "• <code>@{bot_username} ссылка_на_трек</code> — скачать трек по ссылке в чате (нажав плашку в меню)\n\n"
            "<b>Скачивание по ссылке (в личных сообщениях):</b>\n"
            "Отправьте боту прямую ссылку на трек или плейлист SoundCloud.\n\n"
            "<b>Основные команды:</b>\n"
            "• /start — Показать главное меню\n"
            "• /history — Посмотреть историю скачиваний\n"
            "• /clear_history — Очистить историю скачиваний\n"
            "• /support — Написать разработчику (отзыв / жалоба)\n"
            "• /help — Показать эту справку"
        ),
        "text_prompt": "Скиньте ссылку на трек или плейлист SoundCloud, либо воспользуйтесь поиском через кнопки ниже.",
        "playlist_choice": "Как отправить треки?",
        "playlist_over_limit": "⚠️ <i>В плейлисте более 50 треков ({count}). Скачивание по отдельности недоступно — доступно только скачивание архивом (ZIP).</i>",
        "playlist_over_limit_alert": "⚠️ В плейлисте более 50 треков. Скачивание по отдельности недоступно — используйте скачивание архивом.",
        "btn_pl_zip": "📁 Архивом (ZIP)",
        "btn_pl_sep": "🎵 По отдельности",
        "err_already_downloading": "⚠️ У вас уже идет скачивание! Пожалуйста, дождитесь завершения текущей загрузки.",
        "err_disk_full": "⚠️ На сервере временно недостаточно свободного места. Попробуйте позже.",
        "only_soundcloud": "❌ Поддерживаются только ссылки на SoundCloud.",
        "downloading_track": "⏳ Скачиваю: {title}...",
        "downloading_song": "⏳ Скачиваю трек...",
        "file_too_large": "⚠️ Файл «{title}» слишком большой ({size:.1f} МБ).\nTelegram Bot API не позволяет отправлять файлы крупнее 50 МБ.",
        "err_drm": "🔒 Этот трек защищён DRM и недоступен для скачивания.",
        "err_404": "❌ Трек не найден. Возможно, он был удалён.",
        "err_403": "🚫 Доступ к треку заблокирован.",
        "err_429": "⏳ Слишком много запросов. Подождите немного и попробуйте снова.",
        "err_generic": "❌ Не удалось скачать трек. Попробуйте другой.",
        "data_expired": "Данные устарели. Повторите поиск.",
        "starting_download": "⏳ Начинаю скачивание…",
        "loading_playlist_info": "🔄 Загружаю информацию о плейлисте…",
        "err_playlist_empty": "❌ Не удалось загрузить плейлист или он пуст.",
        "downloading_playlist_zip": "⏳ Скачиваю {count} из «{title}»…\nЭто может занять некоторое время.",
        "downloading_playlist_sep": "⏳ Скачиваю треки из «{title}»… ({current}/{total})",
        "err_playlist_sep_failed": "❌ Не удалось скачать трек из «{title}».",
        "playlist_sep_done": "✅ Готово! Отправлено {sent} из {total} из «{title}».",
        "err_track_not_found": "Ошибка: трек не найден.",
        "searching_tracks": "🔎 Ищу треки на SoundCloud...",
        "nothing_found": "❌ Ничего не найдено. Попробуйте другой запрос.",
        "ban_title": "⚠️ SoundCloud временно ограничил доступ",
        "ban_desc": "Подождите {sec} сек. и повторите попытку.",
        "ban_message": "Сервис перегружен, попробуйте чуть позже.",
    },
    "en": {
        "welcome": (
            "Welcome to @{bot_username}!\n\n"
            "Send a link to a playlist or song on SoundCloud or use the search in the bot.\n\n"
            "Click /help for more information."
        ),
        "btn_search_track": "🎧 Search track",
        "btn_search_playlist": "📂 Search playlist",
        "btn_history": "📄 Download history",
        "btn_support": "💬 Support / Feedback",
        "btn_premium": "💎 Premium Subscription",
        "btn_language": "🌐 Language / Язык",
        "btn_buy_tribute": "💳 Pay $1 (Tribute)",
        "btn_check_pay": "🔄 Check Payment",
        "playlist_prefix": "Playlist: ",
        "invoice_created": "💎 <b>Tribute Payment Link Ready!</b>\n\n1. Click <b>«Pay $1 (Tribute)»</b> below.\n2. Complete payment via bank card or Apple Pay.\n3. Once done, click <b>«🔄 Check Payment»</b> below.",
        "pay_not_found": "⏳ Payment has not been received yet. Please complete payment in Tribute and try again.",
        "pay_checking_notice": "⏳ Request sent! Your Premium subscription will activate in a few moments.",
        "pay_success_alert": "🎉 Congratulations! Your 💎 30-day Premium Subscription has been activated!",
        "err_token_missing": "⚠️ Payment link is being configured by administrator. Please contact support.",
        "premium_info": (
            "💎 <b>Premium Subscription ($1 / month)</b>\n\n"
            "<b>🆓 Free Plan:</b>\n"
            "• Up to 40 tracks per day\n"
            "• 3 playlists per day (up to 50 tracks)\n"
            "• History of last 20 downloads\n"
            "• Standard queue\n\n"
            "<b>💎 Premium Plan ($1 / month):</b>\n"
            "• ♾️ Unlimited track downloads\n"
            "• ♾️ Unlimited playlists of any size\n"
            "• ♾️ Unlimited download history\n"
            "• 🕒 Zero wait time in queue"
        ),
        "premium_active_status": "💎 <b>Your Premium Subscription is active!</b>\nExpires on: <code>{expires_at}</code>",
        "premium_active_whitelisted": "💎 <b>You have active Permanent Premium access!</b>",
        "whitelist_activated": "🎉 Congratulations! You have been granted 💎 <b>Permanent Premium access</b>!",
        "err_daily_tracks_limit": "⚠️ <b>Daily track download limit reached!</b>\nYou have used your 40 downloads for today.\n\nUpgrade to <b>💎 Premium ($1/mo)</b> to remove limits!",
        "err_daily_playlists_limit": "⚠️ Daily playlist download limit reached!\nFree version supports downloading only 3 playlists per day.\n\nUpgrade to 💎 Premium ($1/mo) to remove limits!",
        "err_playlist_tracks_over_limit": "⚠️ Playlist track limit!\nFree version supports up to 50 tracks per playlist (yours has {count}).\n\nUpgrade to 💎 Premium ($1/mo) to remove limits!",
        "support_prompt": "✍️ <b>Write your message or report to the administrator:</b>\n\n<i>(Describe the issue or paste the broken link. Send /cancel to abort)</i>",
        "support_sent": "✅ <b>Your message has been sent to the administrator!</b>\nThank you for your feedback.",
        "support_cooldown": "⚠️ <b>Too many requests!</b>\nYou can send the next message in {sec} sec.",
        "support_cancel": "❌ Support message submission cancelled.",
        "btn_reply_user": "✉️ Reply",
        "reply_prompt": "✍️ <b>Write a reply to user {user_hash}:</b>\n<i>(Send /cancel to abort)</i>",
        "reply_sent": "✅ Reply delivered to user successfully!",
        "user_received_reply": "📩 <b>Reply from administrator:</b>\n\n{text}",
        "select_language": "🌐 Select language / Выберите язык:",
        "lang_changed": "✅ Language changed to English!",
        "history_empty": "📄 Your download history is empty.",
        "history_title": "📄 <b>Recent downloads</b>\n",
        "today": "Today {time}",
        "yesterday": "Yesterday {time}",
        "cover_track": "🎧 Track: {title}",
        "cover_artist": "👤 Artist: {artist}",
        "cover_date": "📅 Date: {date}",
        "btn_clear_history": "🗑 Clear history",
        "confirm_clear_history": "🗑 <b>Select time period to clear download history:</b>",
        "btn_clear_7days": "🗓 Last 7 days",
        "btn_clear_all": "🔥 Clear all",
        "btn_confirm_clear": "✅ Yes, clear",
        "btn_cancel_clear": "❌ Cancel",
        "history_cleared_7days": "🗓 Download history for the last 7 days cleared!",
        "history_cleared_all": "🔥 Your entire download history has been cleared!",
        "history_cleared": "🗑 Your download history has been successfully cleared!",
        "action_cancelled": "Action cancelled.",
        "help_text": (
            "📖 <b>Help & Commands for @{bot_username}</b>\n\n"
            "<b>Inline search (in any chat):</b>\n"
            "• <code>@{bot_username} track_name</code> — search for a track on SoundCloud\n"
            "• <code>@{bot_username} /playlist playlist_name</code> — search for a playlist on SoundCloud\n"
            "• <code>@{bot_username} track_link</code> — download track by link in chat (via pop-up card)\n\n"
            "<b>Direct link download (in private chat):</b>\n"
            "Send the bot a direct link to a track or playlist on SoundCloud.\n\n"
            "<b>Main commands:</b>\n"
            "• /start — Open main menu\n"
            "• /history — View download history\n"
            "• /clear_history — Clear download history\n"
            "• /support — Send feedback or report an issue\n"
            "• /help — Show this help message"
        ),
        "text_prompt": "Send a link to a track or playlist on SoundCloud, or use the search buttons below.",
        "playlist_choice": "How would you like to send the tracks?",
        "playlist_over_limit": "⚠️ <i>This playlist has more than 50 tracks ({count}). Sending tracks separately is disabled — only ZIP archive download is available.</i>",
        "playlist_over_limit_alert": "⚠️ Playlist contains more than 50 tracks. Separate sending is disabled — use ZIP archive download.",
        "btn_pl_zip": "📁 Archive (ZIP)",
        "btn_pl_sep": "🎵 Separately",
        "err_already_downloading": "⚠️ You already have an active download in progress! Please wait for it to finish.",
        "err_disk_full": "⚠️ Server is temporarily low on disk space. Please try again later.",
        "only_soundcloud": "❌ Only SoundCloud links are supported.",
        "downloading_track": "⏳ Downloading: {title}...",
        "downloading_song": "⏳ Downloading track...",
        "file_too_large": "⚠️ File «{title}» is too large ({size:.1f} MB).\nTelegram Bot API does not allow sending files larger than 50 MB.",
        "err_drm": "🔒 This track is DRM protected and cannot be downloaded.",
        "err_404": "❌ Track not found. It might have been deleted.",
        "err_403": "🚫 Access to track is forbidden.",
        "err_429": "⏳ Too many requests. Please wait a bit and try again.",
        "err_generic": "❌ Failed to download track. Try another one.",
        "data_expired": "Data expired. Please search again.",
        "starting_download": "⏳ Starting download…",
        "loading_playlist_info": "🔄 Loading playlist information…",
        "err_playlist_empty": "❌ Failed to load playlist or it is empty.",
        "downloading_playlist_zip": "⏳ Downloading {count} from «{title}»…\nThis may take some time.",
        "downloading_playlist_sep": "⏳ Downloading tracks from «{title}»… ({current}/{total})",
        "err_playlist_sep_failed": "❌ Failed to download tracks from «{title}».",
        "playlist_sep_done": "✅ Done! Sent {sent} of {total} from «{title}».",
        "err_track_not_found": "Error: track not found.",
        "searching_tracks": "🔎 Searching tracks on SoundCloud...",
        "nothing_found": "❌ Nothing found. Try another query.",
        "ban_title": "⚠️ SoundCloud rate limit reached",
        "ban_desc": "Please wait {sec} sec and try again.",
        "ban_message": "Service is busy, please try again shortly.",
    },
}


def get_text(key: str, lang: str = "ru", **kwargs) -> str:
    """Возвращает локализованную строку с подстановкой параметров."""
    lang_dict = MESSAGES.get(lang, MESSAGES["ru"])
    text = lang_dict.get(key, MESSAGES["ru"].get(key, ""))
    if kwargs:
        return text.format(**kwargs)
    return text


def format_cover_caption(title: str, artist: str, date: str | None = None, lang: str = "ru") -> str:
    """Форматирует подпись под обложкой трека."""
    lines = [
        get_text("cover_track", lang, title=title),
        get_text("cover_artist", lang, artist=artist),
    ]
    if date:
        lines.append(get_text("cover_date", lang, date=date))
    return "\n".join(lines)
