"""
Главное окно приложения ОАЭ — WhatsApp Sender.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable

from PySide6.QtCore import (
    Qt, QThread, Signal, QSize, QDateTime, QTimer,
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QFontMetrics,
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QListWidget,
    QListWidgetItem, QComboBox, QCheckBox, QDateTimeEdit,
    QSplitter, QStackedWidget, QScrollArea, QFrame,
    QMessageBox, QInputDialog, QSizePolicy,
)

import config_manager
from account_manager import AccountManager
from gui.proxy_dialog import ProxyDialog
from gui.accounts_tab import AccountsTab
from gui.gpt_dialog import GptSettingsDialog

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  Stub backend functions (replaced by real implementations from whatsapp_client)
# ══════════════════════════════════════════════════════════════════════════════

def load_contacts():
    return [
        {"id": i, "name": f"Contact {i}", "phone": f"+971501234{i:03d}"}
        for i in range(1, 6)
    ]


def send_test_message(phone: str, text: str, proxy_settings=None) -> bool:
    time.sleep(1)  # simulate network call
    return True


def send_bulk_messages(
    contacts: list,
    text: str,
    proxy_settings=None,
    on_progress: Callable | None = None,
) -> tuple[int, int]:
    for i, _c in enumerate(contacts):
        time.sleep(0.1)
        if on_progress:
            on_progress(i + 1, len(contacts))
    return len(contacts), 0


# ══════════════════════════════════════════════════════════════════════════════
#  SimpleChart — QWidget drawing two line series with QPainter
# ══════════════════════════════════════════════════════════════════════════════

class SimpleChart(QWidget):
    """
    Tiny sparkline chart that draws two series:
      - sent  (purple #6C63FF)
      - errors (red #FF6B6B)

    Call add_point(sent, errors) to append a data point and redraw.
    """

    _COLOR_SENT   = QColor("#6C63FF")
    _COLOR_ERRORS = QColor("#FF6B6B")
    _COLOR_BG     = QColor("#0F1829")
    _COLOR_GRID   = QColor("#1E2A4A")
    _MAX_POINTS   = 30

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setMinimumWidth(80)
        self._sent:   list[int] = []
        self._errors: list[int] = []

    def add_point(self, sent: int, errors: int) -> None:
        self._sent.append(sent)
        self._errors.append(errors)
        if len(self._sent) > self._MAX_POINTS:
            self._sent   = self._sent[-self._MAX_POINTS:]
            self._errors = self._errors[-self._MAX_POINTS:]
        self.update()

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        pad = 4

        # background
        p.fillRect(0, 0, w, h, self._COLOR_BG)

        # horizontal grid line at mid
        p.setPen(QPen(self._COLOR_GRID, 1))
        p.drawLine(pad, h // 2, w - pad, h // 2)

        n = len(self._sent)
        if n < 2:
            p.end()
            return

        all_vals = self._sent + self._errors
        max_v = max(all_vals) or 1

        def _series_points(series: list[int]) -> list[tuple[float, float]]:
            pts = []
            for i, v in enumerate(series):
                x = pad + i * (w - 2 * pad) / (n - 1)
                y = (h - pad) - v / max_v * (h - 2 * pad)
                pts.append((x, y))
            return pts

        self._draw_series(p, _series_points(self._sent),   self._COLOR_SENT)
        self._draw_series(p, _series_points(self._errors), self._COLOR_ERRORS)
        p.end()

    @staticmethod
    def _draw_series(
        painter: QPainter,
        pts: list[tuple[float, float]],
        color: QColor,
    ) -> None:
        pen = QPen(color, 1.5)
        painter.setPen(pen)
        for i in range(1, len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            painter.drawLine(int(x0), int(y0), int(x1), int(y1))
        # dots at each point
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        for x, y in pts:
            painter.drawEllipse(int(x) - 2, int(y) - 2, 4, 4)


# ══════════════════════════════════════════════════════════════════════════════
#  Worker threads
# ══════════════════════════════════════════════════════════════════════════════

class _TestWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, phone: str, text: str, proxy_settings):
        super().__init__()
        self._phone   = phone
        self._text    = text
        self._proxy   = proxy_settings

    def run(self) -> None:
        try:
            ok = send_test_message(self._phone, self._text, self._proxy)
            self.finished.emit(ok, "Сообщение отправлено успешно." if ok else "Не удалось отправить.")
        except Exception as exc:
            self.finished.emit(False, f"Ошибка: {exc}")


class _SequentialBulkWorker(QThread):
    """
    Последовательная рассылка с задержками и поддержкой остановки.

    Сигналы:
      progress(done, total, phone)  — после каждой отправки
      contact_sent(index)           — индекс контакта в списке (для удаления из GUI)
      finished(sent, errors, stopped)
    """
    progress     = Signal(int, int, str, int, int)  # done, total, phone, sent, errors
    contact_sent = Signal(int)                      # index в исходном списке
    log_entry    = Signal(str, bool)                # "phone  name", ok
    finished     = Signal(int, int, bool)           # sent, errors, was_stopped

    DELAY_MIN = 10   # сек
    DELAY_MAX = 25   # сек

    def __init__(
        self,
        manager,
        contacts: list,
        text: str,
        url: str,
        stop_event: "threading.Event",
        gpt_cfg: dict | None = None,
        proxies: dict | None = None,
        button_text: str = "",
        button_url: str = "",
    ):
        super().__init__()
        self._manager      = manager
        self._contacts     = contacts
        self._text         = text
        self._url          = url
        self._stop         = stop_event
        self._gpt_cfg      = gpt_cfg or {}
        self._proxies      = proxies
        self._button_text  = button_text
        self._button_url   = button_url

    def run(self) -> None:
        import threading, random, time
        import history_manager

        accounts = self._manager.get_connected()
        if not accounts:
            self.finished.emit(0, len(self._contacts), False)
            return

        # GPT: подготовим параметры один раз
        use_gpt = bool(
            self._gpt_cfg.get("enabled")
            and self._gpt_cfg.get("api_key", "").strip()
        )
        if use_gpt:
            from gpt_text_variator import generate_variant as _gpt_variant
            _gpt_model  = self._gpt_cfg.get("model", "gpt-4.1-mini")
            _gpt_temp   = float(self._gpt_cfg.get("temperature", 0.3))
            _gpt_key    = self._gpt_cfg.get("api_key", "")
        else:
            _gpt_variant = None

        sent = errors = 0
        total = len(self._contacts)

        for idx, contact in enumerate(self._contacts):
            if self._stop.is_set():
                history_manager.save_queue(self._contacts[idx:])
                self.finished.emit(sent, errors, True)
                return

            phone = contact.get("phone", "").lstrip("+")
            name  = contact.get("name", "")

            # Генерируем вариацию текста (если включено)
            if use_gpt and _gpt_variant is not None:
                send_text = _gpt_variant(
                    self._text,
                    api_key=_gpt_key,
                    model=_gpt_model,
                    temperature=_gpt_temp,
                    proxies=self._proxies,
                )
            else:
                send_text = self._text

            # Round-robin по аккаунтам
            account = accounts[idx % len(accounts)]
            ok = account.send(
                phone, send_text, self._url,
                button_text=self._button_text,
                button_url=self._button_url,
            )

            if ok:
                sent += 1
                history_manager.record_sent(
                    contact.get("phone", ""), name, "success", send_text
                )
            else:
                errors += 1
                history_manager.record_sent(
                    contact.get("phone", ""), name, "failed", send_text
                )

            label = contact.get("phone", "")
            if contact.get("name"):
                label = f"{contact['name']}  {label}"
            self.log_entry.emit(label, ok)
            self.contact_sent.emit(idx)
            self.progress.emit(idx + 1, total, contact.get("phone", ""), sent, errors)

            # Случайная задержка перед следующим (кроме последнего)
            if idx < total - 1:
                delay = random.uniform(self.DELAY_MIN, self.DELAY_MAX)
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline:
                    if self._stop.is_set():
                        history_manager.save_queue(self._contacts[idx + 1:])
                        self.finished.emit(sent, errors, True)
                        return
                    time.sleep(0.4)

        history_manager.save_queue([])   # очередь пуста
        self.finished.emit(sent, errors, False)


class _BulkWorker(QThread):
    progress  = Signal(int, int)   # (done, total)
    finished  = Signal(int, int)   # (sent, errors)

    def __init__(self, contacts: list, text: str, proxy_settings):
        super().__init__()
        self._contacts = contacts
        self._text     = text
        self._proxy    = proxy_settings

    def run(self) -> None:
        try:
            sent, errors = send_bulk_messages(
                self._contacts,
                self._text,
                self._proxy,
                on_progress=lambda d, t: self.progress.emit(d, t),
            )
            self.finished.emit(sent, errors)
        except Exception as exc:
            logger.error("Bulk send error: %s", exc)
            self.finished.emit(0, len(self._contacts))


# ══════════════════════════════════════════════════════════════════════════════
#  Helper builders
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_gpt_proxy(gpt_cfg: dict, system_proxies: dict | None) -> dict | None:
    """Возвращает прокси-dict для GPT на основе proxy_mode из конфига."""
    mode = gpt_cfg.get("proxy_mode", "none")
    if mode == "system":
        return system_proxies
    if mode == "custom":
        url = gpt_cfg.get("custom_proxy", "").strip()
        if url:
            return {"http": url, "https": url}
    return None   # none


def _icon_btn(text: str, tooltip: str = "", parent: QWidget | None = None) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setObjectName("iconBtn")
    btn.setFixedSize(QSize(32, 32))
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def _panel(parent: QWidget | None = None) -> QWidget:
    w = QWidget(parent)
    w.setObjectName("panel")
    return w


def _panel_title(text: str, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setObjectName("panelTitle")
    return lbl


# ══════════════════════════════════════════════════════════════════════════════
#  MainWindow
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ОАЭ — WhatsApp Sender")
        self.setMinimumSize(1200, 750)

        # runtime state
        self._cfg:           dict  = config_manager.load()
        self._templates:     list  = []
        self._total_sent:    int   = 0
        self._total_failed:  int   = 0
        self._total_errors:  int   = 0

        # worker refs (keep alive)
        self._test_worker: _TestWorker | None = None
        self._bulk_worker: _BulkWorker | None = None

        # account manager (multiple WA accounts + multithreaded send)
        self._account_manager = AccountManager()

        self._all_contacts: list[dict] = []
        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  UI construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root_widget = QWidget()
        self.setCentralWidget(root_widget)

        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. top bar
        root_layout.addWidget(self._build_top_bar())

        # 2. stacked pages
        self._stack = QStackedWidget()
        root_layout.addWidget(self._stack, 1)

        self._stack.addWidget(self._build_contacts_page())    # 0 – Список контактов
        self._stack.addWidget(self._build_broadcast_page())   # 1 – Рассылка
        self._stack.addWidget(self._build_templates_page())   # 2 – Шаблоны
        self._accounts_tab = AccountsTab(self._account_manager, self._cfg)
        self._stack.addWidget(self._accounts_tab)             # 3 – Аккаунты

        self._stack.setCurrentIndex(1)  # default to broadcast
        self._tab_buttons[1].setProperty("active", True)

        # 3. bottom status strip
        root_layout.addWidget(self._build_status_strip())

    # ── Top bar ───────────────────────────────────────────────────────────────

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topBar")
        bar.setFixedHeight(48)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        # hamburger / logo area
        menu_btn = _icon_btn("☰", "Меню")
        menu_btn.clicked.connect(lambda: None)
        layout.addWidget(menu_btn)

        title = QLabel("ОАЭ")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        layout.addSpacing(16)

        # tab buttons
        tab_names = ["Список контактов", "Рассылка", "Шаблоны", "Аккаунты"]
        self._tab_buttons: list[QPushButton] = []

        for idx, name in enumerate(tab_names):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("tabBtn")
            btn.setStyleSheet("""
                QPushButton[active="true"] {
                    color: #FFFFFF;
                    border-bottom: 2px solid #6C63FF;
                    background: #1A1A2E;
                }
                QPushButton {
                    background: transparent;
                    border: none;
                    border-bottom: 2px solid transparent;
                    color: #8888AA;
                    padding: 8px 18px;
                    font-size: 13px;
                }
                QPushButton:hover { color: #CCCCFF; }
            """)
            btn.clicked.connect(lambda _checked, i=idx: self._switch_tab(i))
            self._tab_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # right side controls
        self._search_top = QLineEdit()
        self._search_top.setPlaceholderText("Поиск...")
        self._search_top.setFixedWidth(180)
        self._search_top.textChanged.connect(self._on_top_search)
        layout.addWidget(self._search_top)

        layout.addSpacing(4)

        proxy_btn = _icon_btn("⚙", "Настройки прокси")
        proxy_btn.clicked.connect(self._on_open_proxy)
        layout.addWidget(proxy_btn)

        notif_btn = _icon_btn("🔔", "Уведомления")
        layout.addWidget(notif_btn)

        return bar

    def _switch_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._tab_buttons):
            btn.setProperty("active", str(i == index).lower())
            # Force style refresh
            btn.setStyleSheet(btn.styleSheet())

    # ── Contacts page (tab 0) ─────────────────────────────────────────────────

    def _build_contacts_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)

        title = _panel_title("Список контактов")
        layout.addWidget(title)

        info = QLabel(
            "Здесь отображаются все загруженные контакты. "
            "Используйте вкладку «Рассылка» для отправки сообщений."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #8888AA;")
        layout.addWidget(info)

        self._contacts_all_list = QListWidget()
        layout.addWidget(self._contacts_all_list, 1)

        load_btn = QPushButton("📂  Открыть файл контактов")
        load_btn.clicked.connect(self._load_contacts)
        layout.addWidget(load_btn)

        return page

    # ── Broadcast page (tab 1) ────────────────────────────────────────────────

    def _build_broadcast_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # horizontal splitter: left | center | right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        page_layout.addWidget(splitter, 1)

        splitter.addWidget(self._build_left_contacts_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())

        splitter.setSizes([220, 700, 280])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        return page

    # ── Templates page (tab 2) ────────────────────────────────────────────────

    def _build_templates_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)

        title = _panel_title("Управление шаблонами")
        layout.addWidget(title)

        self._templates_main_list = QListWidget()
        self._templates_main_list.itemDoubleClicked.connect(
            lambda item: self._apply_template_from_item(item)
        )
        layout.addWidget(self._templates_main_list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Добавить шаблон")
        add_btn.clicked.connect(self._on_add_template_dialog)
        del_btn = QPushButton("Удалить выбранный")
        del_btn.clicked.connect(self._on_delete_template)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return page

    # ── Left contacts panel ───────────────────────────────────────────────────

    def _build_left_contacts_panel(self) -> QWidget:
        panel = _panel()
        panel.setFixedWidth(220)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # header row: label + кнопка открыть файл
        header_row = QHBoxLayout()
        self._contacts_header = QLabel("0 контактов выбрано")
        self._contacts_header.setObjectName("panelTitle")
        header_row.addWidget(self._contacts_header, 1)

        open_btn = _icon_btn("📂", "Открыть файл контактов")
        open_btn.clicked.connect(self._load_contacts)
        header_row.addWidget(open_btn)
        layout.addLayout(header_row)

        # search
        self._contact_search = QLineEdit()
        self._contact_search.setPlaceholderText("Поиск контактов...")
        self._contact_search.textChanged.connect(self._filter_contacts)
        layout.addWidget(self._contact_search)

        # filter combo
        self._contact_filter = QComboBox()
        self._contact_filter.addItems(["Все", "Из файла", "Вручную"])
        self._contact_filter.currentTextChanged.connect(self._filter_contacts)
        layout.addWidget(self._contact_filter)

        # "select all" row
        sel_row = QHBoxLayout()
        self._chk_all = QCheckBox("Все")
        self._chk_all.setChecked(True)
        self._chk_all.stateChanged.connect(self._on_check_all)
        sel_row.addWidget(self._chk_all)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # contact list
        self._contact_list = QListWidget()
        self._contact_list.itemChanged.connect(self._on_contact_item_changed)
        layout.addWidget(self._contact_list, 1)

        return panel

    # ── Center panel ──────────────────────────────────────────────────────────

    def _build_center_panel(self) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ── compose + preview row ──────────────────────────────────────────────
        compose_row = QHBoxLayout()
        compose_row.setSpacing(8)
        compose_row.addWidget(self._build_compose_form(), 1)
        compose_row.addWidget(self._build_preview_panel(), 1)
        outer.addLayout(compose_row, 1)

        # ── button row ────────────────────────────────────────────────────────
        outer.addWidget(self._build_action_buttons())

        # ── schedule bar ──────────────────────────────────────────────────────
        outer.addWidget(self._build_schedule_bar())

        # ── send status line ──────────────────────────────────────────────────
        self._send_status_lbl = QLabel("Выбрано: 0 контактов для рассылки")
        self._send_status_lbl.setStyleSheet("color: #8888AA; font-size: 12px;")
        outer.addWidget(self._send_status_lbl)

        return container

    def _build_compose_form(self) -> QWidget:
        form = _panel()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(_panel_title("Сообщение"))

        # message
        self._message_edit = QTextEdit()
        self._message_edit.setPlaceholderText("Введите сообщение…")
        self._message_edit.textChanged.connect(self._on_message_changed)
        layout.addWidget(self._message_edit, 1)

        # char counter
        self._char_counter = QLabel("0/500")
        self._char_counter.setStyleSheet("color: #8888AA; font-size: 11px;")
        self._char_counter.setAlignment(Qt.AlignRight)
        layout.addWidget(self._char_counter)

        # ── URL-кнопка (опционально) ──────────────────────────────────────────
        self._chk_button = QCheckBox("Добавить кнопку-ссылку")
        self._chk_button.setStyleSheet("font-size: 12px; color: #AAAACC;")
        self._chk_button.setToolTip(
            "Отправить сообщение с кнопкой-ссылкой (InteractiveMessage).\n"
            "⚠ Работает только на аккаунтах без ограничений.\n"
            "При массовой отправке повышает риск блокировки."
        )
        self._chk_button.toggled.connect(self._on_button_toggled)
        layout.addWidget(self._chk_button)

        self._btn_fields = QWidget()
        btn_fl = QVBoxLayout(self._btn_fields)
        btn_fl.setContentsMargins(0, 2, 0, 2)
        btn_fl.setSpacing(4)

        self._btn_text_edit = QLineEdit()
        self._btn_text_edit.setPlaceholderText("Текст кнопки, напр: «Перейти на сайт»")
        self._btn_text_edit.textChanged.connect(self._update_preview)
        btn_fl.addWidget(self._btn_text_edit)

        self._btn_url_edit = QLineEdit()
        self._btn_url_edit.setPlaceholderText("URL кнопки, напр: https://example.com")
        self._btn_url_edit.textChanged.connect(self._update_preview)
        btn_fl.addWidget(self._btn_url_edit)

        self._btn_fields.setVisible(False)
        layout.addWidget(self._btn_fields)

        # ── ChatGPT вариации ──────────────────────────────────────────────────
        gpt_row = QHBoxLayout()
        gpt_row.setSpacing(4)

        self._chk_gpt = QCheckBox("ChatGPT вариации")
        self._chk_gpt.setToolTip(
            "Слегка переформулировать каждое сообщение через ChatGPT\n"
            "перед отправкой (ссылки и числа остаются без изменений)."
        )
        self._chk_gpt.setStyleSheet("font-size: 12px; color: #AAAACC;")
        self._chk_gpt.setChecked(bool(self._cfg.get("gpt", {}).get("enabled", False)))
        self._chk_gpt.toggled.connect(self._on_gpt_toggled)
        gpt_row.addWidget(self._chk_gpt)

        gpt_settings_btn = _icon_btn("⚙", "Настройки ChatGPT (ключ, модель, temperature)")
        gpt_settings_btn.clicked.connect(self._on_open_gpt_settings)
        gpt_row.addWidget(gpt_settings_btn)
        gpt_row.addStretch()

        layout.addLayout(gpt_row)

        return form

    def _build_preview_panel(self) -> QWidget:
        preview = QWidget()
        preview.setObjectName("previewPanel")

        layout = QVBoxLayout(preview)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        hdr = QLabel("Предпросмотр")
        hdr.setObjectName("panelTitle")
        layout.addWidget(hdr)

        # phone-like chat area
        chat_area = QWidget()
        chat_area.setStyleSheet("background: #0D1117; border-radius: 8px;")

        chat_layout = QVBoxLayout(chat_area)
        chat_layout.setContentsMargins(10, 10, 10, 10)
        chat_layout.setAlignment(Qt.AlignBottom | Qt.AlignLeft)

        self._bubble_lbl = QLabel("…")
        self._bubble_lbl.setObjectName("bubble")
        self._bubble_lbl.setWordWrap(True)
        self._bubble_lbl.setTextFormat(Qt.PlainText)
        self._bubble_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        # timestamp inside bubble
        self._bubble_time = QLabel(datetime.now().strftime("%H:%M"))
        self._bubble_time.setStyleSheet("color: #8BBF8B; font-size: 10px;")
        self._bubble_time.setAlignment(Qt.AlignRight)

        chat_layout.addStretch()
        chat_layout.addWidget(self._bubble_lbl)
        chat_layout.addWidget(self._bubble_time)

        layout.addWidget(chat_area, 1)

        return preview

    def _build_action_buttons(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        btn_test = QPushButton("▷  Отправить тест")
        btn_test.setStyleSheet(
            "QPushButton { background: #1E3A6E; color: #7EB8FF; }"
            "QPushButton:hover { background: #2A5090; }"
        )
        btn_test.clicked.connect(self._on_send_test)
        layout.addWidget(btn_test)

        btn_save_tpl = QPushButton("Сохранить шаблон")
        btn_save_tpl.clicked.connect(self._on_save_template)
        layout.addWidget(btn_save_tpl)

        btn_reset = QPushButton("Сбросить")
        btn_reset.setObjectName("btnReset")
        btn_reset.clicked.connect(self._on_reset)
        layout.addWidget(btn_reset)

        layout.addStretch()

        self._btn_stop = QPushButton("⏹  Остановить")
        self._btn_stop.setStyleSheet(
            "QPushButton { background: #6A2020; color: #FF9999; border-radius: 6px; padding: 7px 16px; }"
            "QPushButton:hover { background: #8A3030; }"
        )
        self._btn_stop.setVisible(False)
        self._btn_stop.clicked.connect(self._on_stop_bulk)
        layout.addWidget(self._btn_stop)

        self._btn_send = QPushButton("Отправить  ➤")
        self._btn_send.setObjectName("btnSend")
        self._btn_send.clicked.connect(self._on_send_bulk)
        layout.addWidget(self._btn_send)

        return row

    def _build_schedule_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            "QWidget { background: #13132A; border-radius: 6px; padding: 4px 8px; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self._chk_schedule = QCheckBox("Запланировать")
        self._chk_schedule.toggled.connect(self._on_schedule_toggled)
        layout.addWidget(self._chk_schedule)

        self._dt_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self._dt_edit.setDisplayFormat("dd.MM.yyyy  HH:mm")
        self._dt_edit.setCalendarPopup(True)
        self._dt_edit.setEnabled(False)
        self._dt_edit.setFixedWidth(160)
        layout.addWidget(self._dt_edit)

        self._schedule_lbl = QLabel("Рассылка не запланирована")
        self._schedule_lbl.setStyleSheet("color: #8888AA; font-size: 11px;")
        layout.addWidget(self._schedule_lbl)

        layout.addStretch()

        return bar

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = _panel()
        panel.setFixedWidth(280)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # stats header
        stats_hdr = QHBoxLayout()
        stats_hdr.addWidget(_panel_title("Статистика"))
        stats_hdr.addStretch()
        self._stats_period = QComboBox()
        self._stats_period.addItems(["Сегодня", "Неделя", "Месяц"])
        self._stats_period.setFixedWidth(90)
        stats_hdr.addWidget(self._stats_period)
        layout.addLayout(stats_hdr)

        # stat labels
        self._lbl_sent   = QLabel("0 ▲ успешно")
        self._lbl_errors = QLabel("0 ○ ошибок")
        self._lbl_sent.setStyleSheet("color: #6C63FF; font-size: 14px;")
        self._lbl_errors.setStyleSheet("color: #FF6B6B; font-size: 14px;")
        layout.addWidget(self._lbl_sent)
        layout.addWidget(self._lbl_errors)

        # sparkline chart
        self._chart = SimpleChart()
        layout.addWidget(self._chart)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #2A2A4A;")
        layout.addWidget(separator)

        # ── Лог отправки ──────────────────────────────────────────────────────
        log_hdr = QHBoxLayout()
        log_hdr.addWidget(_panel_title("Лог отправки"))
        log_hdr.addStretch()
        clear_log_btn = QPushButton("✕")
        clear_log_btn.setObjectName("iconBtn")
        clear_log_btn.setFixedSize(QSize(22, 22))
        clear_log_btn.setToolTip("Очистить лог")
        log_hdr.addWidget(clear_log_btn)
        layout.addLayout(log_hdr)

        from PySide6.QtWidgets import QTextEdit
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setStyleSheet(
            "QTextEdit {"
            "  background: #0B0F1E;"
            "  color: #CCCCDD;"
            "  font-family: Consolas, monospace;"
            "  font-size: 11px;"
            "  border: 1px solid #1E2A4A;"
            "  border-radius: 4px;"
            "}"
        )
        clear_log_btn.clicked.connect(self._log_view.clear)
        layout.addWidget(self._log_view, 1)

        return panel

    # ── Bottom status strip ───────────────────────────────────────────────────

    def _build_status_strip(self) -> QWidget:
        strip = QWidget()
        strip.setObjectName("statusStrip")
        strip.setFixedHeight(64)

        layout = QHBoxLayout(strip)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(16)

        cells_data = [
            ("Выбрано",        "selected"),
            ("Успешно",        "sent"),
            ("Не доставлено",  "failed"),
            ("Ошибок",         "errors"),
        ]

        self._stat_nums: dict[str, QLabel] = {}

        for label_text, key in cells_data:
            cell = QWidget()
            cell.setObjectName("statCell")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(10, 4, 10, 4)
            cell_layout.setSpacing(0)
            cell_layout.setAlignment(Qt.AlignCenter)

            num_lbl = QLabel("0")
            num_lbl.setObjectName("statNum")
            num_lbl.setAlignment(Qt.AlignCenter)

            desc_lbl = QLabel(label_text)
            desc_lbl.setObjectName("statLabel")
            desc_lbl.setAlignment(Qt.AlignCenter)

            cell_layout.addWidget(num_lbl)
            cell_layout.addWidget(desc_lbl)

            self._stat_nums[key] = num_lbl
            layout.addWidget(cell)

        layout.addStretch()

        # right side: current time
        self._clock_lbl = QLabel()
        self._clock_lbl.setStyleSheet("color: #555577; font-size: 11px;")
        layout.addWidget(self._clock_lbl)

        # update clock every 30s
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(30_000)
        self._tick_clock()

        return strip

    # ══════════════════════════════════════════════════════════════════════════
    #  Data loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_contacts(self) -> None:
        """Открывает проводник для выбора файла контактов (CSV или TXT)."""
        from PySide6.QtWidgets import QFileDialog
        import contact_manager as cm

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл контактов",
            "",
            "Файлы контактов (*.csv *.txt);;Все файлы (*)",
        )
        if not path:
            return  # пользователь закрыл диалог

        try:
            raw = cm.load_contacts(path)
            contacts = [
                {
                    "id": i,
                    "name": c.name or f"Контакт {i + 1}",
                    "phone": "+" + c.phone,
                    "source": "file",
                }
                for i, c in enumerate(raw)
            ]
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка загрузки", str(exc))
            return

        self._all_contacts = contacts
        self._populate_contact_list(contacts)
        self._populate_contacts_all_page(contacts)
        logger.info("Загружено %d контактов из %s", len(contacts), path)

    def _populate_contact_list(self, contacts: list[dict]) -> None:
        self._contact_list.blockSignals(True)
        self._contact_list.clear()

        for contact in contacts:
            label = f"{contact['name']}  {contact['phone']}" if contact.get("name") else contact["phone"]
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, contact)
            self._contact_list.addItem(item)

        self._contact_list.blockSignals(False)
        self._refresh_contact_header()

    def _populate_contacts_all_page(self, contacts: list[dict]) -> None:
        self._contacts_all_list.clear()
        for contact in contacts:
            label = f"{contact.get('name', '')}  {contact['phone']}".strip()
            item = QListWidgetItem(label)
            self._contacts_all_list.addItem(item)

    # ══════════════════════════════════════════════════════════════════════════
    #  Slots and event handlers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_contact_item_changed(self, _item: QListWidgetItem) -> None:
        self._refresh_contact_header()

    def _refresh_contact_header(self) -> None:
        selected = len(self._get_selected_contacts())
        total    = self._contact_list.count()
        self._contacts_header.setText(f"{selected} / {total} контактов выбрано")
        self._send_status_lbl.setText(f"Выбрано: {selected} контактов для рассылки")
        self.update_stats(selected, self._total_sent, self._total_failed, self._total_errors)

    def _get_selected_contacts(self) -> list[dict]:
        result = []
        for i in range(self._contact_list.count()):
            item = self._contact_list.item(i)
            if item and item.checkState() == Qt.Checked:
                data = item.data(Qt.UserRole)
                if data:
                    result.append(data)
        return result

    def _filter_contacts(self) -> None:
        query      = self._contact_search.text().lower()
        flt        = self._contact_filter.currentText()  # "Все" / "Из файла" / "Вручную"

        for i in range(self._contact_list.count()):
            item = self._contact_list.item(i)
            data = item.data(Qt.UserRole) or {}

            text_match = query in item.text().lower() if query else True

            if flt == "Из файла":
                src_match = data.get("source") == "file"
            elif flt == "Вручную":
                src_match = data.get("source") == "manual"
            else:
                src_match = True

            item.setHidden(not (text_match and src_match))

    def _on_check_all(self, state: int) -> None:
        check = Qt.Checked if state == Qt.Checked.value else Qt.Unchecked
        self._contact_list.blockSignals(True)
        for i in range(self._contact_list.count()):
            item = self._contact_list.item(i)
            if not item.isHidden():
                item.setCheckState(check)
        self._contact_list.blockSignals(False)
        self._refresh_contact_header()

    def _on_message_changed(self) -> None:
        text = self._message_edit.toPlainText()
        count = len(text)
        color = "#FF6B6B" if count > 500 else "#8888AA"
        self._char_counter.setText(f"{count}/500")
        self._char_counter.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._update_preview()

    def _update_preview(self) -> None:
        message = self._message_edit.toPlainText().strip() or "…"
        if self._chk_button.isChecked():
            btn_text = self._btn_text_edit.text().strip() or "Кнопка"
            message += f"\n\n[ 🔗 {btn_text} ]"
        self._bubble_lbl.setText(message)
        self._bubble_time.setText(datetime.now().strftime("%H:%M"))

    def _on_top_search(self, text: str) -> None:
        self._contact_search.setText(text)

    def _on_schedule_toggled(self, checked: bool) -> None:
        self._dt_edit.setEnabled(checked)
        if checked:
            dt = self._dt_edit.dateTime().toString("dd.MM.yyyy HH:mm")
            self._schedule_lbl.setText(f"Запланировано на {dt}")
        else:
            self._schedule_lbl.setText("Рассылка не запланирована")

    def _tick_clock(self) -> None:
        self._clock_lbl.setText(datetime.now().strftime("%d.%m.%Y  %H:%M"))

    # ── Add / delete contacts ─────────────────────────────────────────────────

    def _on_add_manual_contact(self) -> None:
        phone, ok = QInputDialog.getText(self, "Добавить контакт", "Номер телефона:")
        if not ok or not phone.strip():
            return
        name, _ = QInputDialog.getText(self, "Добавить контакт", "Имя (необязательно):")
        contact = {
            "id":     len(self._all_contacts) + 1,
            "name":   name.strip(),
            "phone":  phone.strip(),
            "source": "manual",
        }
        self._all_contacts.append(contact)
        label = f"{contact['name']}  {contact['phone']}" if contact["name"] else contact["phone"]
        item  = QListWidgetItem(label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setData(Qt.UserRole, contact)
        self._contact_list.addItem(item)
        self._populate_contacts_all_page(self._all_contacts)
        self._refresh_contact_header()

    # ── Templates ─────────────────────────────────────────────────────────────

    def _on_add_template_dialog(self) -> None:
        name, ok = QInputDialog.getText(self, "Новый шаблон", "Название шаблона:")
        if not ok or not name.strip():
            return
        text, ok2 = QInputDialog.getMultiLineText(self, "Новый шаблон", "Текст шаблона:")
        if not ok2:
            return
        self._add_template(name.strip(), text.strip())

    def _add_template(self, name: str, text: str) -> None:
        tpl = {"name": name, "text": text}
        self._templates.append(tpl)
        self._refresh_template_lists()

    def _refresh_template_lists(self) -> None:
        for lst in (self._templates_main_list,):
            lst.clear()
            for tpl in self._templates:
                preview = tpl["text"][:60].replace("\n", " ")
                item = QListWidgetItem()
                item.setText(f"{tpl['name']}\n{preview}…" if len(tpl["text"]) > 60 else f"{tpl['name']}\n{tpl['text']}")
                item.setData(Qt.UserRole, tpl)
                lst.addItem(item)

    def _apply_template_from_item(self, item: QListWidgetItem) -> None:
        tpl = item.data(Qt.UserRole)
        if tpl:
            self._message_edit.setPlainText(tpl.get("text", ""))
            self._switch_tab(1)

    def _on_save_template(self) -> None:
        text = self._message_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Шаблон", "Нет текста для сохранения.")
            return
        name, ok = QInputDialog.getText(self, "Сохранить шаблон", "Название шаблона:")
        if ok and name.strip():
            self._add_template(name.strip(), text)
            QMessageBox.information(self, "Шаблон", f"Шаблон «{name.strip()}» сохранён.")

    def _on_delete_template(self) -> None:
        row = self._templates_main_list.currentRow()
        if row < 0:
            return
        del self._templates[row]
        self._refresh_template_lists()

    # ── Reset ─────────────────────────────────────────────────────────────────

    def _on_reset(self) -> None:
        self._message_edit.clear()
        self._chk_schedule.setChecked(False)

    # ── Proxy dialog ──────────────────────────────────────────────────────────

    def _on_open_proxy(self) -> None:
        dlg = ProxyDialog(self._cfg, self)
        if dlg.exec():
            self._cfg = config_manager.load()

    def _on_button_toggled(self, enabled: bool) -> None:
        self._btn_fields.setVisible(enabled)
        self._update_preview()

    def _on_gpt_toggled(self, enabled: bool) -> None:
        """Сохраняет флаг enabled сразу при переключении чекбокса."""
        self._cfg.setdefault("gpt", {})
        self._cfg["gpt"]["enabled"] = enabled
        config_manager.save(self._cfg)

    def _on_open_gpt_settings(self) -> None:
        dlg = GptSettingsDialog(self._cfg, self)
        if dlg.exec():
            self._cfg = config_manager.load()
            # Синхронизируем чекбокс с сохранённым значением
            self._chk_gpt.setChecked(bool(self._cfg.get("gpt", {}).get("enabled", False)))

    # ── Send test ─────────────────────────────────────────────────────────────

    def _on_send_test(self) -> None:
        selected = self._get_selected_contacts()
        if not selected:
            QMessageBox.warning(self, "Отправить тест", "Выберите хотя бы один контакт из списка.")
            return
        phone = selected[0].get("phone", "").lstrip("+")
        text  = self._message_edit.toPlainText().strip()

        if not text:
            QMessageBox.warning(self, "Отправить тест", "Введите текст сообщения.")
            return

        proxy = config_manager.get_proxy_settings(self._cfg)

        self._test_worker = _TestWorker(phone, text, proxy)
        self._test_worker.finished.connect(self._on_test_done)
        self._test_worker.start()

    def _on_test_done(self, ok: bool, msg: str) -> None:
        if ok:
            QMessageBox.information(self, "Тестовое сообщение", msg)
        else:
            QMessageBox.warning(self, "Тестовое сообщение", msg)

    # ── Send bulk ─────────────────────────────────────────────────────────────

    def _on_send_bulk(self) -> None:
        contacts = self._get_selected_contacts()
        if not contacts:
            QMessageBox.warning(self, "Рассылка", "Не выбрано ни одного контакта.")
            return

        text = self._message_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Рассылка", "Введите текст сообщения.")
            return

        connected = self._account_manager.get_connected()
        if not connected:
            reply = QMessageBox.question(
                self,
                "Нет подключённых аккаунтов",
                "Нет подключённых аккаунтов WhatsApp.\n"
                "Перейти на вкладку «Аккаунты» и добавить?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._switch_tab(3)
            return

        confirm = QMessageBox.question(
            self,
            "Подтверждение рассылки",
            f"Отправить сообщение {len(contacts)} контактам\n"
            f"через {len(connected)} аккаунт(ов) WhatsApp?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        import threading
        url      = self._cfg.get("event_url", "")
        gpt_cfg  = self._cfg.get("gpt", {})
        # Синхронизируем enabled с текущим состоянием чекбокса
        gpt_cfg     = {**gpt_cfg, "enabled": self._chk_gpt.isChecked()}
        proxies     = config_manager.get_proxy_settings(self._cfg)
        gpt_proxies = _resolve_gpt_proxy(gpt_cfg, proxies)
        self._stop_event = threading.Event()

        btn_text = self._btn_text_edit.text().strip() if self._chk_button.isChecked() else ""
        btn_url  = self._btn_url_edit.text().strip()  if self._chk_button.isChecked() else ""

        self._bulk_worker = _SequentialBulkWorker(
            self._account_manager, contacts, text, url,
            self._stop_event, gpt_cfg=gpt_cfg, proxies=gpt_proxies,
            button_text=btn_text, button_url=btn_url,
        )
        self._bulk_worker.progress.connect(self._on_bulk_progress)
        self._bulk_worker.log_entry.connect(self._on_log_entry)
        self._bulk_worker.contact_sent.connect(self._on_contact_sent)
        self._bulk_worker.finished.connect(self._on_bulk_done)
        self._bulk_worker.start()

        self._btn_send.setEnabled(False)
        self._btn_stop.setVisible(True)
        self._send_status_lbl.setText(f"Отправка… 0 / {len(contacts)}")

    def _on_stop_bulk(self) -> None:
        if hasattr(self, "_stop_event"):
            self._stop_event.set()
        self._btn_stop.setEnabled(False)
        self._btn_stop.setText("⏹  Останавливаю…")

    def _on_bulk_progress(self, done: int, total: int, phone: str, sent: int, errors: int) -> None:
        self._send_status_lbl.setText(
            f"Отправка… {done} / {total}  |  последний: {phone}"
        )
        # Обновляем счётчики в реальном времени
        self._total_sent   = sent
        self._total_errors = errors
        self._lbl_sent.setText(f"{sent} ▲ успешно")
        self._lbl_errors.setText(f"{errors} ○ ошибок")
        self._chart.add_point(sent, errors)
        self.update_stats(self._contact_list.count(), sent, self._total_failed, errors)

    def _on_log_entry(self, label: str, ok: bool) -> None:
        from datetime import datetime
        ts    = datetime.now().strftime("%H:%M:%S")
        icon  = "✓" if ok else "✗"
        color = "#25A244" if ok else "#FF6666"
        self._log_view.append(
            f'<span style="color:#555577">{ts}</span> '
            f'<span style="color:{color}">{icon}</span> '
            f'<span style="color:#CCCCDD">{label}</span>'
        )
        # Автопрокрутка вниз
        sb = self._log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_contact_sent(self, index: int) -> None:
        """Удаляет отправленный контакт из списка (он переехал в history.csv)."""
        # Ищем по индексу в текущем видимом списке
        if index < self._contact_list.count():
            item = self._contact_list.item(index)
            if item:
                self._contact_list.takeItem(index)
        self._refresh_contact_header()

    def _on_bulk_done(self, sent: int, errors: int, stopped: bool) -> None:
        import history_manager

        # _total_sent/_total_errors уже обновлены по ходу через _on_bulk_progress
        self._btn_send.setEnabled(True)
        self._btn_stop.setVisible(False)
        self._btn_stop.setEnabled(True)
        self._btn_stop.setText("⏹  Остановить")

        selected = len(self._get_selected_contacts())
        self.update_stats(selected, self._total_sent, self._total_failed, self._total_errors)

        hist = history_manager.history_count()
        if stopped:
            remaining = self._contact_list.count()
            self._send_status_lbl.setText(
                f"Остановлено. Отправлено: {sent}, ошибок: {errors}. "
                f"Осталось в очереди: {remaining} → queue.csv"
            )
            QMessageBox.information(
                self, "Рассылка остановлена",
                f"Отправлено: {sent}\nОшибок: {errors}\n"
                f"Осталось в очереди: {remaining}\n\n"
                f"Остаток сохранён в queue.csv\n"
                f"История отправок: history.csv ({hist} записей)",
            )
        else:
            self._send_status_lbl.setText(f"Готово: {sent} отправлено, {errors} ошибок")
            QMessageBox.information(
                self, "Рассылка завершена",
                f"Отправлено: {sent}\nОшибок: {errors}\n\n"
                f"История отправок: history.csv ({hist} записей)",
            )

    # ══════════════════════════════════════════════════════════════════════════
    #  Stats strip update
    # ══════════════════════════════════════════════════════════════════════════

    def update_stats(self, selected: int, sent: int, failed: int, errors: int) -> None:
        """Update the four stat cells in the bottom strip."""
        self._stat_nums["selected"].setText(str(selected))
        self._stat_nums["sent"].setText(str(sent))
        self._stat_nums["failed"].setText(str(failed))
        self._stat_nums["errors"].setText(str(errors))
