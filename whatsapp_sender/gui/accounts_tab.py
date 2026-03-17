"""
Вкладка «Аккаунты» — управление множественными WhatsApp-сессиями.

Каждая строка в списке = один аккаунт. Цветной индикатор статуса:
  🟢 connected  🟡 connecting  🔴 disconnected/error
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject, QSize
from PySide6.QtGui import QColor, QPainter, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QFrame, QSizePolicy,
)

from account_manager import AccountManager, AccountStatus, AccountInfo
import config_manager

logger = logging.getLogger(__name__)


# ── Qt-мост: безопасная передача событий из фоновых потоков в GUI ─────────────

class _AccountSignals(QObject):
    qr_received    = Signal(str, bytes)          # (account_id, qr_bytes)
    status_changed = Signal(str, str, str)       # (account_id, status_value, phone)


# ── Виджет одной строки аккаунта ─────────────────────────────────────────────

class _AccountRow(QWidget):
    remove_requested = Signal(str)   # account_id

    _STATUS_COLORS = {
        AccountStatus.CONNECTED:    "#25A244",
        AccountStatus.CONNECTING:   "#F0A500",
        AccountStatus.DISCONNECTED: "#FF6666",
        AccountStatus.ERROR:        "#FF6666",
    }

    def __init__(self, info: AccountInfo, parent=None):
        super().__init__(parent)
        self._info = info
        self.setFixedHeight(56)
        self.setObjectName("panel")
        self._build()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)

        # Цветная точка-индикатор
        self._dot = QLabel("●")
        self._dot.setFixedWidth(16)
        row.addWidget(self._dot)

        # Название аккаунта + номер телефона
        col = QVBoxLayout()
        col.setSpacing(1)
        self._lbl_id = QLabel(self._info.account_id)
        self._lbl_id.setStyleSheet("font-weight: bold; color: #E0E0E0;")
        self._lbl_phone = QLabel(self._info.phone or "ожидает авторизации…")
        self._lbl_phone.setStyleSheet("font-size: 11px; color: #8888AA;")
        col.addWidget(self._lbl_id)
        col.addWidget(self._lbl_phone)
        row.addLayout(col, 1)

        # Счётчики
        self._lbl_stats = QLabel("✓ 0  ✗ 0")
        self._lbl_stats.setStyleSheet("color: #8888AA; font-size: 11px;")
        row.addWidget(self._lbl_stats)

        # Кнопка удалить
        del_btn = QPushButton("✕")
        del_btn.setObjectName("iconBtn")
        del_btn.setFixedSize(QSize(28, 28))
        del_btn.setToolTip("Удалить аккаунт")
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self._info.account_id))
        row.addWidget(del_btn)

        self._refresh_status()

    def update_status(self, status: AccountStatus, phone: str):
        self._info.status = status
        if phone:
            self._info.phone = phone
        self._refresh_status()

    def update_stats(self):
        self._lbl_stats.setText(f"✓ {self._info.sent_count}  ✗ {self._info.error_count}")

    def _refresh_status(self):
        color = self._STATUS_COLORS.get(self._info.status, "#8888AA")
        self._dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        self._lbl_phone.setText(self._info.phone or _STATUS_LABELS.get(self._info.status, "…"))


_STATUS_LABELS = {
    AccountStatus.CONNECTING:    "подключение… (отсканируй QR)",
    AccountStatus.CONNECTED:     "подключён",
    AccountStatus.DISCONNECTED:  "отключён",
    AccountStatus.ERROR:         "ошибка подключения",
}


# ── Основной виджет вкладки ───────────────────────────────────────────────────

class AccountsTab(QWidget):
    """
    Вкладка управления аккаунтами WhatsApp.
    Подключается к AccountManager через Qt-сигналы (thread-safe).
    """

    accounts_changed = Signal()   # кол-во подключённых аккаунтов изменилось

    def __init__(self, manager: AccountManager, cfg: dict, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._cfg     = cfg
        self._rows: dict[str, _AccountRow] = {}   # account_id -> row widget

        # Применяем сохранённый автопрофиль к менеджеру сразу при старте
        self._sync_auto_profile()

        self._signals = _AccountSignals()
        self._signals.qr_received.connect(self._on_qr_gui)
        self._signals.status_changed.connect(self._on_status_gui)

        # Прокидываем коллбэки из AccountManager в Qt-сигналы
        self._manager.on_qr     = lambda aid, data: self._signals.qr_received.emit(aid, data)
        self._manager.on_status = lambda aid, st, ph: self._signals.status_changed.emit(aid, st.value, ph)

        self._build_ui()
        self._refresh_list()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Заголовок + кнопки
        header = QHBoxLayout()
        title = QLabel("Аккаунты WhatsApp")
        title.setObjectName("panelTitle")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #FFFFFF;")
        header.addWidget(title)
        header.addStretch()

        profile_btn = QPushButton("⚙ Профиль")
        profile_btn.setObjectName("iconBtn")
        profile_btn.setFixedHeight(32)
        profile_btn.setToolTip("Настроить автоматическое имя и фото профиля для новых аккаунтов")
        profile_btn.clicked.connect(self._on_profile_settings)
        header.addWidget(profile_btn)

        add_btn = QPushButton("+ Добавить аккаунт")
        add_btn.setObjectName("btnSend")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._on_add)
        header.addWidget(add_btn)
        root.addLayout(header)

        # Описание
        hint = QLabel(
            "Каждый аккаунт работает в своём потоке. "
            "При добавлении откроется QR-код для сканирования.\n"
            "Рассылка автоматически распределяется по всем подключённым аккаунтам."
        )
        hint.setStyleSheet("color: #8888AA; font-size: 12px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Разделитель
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #2A2A4A;")
        root.addWidget(line)

        # Список аккаунтов (вертикальная прокрутка)
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        self._rows_layout.addStretch()

        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidget(self._rows_container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        # Нижняя строка статистики
        self._lbl_summary = QLabel("Нет подключённых аккаунтов")
        self._lbl_summary.setStyleSheet("color: #8888AA; font-size: 12px;")
        root.addWidget(self._lbl_summary)

    # ── Управление строками ───────────────────────────────────────────────────

    def _refresh_list(self):
        """Синхронизирует виджеты с текущим состоянием AccountManager."""
        for info in self._manager.get_all():
            if info.account_id not in self._rows:
                self._add_row(info)
        self._update_summary()

    def _add_row(self, info: AccountInfo):
        row = _AccountRow(info)
        row.remove_requested.connect(self._on_remove)
        # Вставляем перед stretch
        idx = self._rows_layout.count() - 1
        self._rows_layout.insertWidget(idx, row)
        self._rows[info.account_id] = row

    def _remove_row(self, account_id: str):
        row = self._rows.pop(account_id, None)
        if row:
            self._rows_layout.removeWidget(row)
            row.deleteLater()

    def _update_summary(self):
        connected = sum(
            1 for t in self._manager.get_all()
            if t.status == AccountStatus.CONNECTED
        )
        total = len(self._manager.get_all())
        self._lbl_summary.setText(
            f"Всего аккаунтов: {total}   •   Подключено: {connected}"
        )
        self.accounts_changed.emit()

    # ── Обработчики ──────────────────────────────────────────────────────────

    def _sync_auto_profile(self):
        """Передаёт auto_profile из конфига в AccountManager."""
        self._manager.auto_profile = self._cfg.get("auto_profile", {})

    def _on_profile_settings(self):
        from gui.profile_dialog import ProfileDialog
        dlg = ProfileDialog(self._cfg, self)
        if dlg.exec():
            self._cfg = config_manager.load()
            self._sync_auto_profile()

    def _on_add(self):
        account_id = self._manager.add_account()
        infos = {i.account_id: i for i in self._manager.get_all()}
        if account_id in infos:
            self._add_row(infos[account_id])
        self._update_summary()

    def _on_remove(self, account_id: str):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Удалить аккаунт",
            f"Удалить аккаунт {account_id}?\nСессия будет удалена.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._manager.remove_account(account_id)
            self._remove_row(account_id)
            self._update_summary()

    def _on_qr_gui(self, account_id: str, _data: bytes):
        """Вызывается в GUI-потоке когда QR готов."""
        row = self._rows.get(account_id)
        if row:
            row.update_status(AccountStatus.CONNECTING, "")
        logger.info("QR для %s открыт автоматически.", account_id)

    def _on_status_gui(self, account_id: str, status_value: str, phone: str):
        """Вызывается в GUI-потоке при смене статуса аккаунта."""
        status = AccountStatus(status_value)
        row = self._rows.get(account_id)
        if row:
            row.update_status(status, phone)
        self._update_summary()
