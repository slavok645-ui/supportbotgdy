import threading
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import BOT_TOKEN, OPERATORS_CHAT_ID, str_to_int_safe, BOT_TOKENS
from srs.database import dictionaries as state
from srs.handlers.blacklist import is_blacklisted, admin_blacklist_add, admin_blacklist_remove, admin_blacklist_list
from srs.texts.quiq_replies import QUICK_REPLIES, TICKET_CLOSED, ADMIN_STATS

from srs.handlers.admin import is_admin

OPERATORS_CHAT_ID = str_to_int_safe(OPERATORS_CHAT_ID)


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return

    await update.effective_chat.send_message(QUICK_REPLIES["greeting"])


async def create_ticket(chat_id: int, update: Update) -> int:
    # создаём новый тикет
    ticket_id = next(state.ticket_counter)
    state.tickets[ticket_id] = {
        "client_chat_id": chat_id,
        "status": "open",
        "created_at": datetime.now(timezone.utc),
        "first_response_at": None,
    }
    state.client_to_ticket[chat_id] = ticket_id

    # Дебаг
    print(f"[DEBUG] Создан тикет #{ticket_id} для чата {chat_id}")
    print(f"[DEBUG] Всего тикетов: {len(state.tickets)}")

    # уведомляем клиента
    await update.effective_chat.send_message(
        f"Ваша заявка №{ticket_id} принята. Ожидайте ответа оператора."
    )

    return ticket_id


