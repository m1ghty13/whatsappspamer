"""
WhatsApp клиент на базе neonize.

neonize — Python-обёртка над whatsmeow (Go-библиотека),
реализует протокол WhatsApp Web через WebSocket.
Репозиторий: https://github.com/krypton-byte/neonize

Авторизация:
  При первом запуске создаётся файл qr.png и открывается автоматически.
  Отсканируй его телефоном: WhatsApp → Настройки → Связанные устройства.
  Сессия сохраняется в session.sqlite3 — повторное сканирование не нужно.

Важно про "кнопки":
  В неофициальном API кнопки с CTA-ссылкой недоступны —
  это функция только официального Business API.
  URL вставляется в конец текста: WhatsApp отображает превью-карточку.
"""

import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import segno
from neonize.client import NewClient
from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message, ExtendedTextMessage
from neonize.utils.jid import JID

logger = logging.getLogger(__name__)


class SendStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INVALID_PHONE = "invalid_phone"


@dataclass
class SendResult:
    phone: str
    status: SendStatus
    message_id: str = ""
    error: str = ""
    message_text: str = ""


def _phone_to_jid(phone: str) -> JID:
    return JID(user=phone, server="s.whatsapp.net")


class WhatsAppClient:
    """
    Обёртка над neonize.NewClient.

    Использование:
        client = WhatsAppClient()
        client.on_ready(lambda c: your_send_loop(c))
        client.run()   # блокирует; при первом запуске откроет qr.png
    """

    QR_IMAGE = "qr.png"

    def __init__(self, session_file: str = "session.sqlite3") -> None:
        self._client = NewClient(session_file)
        self._ready_callback = None
        self._register_qr_handler()
        self._register_event_handlers()

    # ─── Публичный интерфейс ─────────────────────────────────────────────────

    def on_ready(self, callback) -> None:
        """Регистрирует callback, вызываемый после подключения к WhatsApp."""
        self._ready_callback = callback

    def run(self) -> None:
        """
        Запускает connect() в фоновом потоке, ждёт флага connected,
        затем вызывает on_ready callback и держит соединение активным.
        """
        logger.info("Подключение к WhatsApp... (qr.png откроется автоматически)")

        t = threading.Thread(target=self._client.connect, daemon=True)
        t.start()

        # Ждём, пока neonize выставит флаг connected
        while not getattr(self._client, "connected", False):
            time.sleep(0.5)

        logger.info("WhatsApp подключён.")
        if self._ready_callback:
            self._ready_callback(self)

        t.join()  # держим процесс живым пока connect() работает

    def send_message(self, phone: str, text: str, url: str = "") -> SendResult:
        """
        Отправляет сообщение. Если url передан — добавляет к тексту,
        WhatsApp разворачивает его в превью-карточку.
        """
        jid = _phone_to_jid(phone)
        full_text = f"{text}\n\n{url}" if url else text

        msg = Message(
            extendedTextMessage=ExtendedTextMessage(
                text=full_text,
                matchedText=url,
                canonicalUrl=url,
                previewType=ExtendedTextMessage.NONE,
            )
        ) if url else Message(conversation=full_text)

        try:
            result = self._client.send_message(jid, msg)
            msg_id = str(getattr(result, "id", ""))
            logger.info("✓ Отправлено → %s (id=%s)", phone, msg_id)
            return SendResult(
                phone=phone,
                status=SendStatus.SUCCESS,
                message_id=msg_id,
                message_text=full_text,
            )
        except Exception as e:
            err = str(e)
            if "not on whatsapp" in err.lower() or "not found" in err.lower():
                logger.warning("✗ Номер не в WhatsApp: %s", phone)
                return SendResult(phone=phone, status=SendStatus.INVALID_PHONE,
                                  error=err, message_text=full_text)
            logger.error("✗ Ошибка для %s: %s", phone, err)
            return SendResult(phone=phone, status=SendStatus.FAILED,
                              error=err, message_text=full_text)

    # ─── Приватное ───────────────────────────────────────────────────────────

    def _register_qr_handler(self) -> None:
        """Сохраняет QR как PNG и открывает его вместо ASCII-арта в терминале."""

        @self._client.qr
        def _on_qr(client: NewClient, data: bytes) -> None:
            path = Path(self.QR_IMAGE)
            segno.make_qr(data).save(str(path), scale=10, border=2)
            logger.info("QR-код сохранён → %s", path.resolve())
            print(f"\n  Открой:  {path.resolve()}")
            print("  Отсканируй: WhatsApp → Настройки → Связанные устройства → Привязать устройство\n")
            try:
                if sys.platform == "win32":
                    os.startfile(str(path.resolve()))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(path)])
                else:
                    subprocess.Popen(["xdg-open", str(path)])
            except Exception as e:
                logger.debug("Не удалось открыть QR автоматически: %s", e)

    def _register_event_handlers(self) -> None:
        pass  # события заменены polling'ом в run()
