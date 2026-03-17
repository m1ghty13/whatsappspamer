"""
Диалог настройки прокси.
"""

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QMessageBox, QCheckBox,
)

import config_manager


# ── Фоновый поток для теста прокси ───────────────────────────────────────────

class _ProxyTester(QThread):
    done = Signal(bool, str)   # (success, message)

    def __init__(self, proxy_dict: dict):
        super().__init__()
        self._proxy = proxy_dict

    def run(self):
        try:
            resp = requests.get(
                "https://httpbin.org/ip",
                proxies=self._proxy,
                timeout=8,
            )
            ip = resp.json().get("origin", "?")
            self.done.emit(True, f"Успешно. Внешний IP: {ip}")
        except Exception as e:
            self.done.emit(False, f"Ошибка: {e}")


# ── Диалог ────────────────────────────────────────────────────────────────────

class ProxyDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки прокси")
        self.setMinimumWidth(380)
        self.setModal(True)
        self._cfg = cfg
        self._tester: _ProxyTester | None = None
        self._build_ui()
        self._load_values()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(14)

        self._enabled = QCheckBox("Использовать прокси")
        root.addWidget(self._enabled)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        self._type = QComboBox()
        self._type.addItems(["HTTP", "SOCKS5"])
        self._host = QLineEdit(); self._host.setPlaceholderText("192.168.1.1")
        self._port = QLineEdit(); self._port.setPlaceholderText("8080")
        self._login = QLineEdit(); self._login.setPlaceholderText("необязательно")
        self._pwd = QLineEdit()
        self._pwd.setEchoMode(QLineEdit.Password)
        self._pwd.setPlaceholderText("необязательно")

        form.addRow("Тип:", self._type)
        form.addRow("Хост:", self._host)
        form.addRow("Порт:", self._port)
        form.addRow("Логин:", self._login)
        form.addRow("Пароль:", self._pwd)
        root.addLayout(form)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        btns = QHBoxLayout()
        self._btn_test = QPushButton("Тестировать")
        btn_save = QPushButton("Сохранить")
        btn_save.setObjectName("btnSend")
        self._btn_test.clicked.connect(self._on_test)
        btn_save.clicked.connect(self._on_save)
        btns.addWidget(self._btn_test)
        btns.addStretch()
        btns.addWidget(btn_save)
        root.addLayout(btns)

        self._enabled.toggled.connect(self._toggle_fields)

    # ── Загрузка / сохранение ─────────────────────────────────────────────────

    def _load_values(self):
        p = self._cfg.get("proxy", {})
        self._enabled.setChecked(bool(p.get("enabled")))
        idx = self._type.findText(p.get("type", "HTTP"))
        if idx >= 0:
            self._type.setCurrentIndex(idx)
        self._host.setText(p.get("host", ""))
        self._port.setText(str(p.get("port", "")))
        self._login.setText(p.get("login", ""))
        self._pwd.setText(p.get("password", ""))
        self._toggle_fields(self._enabled.isChecked())

    def _toggle_fields(self, enabled: bool):
        for w in (self._type, self._host, self._port, self._login, self._pwd):
            w.setEnabled(enabled)

    def _collect(self) -> dict:
        return {
            "enabled": self._enabled.isChecked(),
            "type":     self._type.currentText(),
            "host":     self._host.text().strip(),
            "port":     self._port.text().strip(),
            "login":    self._login.text().strip(),
            "password": self._pwd.text(),
        }

    def _on_save(self):
        self._cfg["proxy"] = self._collect()
        config_manager.save(self._cfg)
        self.accept()

    # ── Тест прокси ──────────────────────────────────────────────────────────

    def _on_test(self):
        proxy_dict = config_manager.get_proxy_settings(
            {"proxy": {**self._collect(), "enabled": True}}
        )
        if not proxy_dict:
            self._status.setText("Заполните хост и порт.")
            return

        self._btn_test.setEnabled(False)
        self._status.setText("Проверяю...")
        self._tester = _ProxyTester(proxy_dict)
        self._tester.done.connect(self._on_test_done)
        self._tester.start()

    def _on_test_done(self, ok: bool, msg: str):
        self._btn_test.setEnabled(True)
        color = "#25A244" if ok else "#FF6666"
        self._status.setStyleSheet(f"color: {color};")
        self._status.setText(msg)
