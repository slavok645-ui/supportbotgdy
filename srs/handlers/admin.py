# srs/handlers/admin.py
from telegram import Update
from config import ADMIN_IDS


def is_admin(update: Update) -> bool:
    if not update.effective_user:
        return False

    if not ADMIN_IDS:
        return True

    return update.effective_user.id in ADMIN_IDS