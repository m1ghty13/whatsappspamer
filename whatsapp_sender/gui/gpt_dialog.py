"""
Диалог настроек ChatGPT-вариаций.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QDoubleSpinBox,
    QPushButton, QDialogButtonBox, QMessageBox,
    QRadioButton, QButtonGroup, QWidget, QGroupBox,
)

import config_manager

logger = logging.getLogger(__name__)

_MODELS = [
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-3.5-turbo",
]

# proxy_mode values
_PROXY_NONE   = "none"
_PROXY_SYSTEM = "system"
_PROXY_CUSTOM = "custom"


class _TestGptWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, api_key: str, model: str, temperature: float, proxy_url: str | None):
        super().__init__()
        self._api_key     = api_key
        self._model       = model
        self._temperature = temperature
        self._proxy_url   = proxy_url   # одна строка вида "socks5://..." или None

    def run(self) -> None:
        try:
            from gpt_text_variator import generate_variant
            proxies = {"https": self._proxy_url, "http": self._proxy_url} if self._proxy_url else None
            sample  = "Добро пожаловать на наше мероприятие 15 мая в 18:00!"
            result  = generate_variant(
                sample,
                api_key=self._api_key,
                model=self._model,
                temperature=self._temperature,
                proxies=proxies,
                timeout=20,
            )
            if result == sample:
                self.finished.emit(
                    False,
                    "Не удалось получить ответ от ChatGPT.\n\n"
                    "Возможные причины:\n"
                    "• api.openai.com заблокирован у вашего провайдера\n"
                    "• Неверный API-ключ\n"
                    "• Попробуйте указать прокси/VPN который может достучаться до OpenAI",
                )
            else:
                self.finished.emit(True, f"Соединение установлено!\n\nПример:\n{result}")
        except Exception as exc:
            self.finished.emit(False, f"Ошибка: {exc}")


class GptSettingsDialog(QDialog):

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки ChatGPT")
        self.setMinimumWidth(460)
        self.setModal(True)

        self._cfg     = cfg
        self._gpt_cfg = cfg.get("gpt", {})
        self._test_worker: _TestGptWorker | None = None

        self._build_ui()
        self._load_values()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc = QLabel(
            "Перед отправкой каждого сообщения ChatGPT слегка переформулирует текст.\n"
            "Ссылки, числа и смысл остаются без изменений."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8888AA; font-size: 12px;")
        layout.addWidget(desc)

        # ── Основные параметры ────────────────────────────────────────────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("sk-proj-...")
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setMinimumWidth(260)

        key_row = QHBoxLayout()
        key_row.addWidget(self._key_edit, 1)
        show_btn = QPushButton("👁")
        show_btn.setFixedSize(28, 28)
        show_btn.setCheckable(True)
        show_btn.toggled.connect(
            lambda on: self._key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        key_row.addWidget(show_btn)
        form.addRow("API-ключ:", _wrap(key_row))

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItems(_MODELS)
        form.addRow("Модель:", self._model_combo)

        self._temp_spin = QDoubleSpinBox()
        self._temp_spin.setRange(0.0, 1.0)
        self._temp_spin.setSingleStep(0.05)
        self._temp_spin.setDecimals(2)
        self._temp_spin.setFixedWidth(80)
        hint = QLabel("(0.0 = точнее, 1.0 = разнообразнее; рекомендуется 0.2–0.4)")
        hint.setStyleSheet("color: #8888AA; font-size: 11px;")
        t_row = QHBoxLayout()
        t_row.addWidget(self._temp_spin)
        t_row.addWidget(hint)
        t_row.addStretch()
        form.addRow("Temperature:", _wrap(t_row))

        layout.addLayout(form)

        # ── Прокси для GPT ────────────────────────────────────────────────────
        proxy_box = QGroupBox("Прокси для запросов ChatGPT")
        proxy_box.setStyleSheet(
            "QGroupBox { color: #AAAACC; font-size: 12px; border: 1px solid #2A2A4A;"
            " border-radius: 4px; margin-top: 6px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        pb_layout = QVBoxLayout(proxy_box)
        pb_layout.setSpacing(6)

        self._proxy_group = QButtonGroup(self)

        self._rb_none   = QRadioButton("Не использовать прокси (прямое подключение)")
        self._rb_system = QRadioButton("Использовать системный прокси (из настроек приложения)")
        self._rb_custom = QRadioButton("Свой прокси для GPT:")
        for rb in (self._rb_none, self._rb_system, self._rb_custom):
            rb.setStyleSheet("color: #CCCCDD; font-size: 12px;")
            self._proxy_group.addButton(rb)
            pb_layout.addWidget(rb)

        self._custom_proxy_edit = QLineEdit()
        self._custom_proxy_edit.setPlaceholderText(
            "http://221.127.134.8:8888  или  socks5://host:port"
        )
        self._custom_proxy_edit.setEnabled(False)
        pb_layout.addWidget(self._custom_proxy_edit)

        proxy_note = QLabel(
            "Если api.openai.com заблокирован провайдером — укажите прокси/VPN.\n"
            "Поддерживаются http://, https://, socks5://"
        )
        proxy_note.setStyleSheet("color: #666688; font-size: 11px;")
        proxy_note.setWordWrap(True)
        pb_layout.addWidget(proxy_note)

        self._rb_custom.toggled.connect(self._custom_proxy_edit.setEnabled)

        layout.addWidget(proxy_box)

        # ── Тест ─────────────────────────────────────────────────────────────
        self._test_btn = QPushButton("Проверить соединение")
        self._test_btn.clicked.connect(self._on_test)
        layout.addWidget(self._test_btn)

        self._test_result_lbl = QLabel("")
        self._test_result_lbl.setWordWrap(True)
        self._test_result_lbl.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._test_result_lbl)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Load / save ───────────────────────────────────────────────────────────

    def _load_values(self) -> None:
        self._key_edit.setText(self._gpt_cfg.get("api_key", ""))

        model = self._gpt_cfg.get("model", "gpt-4.1-mini")
        idx   = self._model_combo.findText(model)
        self._model_combo.setCurrentIndex(idx if idx >= 0 else 0)
        if idx < 0:
            self._model_combo.setCurrentText(model)

        self._temp_spin.setValue(float(self._gpt_cfg.get("temperature", 0.3)))

        mode = self._gpt_cfg.get("proxy_mode", _PROXY_NONE)
        if mode == _PROXY_SYSTEM:
            self._rb_system.setChecked(True)
        elif mode == _PROXY_CUSTOM:
            self._rb_custom.setChecked(True)
        else:
            self._rb_none.setChecked(True)

        self._custom_proxy_edit.setText(self._gpt_cfg.get("custom_proxy", ""))

    def _on_save(self) -> None:
        self._cfg.setdefault("gpt", {})
        self._cfg["gpt"]["api_key"]      = self._key_edit.text().strip()
        self._cfg["gpt"]["model"]        = self._model_combo.currentText().strip()
        self._cfg["gpt"]["temperature"]  = round(self._temp_spin.value(), 2)
        self._cfg["gpt"]["proxy_mode"]   = self._current_proxy_mode()
        self._cfg["gpt"]["custom_proxy"] = self._custom_proxy_edit.text().strip()
        config_manager.save(self._cfg)
        self.accept()

    # ── Test ──────────────────────────────────────────────────────────────────

    def _on_test(self) -> None:
        key = self._key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Тест GPT", "Введите API-ключ.")
            return

        self._test_btn.setEnabled(False)
        self._test_result_lbl.setStyleSheet("color: #8888AA; font-size: 11px;")
        self._test_result_lbl.setText("Проверяю соединение…")

        self._test_worker = _TestGptWorker(
            api_key=key,
            model=self._model_combo.currentText().strip(),
            temperature=self._temp_spin.value(),
            proxy_url=self._resolve_proxy_url(),
        )
        self._test_worker.finished.connect(self._on_test_done)
        self._test_worker.start()

    def _on_test_done(self, ok: bool, msg: str) -> None:
        self._test_btn.setEnabled(True)
        color = "#25A244" if ok else "#FF6666"
        self._test_result_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._test_result_lbl.setText(msg)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _current_proxy_mode(self) -> str:
        if self._rb_system.isChecked():
            return _PROXY_SYSTEM
        if self._rb_custom.isChecked():
            return _PROXY_CUSTOM
        return _PROXY_NONE

    def _resolve_proxy_url(self) -> str | None:
        """Возвращает строку прокси-URL или None."""
        mode = self._current_proxy_mode()
        if mode == _PROXY_NONE:
            return None
        if mode == _PROXY_CUSTOM:
            url = self._custom_proxy_edit.text().strip()
            return url or None
        # system
        sys_proxies = config_manager.get_proxy_settings(self._cfg)
        if sys_proxies:
            return sys_proxies.get("https") or sys_proxies.get("http")
        return None


def _wrap(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w
