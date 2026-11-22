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


def run_headless(argv: list[str]) -> int:
    """app.py --auto [--mode analise|automatico|reparacao|recuperacao] — usado pelo agendamento."""
    from core.automation import MODES, Automation, Busy
    mode = "automatico"
    if "--mode" in argv:
        i = argv.index("--mode")
        if i + 1 < len(argv):
            mode = argv[i + 1]
    if mode not in MODES:
        print(f"Modo inválido: {mode}. Use: {', '.join(MODES)}")
        return 2
    db = Database()
    recover_interrupted(db)
    try:
        Automation(db, log_fn=lambda m: setup_logging().info(m)).run(mode)
    except Busy as e:
        setup_logging().warning(str(e))
        return 1
    return 0


def run_check() -> int:
    """app.py --check — usado no fim da instalação: confirma que tudo carrega."""
    import importlib
    ok = True
    print(f"{APP_NAME} {APP_VERSION} — verificação")
    for mod in ("PySide6.QtWidgets", "mutagen", "core.database", "core.scanner", "core.organizer",
                "core.automation", "core.duplicates", "movies.subtitles", "movies.translation",
                "movies.metadata", "music.organizer", "integrations.tmdb",
                "integrations.opensubtitles", "interface.main_window"):
        try:
            importlib.import_module(mod)
            print(f"  OK   {mod}")
        except Exception as e:  # noqa: BLE001
            ok = ok and not mod.startswith(("PySide6", "core", "interface", "movies", "music"))
            print(f"  ERRO {mod}: {e}")
    from core.diagnostics import run_diagnostics
    for t in run_diagnostics():
        print(f"  {'OK  ' if t.ok else '--  '} {t.name}: {t.version}")
    Database()
    print("RESULTADO: " + ("TUDO OK" if ok else "HÁ ERROS"))
    return 0 if ok else 1


def main() -> int:
    ensure_dirs()
    log = setup_logging()
    log.info("A iniciar %s %s", APP_NAME, APP_VERSION)
    if "--check" in sys.argv:
        return run_check()
    if "--auto" in sys.argv:
        return run_headless(sys.argv)
    db = Database()
    recover_interrupted(db)
    if db.get_setting("backups_enabled"):
        try:
            from core.backup import backup_database
            backup_database(db.path)
        except Exception as e:  # noqa: BLE001
            log.warning("Backup falhou: %s", e)

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
