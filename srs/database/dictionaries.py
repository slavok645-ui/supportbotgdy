# srs/database/dictionaries.py
from itertools import count

# --- Сообщения между клиентами и операторами ---
client_to_operator_message: dict[int, int] = {}  # client_chat_id -> operator_msg_id
operator_message_to_client: dict[int, int] = {}  # operator_msg_id -> client_chat_id

# --- Клиенты, которых уведомили "подождите" ---
clients_notified_wait: set[int] = set()

# --- Тикеты ---
ticket_counter = count(1)  # глобальный счётчик тикетов
tickets: dict[int, dict] = {}  # ticket_id -> информация о тикете
client_to_ticket: dict[int, int] = {}  # client_chat_id -> ticket_id

# Все переменные через state-переменная

# UI / состояние
ticket_has_buttons: set[int] = set()

# Кто ведёт тикет
ticket_operator: dict[int, int] = {}  # ticket_id -> operator_user_id



blacklist = set()  # chat_id пользователей, которых не обрабатывать


