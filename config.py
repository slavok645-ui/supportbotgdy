import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPERATORS_CHAT_ID = os.getenv("OPERATORS_CHAT_ID", "")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
BOT_TOKENS = [t.strip() for t in os.getenv("BOT_TOKENS", "").split(",") if t.strip()]


def str_to_int_safe(value: str, default=None):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# Получаем данные из окружения и сразу используем их
ADMIN_IDS: set[int] = set()
for part in os.getenv("ADMIN_IDS", "").split(","):
    part = part.strip()
    id_ = str_to_int_safe(part)
    if id_ is not None:
        ADMIN_IDS.add(id_)
