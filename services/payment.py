import asyncio
import json
import urllib.request
import urllib.parse
from config import TRIBUTE_LINK, TRIBUTE_API_KEY
from services.logger import log_info, log_error


def get_tribute_pay_url(user_id: int) -> str:
    """Возвращает прямую ссылку на оплату через Tribute."""
    if not TRIBUTE_LINK:
        return ""

    # Если в ссылке уже есть параметры, добавляем user_id
    separator = "&" if "?" in TRIBUTE_LINK else "?"
    return f"{TRIBUTE_LINK}{separator}startapp_param={user_id}"


def check_tribute_payment(user_id: int) -> bool:
    """Проверяет статус оплаты подписки пользователя в Tribute API."""
    if not TRIBUTE_API_KEY:
        # Если API-ключ не задан, возвращаем False
        return False

    query = urllib.parse.urlencode({"user_id": user_id})
    url = f"https://api.tribute.tg/v1/subscriptions?{query}"
    headers = {
        "Authorization": f"Bearer {TRIBUTE_API_KEY}",
        "User-Agent": "SC-Music-Bot/1.0",
        "Accept": "application/json",
    }

    try:
        from services.db import hash_user_id
        u_hash = hash_user_id(user_id)[:8]
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok") and data.get("result"):
                for sub in data["result"]:
                    if sub.get("status") in ("active", "paid"):
                        log_info(f"💳 Подписка Tribute подтверждена для [user:{u_hash}]", user_id=user_id)
                        return True
    except Exception as e:
        from services.db import hash_user_id
        u_hash = hash_user_id(user_id)[:8]
        log_error(f"⚠️ Ошибка проверки подписки Tribute для [user:{u_hash}]: {e}", user_id=user_id)

    return False


async def async_get_tribute_pay_url(user_id: int) -> str:
    return await asyncio.to_thread(get_tribute_pay_url, user_id)


async def async_check_tribute_payment(user_id: int) -> bool:
    return await asyncio.to_thread(check_tribute_payment, user_id)
