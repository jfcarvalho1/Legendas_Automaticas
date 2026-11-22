#!/usr/bin/env python3
"""Media Organizer — ponto de entrada."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import APP_NAME, APP_VERSION, ensure_dirs  # noqa: E402
from core.database import Database, now_iso  # noqa: E402
from core.logger import setup_logging  # noqa: E402
from core.operations import OperationManager  # noqa: E402


def recover_interrupted(db: Database) -> None:
    """Tarefas e operações que ficaram a meio (ex.: o computador desligou-se)."""
    db.execute("UPDATE jobs SET status='interrupted', finished_at=? WHERE status='running'",
               (now_iso(),))
    OperationManager(db).cleanup_reserved()
    # cópias parciais nunca concluídas ficam assinaladas, não são apagadas
    for r in db.query("SELECT operation_id, new_path FROM operations WHERE status='pending' "
                      "AND operation!='reserved'"):
        db.execute("UPDATE operations SET status='failed', error='Interrompida' "
                   "WHERE operation_id=?", (r["operation_id"],))


def main() -> int:
    ensure_dirs()
    log = setup_logging()
    log.info("A iniciar %s %s", APP_NAME, APP_VERSION)
    db = Database()
    recover_interrupted(db)

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("O PySide6 não está instalado. Execute:  bash instalar.sh")
        return 1

    from interface.context import AppContext
    from interface.main_window import FirstRunDialog, MainWindow
    from interface.theme import STYLE

    if sys.platform.startswith("win"):
        # ícone próprio na barra de tarefas do Windows
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MediaOrganizer.App")
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName("media-organizer")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    ctx = AppContext(db)
    win = MainWindow(ctx)
    win.show()
    if not db.get_setting("first_run_done"):
        dlg = FirstRunDialog(ctx, win)
        dlg.exec()
        win.pages["settings"].load()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
