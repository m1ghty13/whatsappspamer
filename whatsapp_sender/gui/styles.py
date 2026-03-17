DARK_QSS = """
/* ── Global ──────────────────────────────────────────────── */
* {
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
    color: #E0E0E0;
}
QMainWindow, QDialog, QWidget {
    background-color: #1A1A2E;
}

/* ── TopBar ──────────────────────────────────────────────── */
#topBar {
    background-color: #10101E;
    border-bottom: 1px solid #2A2A4A;
}
#appTitle {
    font-size: 15px;
    font-weight: bold;
    color: #FFFFFF;
    padding-left: 8px;
}
#iconBtn {
    background: transparent;
    border: none;
    color: #8888AA;
    font-size: 16px;
    padding: 6px 8px;
    border-radius: 6px;
}
#iconBtn:hover { background: #2A2A4A; color: #FFFFFF; }

/* ── Tabs ────────────────────────────────────────────────── */
QTabWidget::pane {
    border: none;
    background: #1A1A2E;
}
QTabBar::tab {
    background: #10101E;
    color: #8888AA;
    padding: 8px 20px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #FFFFFF;
    border-bottom: 2px solid #6C63FF;
    background: #1A1A2E;
}
QTabBar::tab:hover { color: #CCCCFF; background: #1E1E3A; }

/* ── Panels ──────────────────────────────────────────────── */
#panel {
    background-color: #16213E;
    border-radius: 8px;
}
#panelTitle {
    font-size: 13px;
    font-weight: bold;
    color: #CCCCFF;
    padding: 4px 0;
}

/* ── Inputs ──────────────────────────────────────────────── */
QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background: #0F3460;
    border: 1px solid #2A2A6A;
    border-radius: 6px;
    padding: 6px 8px;
    color: #E0E0E0;
    selection-background-color: #6C63FF;
}
QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #6C63FF;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { color: #8888AA; }
QComboBox QAbstractItemView {
    background: #0F3460;
    border: 1px solid #2A2A6A;
    selection-background-color: #6C63FF;
}

/* ── Buttons ─────────────────────────────────────────────── */
QPushButton {
    background: #2A2A5A;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    color: #CCCCEE;
}
QPushButton:hover { background: #3A3A7A; }
QPushButton:pressed { background: #1A1A4A; }

#btnSend {
    background: #25A244;
    color: #FFFFFF;
    font-weight: bold;
    padding: 8px 24px;
}
#btnSend:hover { background: #2DC653; }
#btnSend:pressed { background: #1A8035; }

#btnReset {
    background: #4A2A2A;
    color: #FF9999;
}
#btnReset:hover { background: #6A3A3A; }

/* ── List ────────────────────────────────────────────────── */
QListWidget {
    background: #0F3460;
    border: 1px solid #2A2A6A;
    border-radius: 6px;
    outline: none;
}
QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QListWidget::item:selected { background: #3A3A7A; }
QListWidget::item:hover { background: #1E3A6E; }
QCheckBox { spacing: 6px; color: #CCCCEE; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #4A4A8A;
    border-radius: 3px;
    background: #0F3460;
}
QCheckBox::indicator:checked {
    background: #6C63FF;
    border-color: #6C63FF;
}

/* ── ScrollBar ───────────────────────────────────────────── */
QScrollBar:vertical {
    background: #10101E; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #3A3A7A; border-radius: 4px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Status bar ──────────────────────────────────────────── */
#statusStrip {
    background: #10101E;
    border-top: 1px solid #2A2A4A;
    padding: 4px 12px;
}
#statCell {
    background: #16213E;
    border-radius: 6px;
    padding: 6px 14px;
}
#statNum  { font-size: 20px; font-weight: bold; color: #FFFFFF; }
#statLabel { font-size: 11px; color: #8888AA; }

/* ── Preview (phone bubble) ──────────────────────────────── */
#previewPanel {
    background: #0D0D1A;
    border: 1px solid #2A2A4A;
    border-radius: 10px;
}
#bubble {
    background: #1A3A2A;
    border-radius: 12px;
    border-bottom-left-radius: 2px;
    padding: 10px 14px;
    color: #E8FFE8;
}

/* ── Splitter ────────────────────────────────────────────── */
QSplitter::handle { background: #2A2A4A; width: 1px; }
"""
