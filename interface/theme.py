"""Tema visual escuro (Qt Style Sheet)."""

BG = "#0f141a"
SURFACE = "#161e27"
SURFACE_2 = "#1c2632"
BORDER = "#253242"
TEXT = "#e6edf3"
MUTED = "#8b98a5"
ACCENT = "#3fb6a8"
ACCENT_2 = "#4f8cff"
WARN = "#e3a33b"
DANGER = "#e5534b"
OK = "#46c37b"

STYLE = f"""
* {{ font-size: 10pt; color: {TEXT}; }}
QMainWindow, QWidget#Page, QStackedWidget {{ background: {BG}; }}
QWidget {{ background: transparent; }}
QDialog {{ background: {BG}; }}

/* barra lateral */
QFrame#Sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
QLabel#Brand {{ font-size: 15pt; font-weight: 700; padding: 18px 18px 2px 18px; }}
QLabel#BrandSub {{ color: {MUTED}; font-size: 9pt; padding: 0 18px 14px 18px; }}
QPushButton#NavButton {{
    text-align: left; padding: 10px 18px; margin: 1px 10px; border: none;
    border-radius: 8px; color: {MUTED}; font-size: 10.5pt;
}}
QPushButton#NavButton:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#NavButton:checked {{ background: {SURFACE_2}; color: {TEXT};
    border-left: 3px solid {ACCENT}; font-weight: 600; }}
QLabel#SidebarFooter {{ color: {MUTED}; font-size: 8.5pt; padding: 12px 18px; }}

/* cabeçalhos de página */
QLabel#PageTitle {{ font-size: 20pt; font-weight: 700; }}
QLabel#PageSubtitle {{ color: {MUTED}; }}
QLabel#SectionTitle {{ font-size: 12pt; font-weight: 600; padding-top: 6px; }}
QLabel#Muted {{ color: {MUTED}; }}

/* cartões */
QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#Card:hover {{ border: 1px solid {ACCENT}; }}
QFrame#Panel {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#CardValue {{ font-size: 22pt; font-weight: 700; }}
QLabel#CardLabel {{ color: {MUTED}; font-size: 9.5pt; }}
QLabel#CardHint {{ color: {MUTED}; font-size: 8.5pt; }}

/* botões */
QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {SURFACE_2}; }}
QPushButton#Primary {{ background: {ACCENT}; color: #06201c; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: #52c9bb; }}
QPushButton#Primary:disabled {{ background: {SURFACE_2}; color: {MUTED}; }}
QPushButton#Danger {{ color: {DANGER}; }}

/* campos */
QLineEdit, QComboBox, QSpinBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 7px 10px; selection-background-color: {ACCENT_2};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_2}; }}
QCheckBox {{ spacing: 8px; padding: 3px 0; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px;
    border: 1px solid {BORDER}; background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox:disabled {{ color: {MUTED}; }}

/* tabelas */
QTableView, QTreeView, QListWidget {{
    background: {SURFACE}; alternate-background-color: #18212b;
    border: 1px solid {BORDER}; border-radius: 10px; gridline-color: {BORDER};
    selection-background-color: #24425c; selection-color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_2}; color: {MUTED}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 7px 8px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE_2}; border: none; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 16px;
    border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

QProgressBar {{ background: {SURFACE_2}; border: none; border-radius: 5px; height: 10px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollArea {{ border: none; }}

QStatusBar {{ background: {SURFACE}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: #24425c; }}
QMessageBox {{ background: {BG}; }}
"""
