"""
Точка входа. Оркестрирует весь процесс рассылки.

Запуск:
    python main.py
    python main.py --contacts my_list.csv
    python main.py --dry-run    # тестовый прогон без реальных отправок

Первый запуск:
    В терминале появится QR-код. Отсканируй телефоном:
    WhatsApp → Настройки → Связанные устройства → Привязать устройство.
    Сессия сохраняется в session.sqlite3 — следующие запуски без QR.
"""

import argparse
import logging
import random
import sys
import time

import config
from contact_manager import load_contacts
from result_logger import ResultLogger
from whatsapp_client import WhatsAppClient, SendResult, SendStatus

# ─── Логирование ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sender.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ─── Антиспам ────────────────────────────────────────────────────────────────

def _random_delay() -> None:
    """Случайная пауза в диапазоне [DELAY_MIN_SEC, DELAY_MAX_SEC]."""
    delay = random.uniform(config.DELAY_MIN_SEC, config.DELAY_MAX_SEC)
    logger.info("Пауза %.0f сек...", delay)
    time.sleep(delay)


# ─── Основная логика ─────────────────────────────────────────────────────────

def _send_all(
    client: WhatsAppClient,
    contacts_file: str,
    dry_run: bool,
) -> None:
    """
    Вызывается после успешного подключения к WhatsApp.
    Проходит по контактам и отправляет сообщения.
    """
    contacts = load_contacts(contacts_file)
    if not contacts:
        logger.error("Список контактов пуст. Завершение.")
        sys.exit(1)

    logger.info("Контактов к обработке: %d", len(contacts))

    with ResultLogger(config.RESULTS_DIR) as log:
        for i, contact in enumerate(contacts, start=1):
            logger.info("[%d/%d] Отправка на %s", i, len(contacts), contact.phone)

            if dry_run:
                logger.info("[DRY-RUN] «%s»  →  %s", config.BASE_MESSAGE[:60], config.EVENT_URL)
                result = SendResult(
                    phone=contact.phone,
                    status=SendStatus.SUCCESS,
                    message_id="dry-run-id",
                    message_text=config.BASE_MESSAGE,
                )
            else:
                result = client.send_message(
                    phone=contact.phone,
                    text=config.BASE_MESSAGE,
                    url=config.EVENT_URL,
                )

            log.record(result)

            if i < len(contacts):
                _random_delay()

    logger.info("=== Рассылка завершена ===")


def run(contacts_file: str, dry_run: bool = False) -> None:
    logger.info("=== WhatsApp Sender запущен ===")

    if dry_run:
        logger.info("РЕЖИМ DRY-RUN: реальные запросы не выполняются.")
        # В dry-run режиме подключение не нужно — запускаем напрямую
        _send_all(client=None, contacts_file=contacts_file, dry_run=True)
        return

    wa = WhatsAppClient(session_file="session.sqlite3")
    wa.on_ready(lambda c: _send_all(c, contacts_file, dry_run=False))
    wa.run()  # блокирует; вызовет on_ready после авторизации


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WhatsApp bulk sender (UAE)")
    parser.add_argument(
        "--contacts",
        default=config.CONTACTS_FILE,
        help=f"Путь к файлу контактов (по умолчанию: {config.CONTACTS_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Тестовый прогон без реальных отправок (без QR-кода)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(contacts_file=args.contacts, dry_run=args.dry_run)
