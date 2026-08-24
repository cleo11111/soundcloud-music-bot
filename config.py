from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_SALT = os.getenv("SECRET_SALT", "")
TRIBUTE_LINK = os.getenv("TRIBUTE_LINK", "")
TRIBUTE_API_KEY = os.getenv("TRIBUTE_API_KEY", "")


def verify_config():
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not ADMIN_ID:
        missing.append("ADMIN_ID")
    if not SECRET_SALT:
        missing.append("SECRET_SALT")

    if missing:
        raise RuntimeError(
            f"🚨 Критическая ошибка запуска: в файле .env отсутствуют переменные: {', '.join(missing)}!"
        )


verify_config()
