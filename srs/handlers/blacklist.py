from telegram import Update

from telegram.ext import ContextTypes

from srs.database import dictionaries as state

from srs.handlers.admin import is_admin

def is_blacklisted(chat_id: int) -> bool:
    return chat_id in state.blacklist

async def admin_blacklist_add(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update) or not update.effective_message:
        return

    parts = update.effective_message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_chat.send_message("Использование: /blacklist_add <chat_id>")
        return

    try:
        chat_id = int(parts[1])
    except ValueError:
        await update.effective_chat.send_message("chat_id должен быть числом")
        return

    state.blacklist.add(chat_id)
    await update.effective_chat.send_message(f"Пользователь {chat_id} добавлен в черный список.")

# Команда чс
async def admin_blacklist_remove(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update) or not update.effective_message:
        return

    parts = update.effective_message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.effective_chat.send_message("Использование: /blacklist_remove <chat_id>")
        return

    try:
        chat_id = int(parts[1])
    except ValueError:
        await update.effective_chat.send_message("chat_id должен быть числом")
        return

    state.blacklist.discard(chat_id)
    await update.effective_chat.send_message(f"Пользователь {chat_id} удален из черного списка.")

# Проверка чс
async def admin_blacklist_list(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return

    if not state.blacklist:
        await update.effective_chat.send_message("Черный список пуст.")
        return

    await update.effective_chat.send_message(
        "Черный список:\n" + "\n".join(str(cid) for cid in state.blacklist)
    )



