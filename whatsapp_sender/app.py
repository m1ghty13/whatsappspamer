"""
Entry point for ОАЭ — WhatsApp Sender.

Usage:
    python app.py

Requirements:
    pip install PySide6 requests python-dotenv neonize
"""

import sys
import os

# Ensure the package root is on the path so that
# 'import config_manager' and 'from gui.xxx import ...' work correctly
# when the script is launched from any working directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from gui.main_window import MainWindow
from gui.styles import DARK_QSS


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    app.setApplicationName("Xivora WhatsApp Sender")
    app.setOrganizationName("Xivora Software")

    # Optional: set a window icon if one is available
    icon_path = os.path.join(_HERE, "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