async def handle_client_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает сообщение от клиента:
    - проверяет открытый тикет,
    - если нет, создаёт новый тикет,
    - пересылает сообщение оператору.
    """
    if not update.effective_chat or not update.effective_user or not update.effective_message:
        return

    chat_id = update.effective_chat.id
    msg = update.effective_message
    username = update.effective_user.username or "без_username"
    full_name = update.effective_user.full_name

    # Проверка черного списка
    if is_blacklisted(chat_id):
        # Можно отправить предупреждение или просто игнорировать
        await update.effective_chat.send_message("К сожалению, на данный момент нет свободных операторов.")
        return

    # Проверяем существующий тикет
    ticket_id = state.client_to_ticket.get(chat_id)
    if ticket_id and state.tickets.get(ticket_id, {}).get("status") == "closed":
        state.client_to_ticket.pop(chat_id, None)
        ticket_id = None

    if not ticket_id:
        ticket_id = await create_ticket(chat_id, update)

    await forward_to_operator(context, chat_id, ticket_id, msg, full_name, username)


def make_ticket_header(ticket_id: int, full_name: str, username: str) -> str:
    return f"Тикет #{ticket_id}\nКлиент {full_name} (@{username})"


def make_operator_take_button(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🟢 Взял", callback_data=f"take_ticket:{ticket_id}")]])


def make_close_ticket_buttons(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Закрыть тикет", callback_data=f"close_ticket:{ticket_id}")]])


async def admin_autoreplies(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.effective_user:
        return

    if not is_admin(update):
        return

    if not QUICK_REPLIES:
        await update.effective_chat.send_message("Список автоответов пуст.")
        return

    lines: list[str] = []
    for key, value in QUICK_REPLIES.items():
        lines.append(f"{key}: {value}")

    await update.effective_chat.send_message("Текущие автоответы:\n" + "\n".join(lines))


async def admin_setreply(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.effective_user or not update.effective_message:
        return

    if not is_admin(update):
        return

    text = update.effective_message.text or ""
    parts = text.split(maxsplit=2)

    if len(parts) < 3:
        await update.effective_chat.send_message(
            "Использование: /admin_setreply <ключ> <новый текст>"
        )
        return

    _, key, new_text = parts

    QUICK_REPLIES[key] = new_text
    await update.effective_chat.send_message(
        f"Автоответ для ключа '{key}' обновлён. Текущее значение: {new_text}"
    )


async def admin_chatid(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.effective_user:
        return

    if not is_admin(update):
        return

    msg = update.effective_message

    #  Если команда ответом на сообщение
    if msg and msg.reply_to_message:
        reply_msg_id = msg.reply_to_message.message_id

        client_chat_id = state.operator_message_to_client.get(reply_msg_id)
        if client_chat_id:
            await update.effective_chat.send_message(
                f"chat_id клиента: {client_chat_id}"
            )
            return

        await update.effective_chat.send_message(
            "Не удалось определить клиента по этому сообщению."
        )
        return

    # без reply
    chat_id = update.effective_chat.id
    await update.effective_chat.send_message(f"chat_id этого чата: {chat_id}")


async def forward_to_operator(context: ContextTypes.DEFAULT_TYPE, client_chat_id: int, ticket_id: int, msg,
                              full_name: str, username: str):
    if OPERATORS_CHAT_ID is None:
        return

    header = make_ticket_header(ticket_id, full_name, username)
    if ticket_id not in state.ticket_has_buttons:
        buttons = make_operator_take_button(ticket_id)
        state.ticket_has_buttons.add(ticket_id)
    else:
        buttons = None

    text_or_caption = msg.text or msg.caption or ""

    operator_msg = await context.bot.copy_message(
        chat_id=OPERATORS_CHAT_ID,
        from_chat_id=client_chat_id,
        message_id=msg.message_id,
        caption=f"{header}\n{text_or_caption}".strip(),
        reply_markup=buttons
    )

    state.client_to_operator_message[client_chat_id] = operator_msg.message_id
    state.operator_message_to_client[operator_msg.message_id] = client_chat_id


async def handle_take_ticket_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data.startswith("take_ticket:"):
        return

    try:
        ticket_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("Ошибка тикета")
        return

    # Меняем кнопку на "Закрыть тикет"
    new_markup = make_close_ticket_buttons(ticket_id)
    await query.edit_message_reply_markup(reply_markup=new_markup)

    await query.answer("Вы взяли тикет. Теперь можете его закрыть.")


async def close_ticket(
        ticket_id: int,
        context: ContextTypes.DEFAULT_TYPE
) -> bool:
    ticket = state.tickets.get(ticket_id)
    if not ticket or ticket.get("status") != "open":
        return False

    ticket["status"] = "closed"
    client_chat_id: int | None = ticket.get("client_chat_id")

    if client_chat_id:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "Начать новый тикет",
                callback_data="start_new_ticket"
            )]
        ])

        await context.bot.send_message(
            chat_id=client_chat_id,
            text=TICKET_CLOSED.format(ticket_id=ticket_id),
            reply_markup=keyboard
        )

        # очистка состояния
        operator_msg_id = state.client_to_operator_message.pop(client_chat_id, None)
        if operator_msg_id:
            state.operator_message_to_client.pop(operator_msg_id, None)

        state.client_to_ticket.pop(client_chat_id, None)
        state.ticket_has_buttons.discard(ticket_id)

    return True


async def handle_start_new_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or query.data != "start_new_ticket":
        return

    # Имитация команды /start
    await start(update, context)
    await query.answer("Новый тикет можно создать")


async def handle_close_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data.startswith("close_ticket:"):
        return

    try:
        ticket_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("Ошибка тикета")
        return

    success = await close_ticket(ticket_id, context)
    if success:
        await query.edit_message_reply_markup(None)
        await query.answer("Тикет закрыт")
    else:
        await query.answer("Тикет уже закрыт")


async def admin_stats(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return

    total = len(state.tickets)
    open_tickets = sum(1 for t in state.tickets.values() if t["status"] == "open")
    closed_tickets = sum(1 for t in state.tickets.values() if t["status"] == "closed")

    # Среднее время ответа
    response_times = []
    for t in state.tickets.values():
        created = t.get("created_at")
        first_resp = t.get("first_response_at")
        if created and first_resp:
            delta = (first_resp - created).total_seconds()
            response_times.append(delta)

    if response_times:
        avg_response = sum(response_times) / len(response_times)
        avg_response_str = str(timedelta(seconds=int(avg_response)))
    else:
        avg_response_str = "Нет ответов"

    text = ADMIN_STATS.format(
        total=total,
        open=open_tickets,
        closed=closed_tickets,
        avg_response=avg_response_str
    )

    await update.effective_chat.send_message(text)


async def handle_operator_reply(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
) -> None:
    msg = update.effective_message
    chat = update.effective_chat

    if not msg or not chat or chat.id != OPERATORS_CHAT_ID:
        return

    # Ответ должен быть именно reply
    reply_to = msg.reply_to_message
    if not reply_to:
        return

    client_chat_id = state.operator_message_to_client.get(reply_to.message_id)
    if not client_chat_id:
        return

    # Отправка клиенту
    if msg.text:
        sent_msg = await context.bot.send_message(
            chat_id=client_chat_id,
            text=msg.text
        )
    else:
        sent_msg = await context.bot.copy_message(
            chat_id=client_chat_id,
            from_chat_id=chat.id,
            message_id=msg.message_id
        )

    # Устанавливаем время первого ответа
    client_ticket_id = state.client_to_ticket.get(client_chat_id)
    if client_ticket_id and state.tickets[client_ticket_id].get("first_response_at") is None:
        state.tickets[client_ticket_id]["first_response_at"] = datetime.now(timezone.utc)

    # Обновляем сопоставление сообщений
    state.client_to_operator_message[client_chat_id] = sent_msg.message_id
    state.operator_message_to_client[sent_msg.message_id] = client_chat_id


def register_handlers(app: Application) -> None:
    # Команды
    for cmd, func in [
        ("start", start),
        ("admin_autoreplies", admin_autoreplies),
        ("admin_setreply", admin_setreply),
        ("admin_chatid", admin_chatid),
        ("admin_stats", admin_stats)
    ]:
        app.add_handler(CommandHandler(cmd, func))

    # Сообщения от клиентов
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_client_message))

    # Сообщения от операторов
    if OPERATORS_CHAT_ID:
        app.add_handler(MessageHandler(filters.Chat(OPERATORS_CHAT_ID) & ~filters.COMMAND, handle_operator_reply))

    # Закрытие тикета
    app.add_handler(CallbackQueryHandler(handle_close_ticket_callback, pattern="^close_ticket:"))
    # Начать новый тикет
    app.add_handler(CallbackQueryHandler(handle_start_new_ticket_callback, pattern="^start_new_ticket$"))
    # Взял в работу
    app.add_handler(CallbackQueryHandler(handle_take_ticket_callback, pattern="^take_ticket:"))

    # Чс
    app.add_handler(CommandHandler("blacklist_add", admin_blacklist_add))
    app.add_handler(CommandHandler("blacklist_remove", admin_blacklist_remove))
    app.add_handler(CommandHandler("blacklist_list", admin_blacklist_list))


# --- Функция для создания Application для одного токена ---
def create_application(bot_token: str) -> Application:
    app = (
        Application.builder()
        .token(bot_token)
        .concurrent_updates(True)
        .build()
    )

    register_handlers(app)
    return app


def main() -> None:
    tokens = BOT_TOKENS or [BOT_TOKEN]  # если BOT_TOKENS пуст, берём BOT_TOKEN

    if not tokens or not any(tokens):
        raise RuntimeError("Не заданы токены ботов.")

    # Если один токен — запускаем обычный режим
    if len(tokens) == 1:
        create_application(tokens[0]).run_polling()
        return

    # Если несколько токенов — многопоточность
    threads = []
    for token in tokens:
        t = threading.Thread(
            target=lambda tok=token: create_application(tok).run_polling(),
            daemon=False
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
