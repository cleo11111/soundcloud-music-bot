import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEBUG_MODE = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True, mode=0o700)
LOG_FILE = LOG_DIR / "bot.log"

logger = logging.getLogger("music_bot")
logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)

# 1. Console output (stdout)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
console_handler.setFormatter(console_formatter)

# 2. Rotating log file (max 5 MB per file, keep 3 backups)
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,  
    backupCount=3,
    encoding="utf-8",
)
file_handler.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
file_handler.setFormatter(file_formatter)

if not logger.handlers:
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


def format_user_prefix(user_id: int | None = None) -> str:
    if not user_id:
        return ""
    try:
        from services.db import hash_user_id
        short_hash = hash_user_id(user_id)[:8]
        return f"[user:{short_hash}] "
    except Exception:
        return f"[user:{user_id}] "


def log_debug(msg: str, user_id: int | None = None):
    if DEBUG_MODE:
        prefix = format_user_prefix(user_id)
        logger.debug(f"{prefix}{msg}")


def log_info(msg: str, user_id: int | None = None):
    prefix = format_user_prefix(user_id)
    logger.info(f"{prefix}{msg}")


def log_error(msg: str, user_id: int | None = None):
    prefix = format_user_prefix(user_id)
    logger.error(f"{prefix}{msg}")
