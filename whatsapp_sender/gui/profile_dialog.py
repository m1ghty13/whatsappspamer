"""
Диалог настройки автопрофиля WhatsApp.

Открывается кнопкой «⚙ Профиль» на вкладке Аккаунты.
Настройки сохраняются в config.json → "auto_profile".
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QFrame, QDialogButtonBox,
)

import config_manager


class ProfileDialog(QDialog):
    """Диалог настройки имени и фото профиля WhatsApp."""

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._photo_path = cfg.get("auto_profile", {}).get("photo_path", "")
        self.setWindowTitle("Настройки профиля")
        self.setMinimumWidth(380)
        self.setModal(True)
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(20, 20, 20, 20)

        # Описание
        hint = QLabel(
            "После подключения каждого аккаунта будут автоматически\n"
            "установлены имя и фото профиля WhatsApp."
        )
        hint.setStyleSheet("color: #8888AA; font-size: 12px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #2A2A4A;")
        root.addWidget(line)

        # Имя
        root.addWidget(QLabel("Имя профиля:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Например: Анна | Emaar Events")
        root.addWidget(self._name_edit)

        # Фото
        root.addWidget(QLabel("Фото профиля:"))
        photo_row = QHBoxLayout()
        photo_row.setSpacing(8)

        self._photo_preview = QLabel()
        self._photo_preview.setFixedSize(64, 64)
        self._photo_preview.setAlignment(Qt.AlignCenter)
        self._photo_preview.setStyleSheet(
            "border: 1px solid #2A2A4A; border-radius: 32px; background: #1A1A2E; color: #555;"
        )
        self._photo_preview.setText("нет")
        photo_row.addWidget(self._photo_preview)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        self._photo_lbl = QLabel("Файл не выбран")
        self._photo_lbl.setStyleSheet("color: #8888AA; font-size: 11px;")
        self._photo_lbl.setWordWrap(True)
        btn_col.addWidget(self._photo_lbl)

        pick_btn = QPushButton("Выбрать изображение…")
        pick_btn.setFixedHeight(30)
        pick_btn.clicked.connect(self._on_pick_photo)
        btn_col.addWidget(pick_btn)

        clear_btn = QPushButton("Очистить")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._on_clear_photo)
        btn_col.addWidget(clear_btn)

        photo_row.addLayout(btn_col, 1)
        root.addLayout(photo_row)

        # Кнопки
        root.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("Сохранить")
        btns.button(QDialogButtonBox.Cancel).setText("Отмена")
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _load(self):
        profile = self._cfg.get("auto_profile", {})
        self._name_edit.setText(profile.get("name", ""))
        self._set_photo_path(profile.get("photo_path", ""))

    def _set_photo_path(self, path: str):
        self._photo_path = path
        if path and Path(path).is_file():
            px = QPixmap(path).scaled(64, 64, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self._photo_preview.setPixmap(px)
            self._photo_lbl.setText(Path(path).name)
        else:
            self._photo_preview.setText("нет")
            self._photo_preview.setPixmap(QPixmap())
            self._photo_lbl.setText("Файл не выбран")

    def _on_pick_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите фото профиля", "",
            "Изображения (*.jpg *.jpeg *.png *.webp)"
        )
        if path:
            self._set_photo_path(path)

    def _on_clear_photo(self):
        self._set_photo_path("")

    def _on_save(self):
        self._cfg.setdefault("auto_profile", {})
        self._cfg["auto_profile"]["name"]       = self._name_edit.text().strip()
        self._cfg["auto_profile"]["photo_path"] = self._photo_path
        config_manager.save(self._cfg)
        self.accept()
