"""
Конфигурация и константы проекта.
Все параметры читаются из переменных окружения (.env файл).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── neonize / WhatsApp Web ───────────────────────────────────────────────────
# SQLite-файл для хранения сессии. Удали его, чтобы пройти QR-авторизацию заново.
SESSION_DB: str = os.getenv("SESSION_DB", "session.sqlite3")

# ─── Сообщение ────────────────────────────────────────────────────────────────
BASE_MESSAGE: str = os.getenv(
    "BASE_MESSAGE",
    "Привет! Приглашаем тебя на наше мероприятие. Будет интересно — не пропусти!",
)
EVENT_URL: str = os.getenv("EVENT_URL", "https://example.com/event")
# BUTTON_TEXT здесь не используется — в неофициальном API кнопки недоступны.
# Ссылка добавляется в конец текста и WhatsApp отображает её как превью-карточку.

# ─── Антиспам ────────────────────────────────────────────────────────────────
# Случайная задержка между отправками (секунды). Максимум — 5 минут (300 сек).
DELAY_MIN_SEC: float = 30.0
DELAY_MAX_SEC: float = 300.0

# ─── Файлы ────────────────────────────────────────────────────────────────────
CONTACTS_FILE: str = os.getenv("CONTACTS_FILE", "contacts.csv")
RESULTS_DIR: str = os.getenv("RESULTS_DIR", "results")
