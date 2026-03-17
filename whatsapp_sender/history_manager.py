"""
Менеджер истории отправок.

Структура файлов:
  history.csv  — все контакты, которым уже отправлено сообщение
  queue.csv    — остаток очереди (контакты которым ещё НЕ отправлено)

При каждой отправке:
  1. Запись добавляется в history.csv
  2. Номер помечается в памяти как отправленный
  3. При вызове save_queue() — сохраняется актуальный остаток очереди
"""

import csv
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

HISTORY_FILE = Path("history.csv")
QUEUE_FILE   = Path("queue.csv")

_HISTORY_FIELDS = ["timestamp", "phone", "name", "status", "message_preview"]


def load_sent_phones() -> set[str]:
    """Возвращает множество номеров из истории (чтобы не слать повторно)."""
    if not HISTORY_FILE.exists():
        return set()
    phones: set[str] = set()
    try:
        with open(HISTORY_FILE, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("phone"):
                    phones.add(row["phone"].strip())
    except Exception as e:
        logger.warning("Не удалось прочитать history.csv: %s", e)
    return phones


def record_sent(phone: str, name: str, status: str, message: str = "") -> None:
    """Добавляет строку в history.csv (создаёт файл если нет)."""
    write_header = not HISTORY_FILE.exists()
    try:
        with open(HISTORY_FILE, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=_HISTORY_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "phone":           phone,
                "name":            name,
                "status":          status,
                "message_preview": message[:80],
            })
    except Exception as e:
        logger.error("Не удалось записать в history.csv: %s", e)


def save_queue(contacts: list[dict]) -> None:
    """
    Сохраняет оставшиеся контакты в queue.csv.
    Вызывать после каждой отправки или при остановке.
    """
    try:
        with open(QUEUE_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["phone", "name"])
            writer.writeheader()
            for c in contacts:
                writer.writerow({"phone": c.get("phone", ""), "name": c.get("name", "")})
    except Exception as e:
        logger.error("Не удалось сохранить queue.csv: %s", e)


def history_count() -> int:
    """Возвращает количество строк в истории."""
    if not HISTORY_FILE.exists():
        return 0
    try:
        with open(HISTORY_FILE, encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in f) - 1)  # минус заголовок
    except Exception:
        return 0
