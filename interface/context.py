"""Contexto partilhado pela interface: base de dados, operações e tarefas em fundo."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from core.database import Database
from core.logger import get_logger
from core.operations import OperationManager
from core.safety import SafeFileManager
from core.scanner import Scanner

log = get_logger("ui")


class ScanWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(str, dict)
    failed = Signal(str, str)

    def __init__(self, kind: str, folder: str, db_path, parent=None):
        super().__init__(parent)
        self.kind, self.folder, self.db_path = kind, folder, db_path
        self.scanner: Scanner | None = None

    def run(self):
        db = Database(self.db_path)
        try:
            self.scanner = Scanner(db, progress=lambda a, b, c: self.progress.emit(a, b, c))
            if self.kind == "movies":
                stats = self.scanner.scan_movies(self.folder)
            else:
                stats = self.scanner.scan_music(self.folder)
            self.done.emit(self.kind, stats)
        except Exception as e:  # noqa: BLE001
            log.exception("Falha na análise")
            try:
                db.log_error("error", "scanner", self.folder, str(e))
            except Exception:  # noqa: BLE001
                pass
            self.failed.emit(self.kind, str(e))
        finally:
            db.close()

    def cancel(self):
        if self.scanner:
            self.scanner.cancel()


class FuncWorker(QThread):
    """Executa fn(progress, cancelled) numa thread e devolve o resultado."""
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            res = self.fn(lambda a, b, c: self.progress.emit(a, b, c), lambda: self._cancel)
            self.done.emit(res)
        except Exception as e:  # noqa: BLE001
            log.exception("Tarefa falhou")
            self.failed.emit(str(e))


class AppContext(QObject):
    data_changed = Signal()
    scan_started = Signal(str)
    scan_progress = Signal(int, int, str)
    scan_finished = Signal(str, dict)
    scan_failed = Signal(str, str)
    navigate = Signal(str, str)   # (página, filtro)

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.ops = OperationManager(db)
        self.files = SafeFileManager(db, self.ops)
        self.worker: ScanWorker | None = None

    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def start_scan(self, kind: str) -> str | None:
        """Devolve uma mensagem de erro ou None se a análise arrancou."""
        if self.busy:
            return "Já existe uma análise em curso."
        key = "movies_folder" if kind == "movies" else "music_source_folder"
        folder = self.db.get_setting(key)
        if not folder:
            return "Defina primeiro a pasta na Configuração."
        self.worker = ScanWorker(kind, folder, self.db.path, self)
        self.worker.progress.connect(self.scan_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        self.scan_started.emit(kind)
        return None

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel()

    def _on_done(self, kind, stats):
        self.scan_finished.emit(kind, stats)
        self.data_changed.emit()

    def _on_failed(self, kind, msg):
        self.scan_failed.emit(kind, msg)
        self.data_changed.emit()
