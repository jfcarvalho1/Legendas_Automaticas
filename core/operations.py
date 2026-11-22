"""Sistema de operações: identificadores únicos, registo e recuperação.

Cada operação sobre ficheiros recebe um identificador OP_AAAAMMDD_NNN e fica
registada na base de dados (tabela operations) e num diário JSON Lines em
logs/operations.jsonl, para rastreabilidade mesmo que a base de dados falhe.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from .config import LOGS_DIR
from .database import Database, now_iso
from .logger import get_logger

log = get_logger("operations")
_id_lock = threading.Lock()

# Estados possíveis
PENDING = "pending"
COMPLETED = "completed"
COPIED = "copied"        # cópia validada, original mantido
FAILED = "failed"
REVERTED = "reverted"

REVERSIBLE = {"move", "rename", "quarantine", "create", "copy"}


class OperationManager:
    def __init__(self, db: Database):
        self.db = db
        self.journal = LOGS_DIR / "operations.jsonl"
        self.journal.parent.mkdir(parents=True, exist_ok=True)

    # -- identificadores ---------------------------------------------------
    def new_operation_id(self) -> str:
        with _id_lock:
            prefix = datetime.now().strftime("OP_%Y%m%d_")
            last = self.db.scalar(
                "SELECT operation_id FROM operations WHERE operation_id LIKE ? "
                "ORDER BY operation_id DESC LIMIT 1", (prefix + "%",))
            n = int(last.rsplit("_", 1)[1]) + 1 if last else 1
            op_id = f"{prefix}{n:03d}"
            # Reserva imediata do identificador
            self.db.execute(
                "INSERT INTO operations(operation_id, operation, timestamp, status) "
                "VALUES(?, 'reserved', ?, ?)", (op_id, now_iso(), PENDING))
            return op_id

    # -- registo -----------------------------------------------------------
    def record(self, op_id: str, operation: str, original_path: str | None,
               new_path: str | None, status: str, result: str | None = None,
               error: str | None = None, reason: str | None = None,
               details: dict | None = None) -> None:
        ts = now_iso()
        self.db.execute(
            "UPDATE operations SET operation=?, original_path=?, new_path=?, timestamp=?, "
            "status=?, result=?, error=?, reason=?, details=? WHERE operation_id=?",
            (operation, original_path, new_path, ts, status, result, error, reason,
             json.dumps(details or {}, ensure_ascii=False), op_id))
        entry = {
            "operation_id": op_id, "operation": operation,
            "original_path": original_path, "new_path": new_path,
            "timestamp": ts, "status": status,
        }
        if result:
            entry["result"] = result
        if error:
            entry["error"] = error
        if reason:
            entry["reason"] = reason
        if details:
            entry["details"] = details
        try:
            with open(self.journal, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:  # o registo na BD já ficou feito
            log.error("Não foi possível escrever o diário de operações: %s", e)
        log.info("%s %s [%s] %s -> %s", op_id, operation, status, original_path, new_path)

    def add_file(self, op_id: str, path: str, role: str, sha256: str | None = None,
                 size: int | None = None) -> None:
        self.db.execute(
            "INSERT INTO operation_files(operation_id, path, role, sha256, size) "
            "VALUES(?,?,?,?,?)", (op_id, path, role, sha256, size))

    def get(self, op_id: str) -> dict | None:
        return self.db.query_one("SELECT * FROM operations WHERE operation_id=?", (op_id,))

    def list(self, limit: int = 500) -> list[dict]:
        return self.db.query(
            "SELECT * FROM operations WHERE operation != 'reserved' "
            "ORDER BY timestamp DESC, operation_id DESC LIMIT ?", (limit,))

    def can_revert(self, op: dict | None) -> tuple[bool, str]:
        if not op:
            return False, "Operação inexistente."
        if op["operation"] not in REVERSIBLE:
            return False, "Este tipo de operação não é reversível."
        if op["status"] != COMPLETED:
            return False, f"Estado '{op['status']}' não permite reverter."
        return True, ""

    def mark_reverted(self, op_id: str, by_op_id: str) -> None:
        self.db.execute("UPDATE operations SET status=?, reverted_by=? WHERE operation_id=?",
                        (REVERTED, by_op_id, op_id))

    def cleanup_reserved(self) -> None:
        """Identificadores reservados e nunca usados (ex.: falha a meio)."""
        self.db.execute(
            "UPDATE operations SET operation='interrupted', status=? "
            "WHERE operation='reserved'", (FAILED,))


def details_json(op: dict) -> dict[str, Any]:
    try:
        return json.loads(op.get("details") or "{}")
    except json.JSONDecodeError:
        return {}
