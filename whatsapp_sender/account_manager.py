"""
Менеджер множественных WhatsApp-аккаунтов.

Каждый аккаунт — отдельный neonize.NewClient в своём потоке.
Сессии хранятся в папке sessions/ под именами account_0.sqlite3, account_1.sqlite3, ...

API:
    mgr = AccountManager()
    mgr.add_account(on_qr, on_status_change)   # добавить новый аккаунт
    mgr.remove_account(account_id)
    mgr.get_connected() -> list[AccountInfo]
    mgr.send_distributed(contacts, text, url)  # распределить по аккаунтам
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)


class AccountStatus(Enum):
    CONNECTING  = "connecting"   # ждёт QR или переподключается
    CONNECTED   = "connected"    # в сети, готов к отправке
    DISCONNECTED = "disconnected"
    ERROR       = "error"


@dataclass
class AccountInfo:
    account_id: str           # уникальный ID = имя файла без .sqlite3
    session_file: str         # полный путь к .sqlite3
    status: AccountStatus = AccountStatus.CONNECTING
    phone: str = ""           # номер телефона после авторизации
    sent_count: int = 0
    error_count: int = 0


# ── Поток одного аккаунта ─────────────────────────────────────────────────────

class _AccountThread(threading.Thread):
    """
    Запускает neonize.NewClient в фоне.
    Вызывает коллбэки on_qr, on_connected, on_disconnected из своего потока.
    """

    def __init__(
        self,
        info: AccountInfo,
        on_qr: Callable[[str, bytes], None],
        on_status: Callable[[str, AccountStatus, str], None],
        auto_profile: dict | None = None,
    ):
        super().__init__(daemon=True)
        self._info         = info
        self._on_qr        = on_qr
        self._on_status    = on_status
        self._client       = None
        self._auto_profile = auto_profile or {}
        self._stopped      = False

    @property
    def client(self):
        return self._client

    def run(self) -> None:
        try:
            from neonize.client import NewClient
            from neonize.events import (
                ConnectedEv, DisconnectedEv, LoggedOutEv,
                PairStatusEv, ConnectFailureEv,
            )
            import segno, os, sys, subprocess, time

            self._client = NewClient(self._info.session_file)

            # threading.Event — единственная безопасная операция из ctypes-коллбэка
            _connected_ev    = threading.Event()
            _disconnected_ev = threading.Event()
            _logged_out_ev   = threading.Event()

            @self._client.event(ConnectedEv)
            def _on_connected(c, _ev):
                _connected_ev.set()
                _disconnected_ev.clear()

            @self._client.event(PairStatusEv)
            def _on_pair(c, ev):
                # После первого сканирования QR — сразу идёт 515 и переподключение.
                # PairStatusEv сигнализирует что паринг прошёл; ConnectedEv придёт
                # через ~2 сек. Взводим флаг только если статус успешный.
                try:
                    if not ev.Error:
                        # не трогаем _connected_ev — ждём ConnectedEv после 515
                        pass
                except Exception:
                    pass

            @self._client.event(DisconnectedEv)
            def _on_disconnected(c, _ev):
                _disconnected_ev.set()
                _connected_ev.clear()

            @self._client.event(ConnectFailureEv)
            def _on_connect_failure(c, _ev):
                _disconnected_ev.set()
                _connected_ev.clear()

            @self._client.event(LoggedOutEv)
            def _on_logged_out(c, _ev):
                _logged_out_ev.set()
                _disconnected_ev.set()
                _connected_ev.clear()

            # QR handler
            @self._client.qr
            def _on_qr(c, data: bytes):
                if not self._stopped:
                    self._on_qr(self._info.account_id, data)

            # Вотчер в отдельном потоке — ждёт события + polling-фоллбэк
            def _watch():
                # Ждём ConnectedEv до 120 сек.
                # Фоллбэк: каждые 0.5 сек проверяем client.connected напрямую —
                # на случай если ConnectedEv не дошёл (первый QR + 515 reconnect).
                deadline = time.monotonic() + 120
                while not _connected_ev.is_set():
                    if time.monotonic() > deadline:
                        break
                    if getattr(self._client, "connected", False):
                        _connected_ev.set()
                        break
                    time.sleep(0.5)

                if not _connected_ev.is_set():
                    self._info.status = AccountStatus.ERROR
                    self._on_status(self._info.account_id, AccountStatus.ERROR, "")
                    return

                me = getattr(self._client, "me", None)
                phone = str(getattr(me, "user", "")) if me else ""
                self._info.phone  = phone
                self._info.status = AccountStatus.CONNECTED
                self._on_status(self._info.account_id, AccountStatus.CONNECTED, phone)

                # Применяем автопрофиль (имя + фото) один раз после входа
                self._apply_auto_profile()

                # Продолжаем слушать отключения/переподключения/логаут
                while True:
                    _disconnected_ev.wait()
                    if not self.is_alive():
                        break

                    if _logged_out_ev.is_set():
                        self._info.status = AccountStatus.ERROR
                        self._on_status(
                            self._info.account_id, AccountStatus.ERROR,
                            "Удалён с телефона — удали и добавь снова"
                        )
                        return

                    self._info.status = AccountStatus.DISCONNECTED
                    self._on_status(self._info.account_id, AccountStatus.DISCONNECTED, "")
                    _disconnected_ev.clear()

                    # Ждём переподключения с polling-фоллбэком
                    reconnect_deadline = time.monotonic() + 30
                    while not _connected_ev.is_set():
                        if time.monotonic() > reconnect_deadline:
                            break
                        if getattr(self._client, "connected", False):
                            _connected_ev.set()
                            break
                        time.sleep(0.5)

                    if _logged_out_ev.is_set():
                        self._info.status = AccountStatus.ERROR
                        self._on_status(
                            self._info.account_id, AccountStatus.ERROR,
                            "Удалён с телефона — удали и добавь снова"
                        )
                        return
                    if _connected_ev.is_set():
                        self._info.status = AccountStatus.CONNECTED
                        self._on_status(self._info.account_id, AccountStatus.CONNECTED, self._info.phone)
                    else:
                        self._info.status = AccountStatus.ERROR
                        self._on_status(self._info.account_id, AccountStatus.ERROR, "")
                        break

            threading.Thread(target=_watch, daemon=True).start()

            self._client.connect()   # блокирует пока соединение живо

            self._info.status = AccountStatus.DISCONNECTED
            self._on_status(self._info.account_id, AccountStatus.DISCONNECTED, "")

        except Exception as e:
            logger.error("Account %s thread error: %s", self._info.account_id, e)
            self._info.status = AccountStatus.ERROR
            self._on_status(self._info.account_id, AccountStatus.ERROR, str(e))

    def _apply_auto_profile(self) -> None:
        """Применяет имя и фото профиля из настроек автопрофиля."""
        if not self._client or not self._auto_profile:
            return
        name = self._auto_profile.get("name", "").strip()
        photo = self._auto_profile.get("photo_path", "").strip()
        if name:
            try:
                self._client.set_profile_name(name)
                logger.info("Account %s: имя профиля установлено → %s", self._info.account_id, name)
            except Exception as e:
                logger.warning("Account %s: не удалось установить имя: %s", self._info.account_id, e)
        if photo and Path(photo).is_file():
            try:
                self._client.set_profile_photo(photo)
                logger.info("Account %s: фото профиля установлено.", self._info.account_id)
            except Exception as e:
                logger.warning("Account %s: не удалось установить фото: %s", self._info.account_id, e)

    def send(
        self,
        phone: str,
        text: str,
        url: str = "",
        button_text: str = "",
        button_url: str = "",
    ) -> bool:
        """Отправляет сообщение через этот аккаунт.

        button_text + button_url → InteractiveMessage с NativeFlow cta_url кнопкой.
        url (без кнопки)         → ExtendedTextMessage с превью ссылки.
        иначе                    → обычный текст.
        """
        if not self._client or not getattr(self._client, "connected", False):
            return False
        if self._info.status == AccountStatus.ERROR:
            return False
        try:
            import json
            from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
                Message, ExtendedTextMessage, InteractiveMessage,
            )
            from neonize.utils.jid import JID

            jid = JID(User=phone, Server="s.whatsapp.net", RawAgent=0, Device=0, Integrator=0)

            if button_text and button_url:
                # Убеждаемся что URL абсолютный — без схемы мобильный WA не открывает
                _burl = button_url
                if _burl and not _burl.startswith(("http://", "https://")):
                    _burl = "https://" + _burl
                # InteractiveMessage с URL-кнопкой (NativeFlow cta_url)
                params = json.dumps({
                    "display_text": button_text,
                    "url": _burl,
                    "merchant_url": _burl,
                })
                msg = Message(
                    interactiveMessage=InteractiveMessage(
                        body=InteractiveMessage.Body(text=text),
                        footer=InteractiveMessage.Footer(text=""),
                        nativeFlowMessage=InteractiveMessage.NativeFlowMessage(
                            buttons=[
                                InteractiveMessage.NativeFlowMessage.NativeFlowButton(
                                    name="cta_url",
                                    buttonParamsJSON=params,
                                )
                            ],
                            messageVersion=1,
                        ),
                    )
                )
            elif url:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                full_text = f"{text}\n\n{url}"
                msg = Message(
                    extendedTextMessage=ExtendedTextMessage(
                        text=full_text,
                        matchedText=url,
                        canonicalUrl=url,
                        previewType=ExtendedTextMessage.NONE,
                    )
                )
            else:
                msg = Message(conversation=text)

            self._client.send_message(jid, msg)
            self._info.sent_count += 1
            return True
        except Exception as e:
            logger.error("Send error on account %s → %s: %s", self._info.account_id, phone, e)
            self._info.error_count += 1
            return False


# ── AccountManager ────────────────────────────────────────────────────────────

class AccountManager:
    """
    Управляет пулом WhatsApp-аккаунтов.

    Коллбэки вызываются из фоновых потоков — в GUI подключай через Qt Signal.
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._threads: dict[str, _AccountThread] = {}   # id -> thread

        # Автопрофиль: применяется к каждому аккаунту после подключения
        self.auto_profile: dict = {}   # {"name": "...", "photo_path": "..."}

        # Коллбэки (устанавливает GUI)
        self.on_qr:     Callable[[str, bytes], None]               | None = None
        self.on_status: Callable[[str, AccountStatus, str], None]  | None = None

        self._restore_sessions()

    # ── Публичный API ─────────────────────────────────────────────────────────

    def add_account(self) -> str:
        """Создаёт новый аккаунт и запускает подключение. Возвращает account_id."""
        account_id = self._next_id()
        session_file = str(SESSIONS_DIR / f"{account_id}.sqlite3")
        info = AccountInfo(account_id=account_id, session_file=session_file)
        self._start(info)
        return account_id

    def remove_account(self, account_id: str) -> None:
        """
        Удаляет аккаунт из активного пула.

        Поскольку neonize держит SQLite открытым через Go-рантайм,
        файл может оставаться заблокированным даже после disconnect().
        Стратегия:
          1. Убираем аккаунт из списка (он больше не используется).
          2. Ставим маркер .pending_delete рядом с файлом.
          3. Пробуем удалить сразу; если не получается — удалится при
             следующем запуске до того как neonize откроет файл.
        """
        with self._lock:
            t = self._threads.pop(account_id, None)

        # Сигнализируем клиенту остановиться
        if t:
            t._stopped = True
            if t.client:
                try:
                    t.client.disconnect()
                except Exception:
                    pass

        # Ставим маркер — гарантия удаления при следующем старте
        marker = SESSIONS_DIR / f"{account_id}.pending_delete"
        marker.touch()

        # Пробуем удалить сразу (с небольшой паузой)
        time.sleep(1.0)
        deleted = True
        for suffix in (".sqlite3", ".png"):
            p = SESSIONS_DIR / f"{account_id}{suffix}"
            if not p.exists():
                continue
            try:
                p.unlink()
            except PermissionError:
                deleted = False
                logger.warning(
                    "Файл %s занят Go-рантаймом neonize. "
                    "Будет удалён при следующем запуске приложения.", p.name
                )

        if deleted:
            marker.unlink(missing_ok=True)

    def get_all(self) -> list[AccountInfo]:
        with self._lock:
            return [t._info for t in self._threads.values()]

    def get_connected(self) -> list[_AccountThread]:
        with self._lock:
            return [t for t in self._threads.values()
                    if t._info.status == AccountStatus.CONNECTED]

    def send_distributed(
        self,
        contacts: list[dict],
        text: str,
        url: str = "",
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[int, int]:
        """
        Распределяет список контактов равномерно по подключённым аккаунтам.
        Каждый аккаунт отправляет свой срез в отдельном потоке.
        Возвращает (sent, errors).
        """
        workers = self.get_connected()
        if not workers:
            raise RuntimeError("Нет подключённых аккаунтов WhatsApp.")

        n = len(workers)
        chunks = [contacts[i::n] for i in range(n)]

        results: list[tuple[int, int]] = [(0, 0)] * n
        lock = threading.Lock()
        done_count = [0]
        total = len(contacts)

        def _worker(idx: int, chunk: list[dict]):
            sent = errors = 0
            for contact in chunk:
                ok = workers[idx].send(contact["phone"], text, url)
                if ok:
                    sent += 1
                else:
                    errors += 1
                with lock:
                    done_count[0] += 1
                    if on_progress:
                        on_progress(done_count[0], total)
            with lock:
                results[idx] = (sent, errors)

        threads = [
            threading.Thread(target=_worker, args=(i, chunk), daemon=True)
            for i, chunk in enumerate(chunks)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_sent   = sum(r[0] for r in results)
        total_errors = sum(r[1] for r in results)
        return total_sent, total_errors

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _start(self, info: AccountInfo) -> None:
        t = _AccountThread(
            info=info,
            on_qr=lambda aid, data: self.on_qr(aid, data) if self.on_qr else None,
            on_status=lambda aid, st, phone: self.on_status(aid, st, phone) if self.on_status else None,
            auto_profile=self.auto_profile,
        )
        with self._lock:
            self._threads[info.account_id] = t
        t.start()

    def _next_id(self) -> str:
        existing = {p.stem for p in SESSIONS_DIR.glob("account_*.sqlite3")}
        i = 0
        while f"account_{i}" in existing or f"account_{i}" in self._threads:
            i += 1
        return f"account_{i}"

    def _restore_sessions(self) -> None:
        """При старте удаляет pending_delete файлы и восстанавливает живые сессии."""
        # Сначала удаляем всё помеченное на удаление (файл свободен — neonize ещё не запущен)
        for marker in SESSIONS_DIR.glob("*.pending_delete"):
            account_id = marker.stem
            for suffix in (".sqlite3", ".png"):
                p = SESSIONS_DIR / f"{account_id}{suffix}"
                p.unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
            logger.info("Удалён аккаунт %s (отложенное удаление).", account_id)

        for session_file in sorted(SESSIONS_DIR.glob("account_*.sqlite3")):
            account_id = session_file.stem
            info = AccountInfo(account_id=account_id, session_file=str(session_file))
            self._start(info)
