"""Protecção dos ficheiros: verificações antes de mover, quarentena e reposição.

Regras (secções 25 e 27 da especificação):
  1. Verificar o ficheiro de origem.
  2. Verificar o destino (nunca sobrescrever).
  3. Tratar conflitos (erro explícito ou nome único).
  4/5. Entre discos diferentes: copiar e validar por SHA256.
  6. Registar a operação.
  7. Só remover a origem quando a política o permitir.
  8. Nunca apagar irreversivelmente.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from .config import QUARANTINE_CATEGORIES
from .database import Database, now_iso
from .logger import get_logger
from .operations import COMPLETED, COPIED, FAILED, OperationManager

log = get_logger("safety")


class SafetyError(Exception):
    """Operação recusada por motivo de segurança."""


def sha256_file(path: Path | str, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def check_source(src: Path) -> None:
    if not src.exists():
        raise SafetyError(f"O ficheiro de origem não existe: {src}")
    if not src.is_file():
        raise SafetyError(f"A origem não é um ficheiro: {src}")
    if not os.access(src, os.R_OK):
        raise SafetyError(f"Sem permissão de leitura: {src}")


def is_case_only_rename(src: Path, dst: Path) -> bool:
    """Windows/macOS: 'matrix.mkv' -> 'Matrix.mkv' aponta para o mesmo ficheiro."""
    try:
        return (src != dst and str(src).lower() == str(dst).lower()
                and dst.exists() and os.path.samefile(src, dst))
    except OSError:
        return False


def check_destination(dst: Path, src: Path | None = None) -> None:
    if src is not None and is_case_only_rename(src, dst):
        return
    if dst.exists() or dst.is_symlink():
        raise SafetyError(f"Conflito: o destino já existe: {dst}")
    parent = dst.parent
    probe = parent
    while not probe.exists():
        probe = probe.parent
    if not os.access(probe, os.W_OK):
        raise SafetyError(f"Sem permissão de escrita no destino: {parent}")


def unique_destination(dst: Path) -> Path:
    """Devolve um caminho livre acrescentando ' (2)', ' (3)', ... ao nome."""
    if not dst.exists():
        return dst
    n = 2
    while True:
        cand = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
        if not cand.exists():
            return cand
        n += 1


def same_device(a: Path, b: Path) -> bool:
    probe = b
    while not probe.exists():
        probe = probe.parent
    return os.stat(a).st_dev == os.stat(probe).st_dev


class SafeFileManager:
    def __init__(self, db: Database, ops: OperationManager | None = None):
        self.db = db
        self.ops = ops or OperationManager(db)

    # -- mover / renomear --------------------------------------------------
    def safe_move(self, src: Path | str, dst: Path | str, operation: str = "move",
                  reason: str | None = None, op_id: str | None = None,
                  details: dict | None = None) -> dict:
        """Move um ficheiro com todas as verificações. Devolve o registo da operação."""
        src, dst = Path(src), Path(dst)
        op_id = op_id or self.ops.new_operation_id()
        details = dict(details or {})
        try:
            check_source(src)
            check_destination(dst, src)
            size = src.stat().st_size
            details.update({"original_name": src.name, "size": size})
            dst.parent.mkdir(parents=True, exist_ok=True)

            if same_device(src, dst.parent):
                # rename no mesmo disco: atómico, o conteúdo não é tocado
                os.rename(src, dst)
                if not dst.exists() or dst.stat().st_size != size:
                    raise SafetyError("Validação falhou após mover.")
                status, result = COMPLETED, "Movido no mesmo disco."
                self.ops.add_file(op_id, str(dst), "destination", None, size)
            else:
                src_hash = sha256_file(src)
                tmp = dst.with_name(dst.name + ".mo-partial")
                shutil.copy2(src, tmp)
                if sha256_file(tmp) != src_hash:
                    tmp.unlink(missing_ok=True)
                    raise SafetyError("A cópia não corresponde ao original (SHA256).")
                os.rename(tmp, dst)
                self.ops.add_file(op_id, str(src), "source", src_hash, size)
                self.ops.add_file(op_id, str(dst), "destination", src_hash, size)
                details["sha256"] = src_hash
                if self.db.get_setting("allow_cross_device_move"):
                    src.unlink()
                    status, result = COMPLETED, "Copiado entre discos, validado e original removido."
                else:
                    status, result = COPIED, ("Copiado entre discos e validado; "
                                              "original preservado (política).")
            self.ops.record(op_id, operation, str(src), str(dst), status, result=result,
                            reason=reason, details=details)
        except Exception as e:  # noqa: BLE001 — tudo fica registado
            self.ops.record(op_id, operation, str(src), str(dst), FAILED, error=str(e),
                            reason=reason, details=details)
            self.db.log_error("error", "safety", str(src), f"{operation}: {e}")
            raise
        return self.ops.get(op_id)

    # -- quarentena --------------------------------------------------------
    def quarantine_root(self, root: Path | None = None) -> Path:
        root = Path(root or self.db.get_setting("quarantine_folder"))
        for c in QUARANTINE_CATEGORIES:
            (root / c).mkdir(parents=True, exist_ok=True)
        return root

    def quarantine(self, src: Path | str, category: str, reason: str,
                   root: Path | None = None, details: dict | None = None) -> dict:
        if not self.db.get_setting("quarantine_enabled"):
            raise SafetyError("A quarentena está desactivada na configuração.")
        if category not in QUARANTINE_CATEGORIES:
            raise SafetyError(f"Categoria de quarentena desconhecida: {category}")
        src = Path(src)
        op_id = self.ops.new_operation_id()
        folder = self.quarantine_root(root) / category
        dst = unique_destination(folder / f"{op_id}__{src.name}")
        manifest = {
            "operation_id": op_id,
            "original_name": src.name,
            "original_path": str(src),
            "quarantine_path": str(dst),
            "category": category,
            "reason": reason,
            "date": now_iso(),
            "restorable": True,
        }
        op = self.safe_move(src, dst, "quarantine", reason=reason, op_id=op_id,
                            details={"category": category, **(details or {})})
        try:
            with open(folder / f"{op_id}.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.error("Manifesto de quarentena não escrito: %s", e)
        if op["status"] == COMPLETED:
            self._mark_media_status(src, dst, "quarantined")
        return op

    # -- criar / copiar -----------------------------------------------------
    def create_file(self, dst: Path | str, data: bytes, operation: str = "create",
                    reason: str | None = None, details: dict | None = None) -> dict:
        """Cria um ficheiro novo (legenda, capa, NFO…). Nunca escreve por cima."""
        dst = Path(dst)
        op_id = self.ops.new_operation_id()
        details = dict(details or {})
        try:
            check_destination(dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".mo-partial")
            tmp.write_bytes(data)
            os.replace(tmp, dst)
            if not dst.exists() or dst.stat().st_size != len(data):
                raise SafetyError("Validação falhou após escrever o ficheiro.")
            details["size"] = len(data)
            self.ops.add_file(op_id, str(dst), "created", hashlib.sha256(data).hexdigest(), len(data))
            self.ops.record(op_id, operation, None, str(dst), COMPLETED,
                            result="Ficheiro criado.", reason=reason, details=details)
        except Exception as e:  # noqa: BLE001
            self.ops.record(op_id, operation, None, str(dst), FAILED, error=str(e),
                            reason=reason, details=details)
            self.db.log_error("error", "safety", str(dst), f"{operation}: {e}")
            raise
        return self.ops.get(op_id)

    def safe_copy(self, src: Path | str, dst: Path | str, reason: str | None = None,
                  details: dict | None = None) -> dict:
        """Copia e valida por SHA256. O original fica sempre intacto."""
        src, dst = Path(src), Path(dst)
        op_id = self.ops.new_operation_id()
        details = dict(details or {})
        try:
            check_source(src)
            check_destination(dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            h = sha256_file(src)
            tmp = dst.with_name(dst.name + ".mo-partial")
            shutil.copy2(src, tmp)
            if sha256_file(tmp) != h:
                tmp.unlink(missing_ok=True)
                raise SafetyError("A cópia não corresponde ao original (SHA256).")
            os.rename(tmp, dst)
            details.update({"sha256": h, "size": src.stat().st_size, "original_name": src.name})
            self.ops.add_file(op_id, str(dst), "destination", h, details["size"])
            self.ops.record(op_id, "copy", str(src), str(dst), COMPLETED,
                            result="Copiado e validado; original intacto.", reason=reason,
                            details=details)
        except Exception as e:  # noqa: BLE001
            self.ops.record(op_id, "copy", str(src), str(dst), FAILED, error=str(e),
                            reason=reason, details=details)
            self.db.log_error("error", "safety", str(src), f"copy: {e}")
            raise
        return self.ops.get(op_id)

    # -- reposição ---------------------------------------------------------
    def revert(self, op_id: str) -> dict:
        op = self.ops.get(op_id)
        ok, why = self.ops.can_revert(op)
        if not ok:
            raise SafetyError(why)
        if op["operation"] in ("create", "copy"):
            # desfazer uma criação/cópia = retirar o ficheiro novo (para a quarentena)
            current = Path(op["new_path"])
            if not current.exists():
                raise SafetyError(f"O ficheiro já não está em: {current}")
            q = self.quarantine(current, "Revertidos", f"Reversão de {op_id}",
                                details={"reverts": op_id})
            if q["status"] == COMPLETED:
                self.ops.mark_reverted(op_id, q["operation_id"])
            return q
        original, current = Path(op["original_path"]), Path(op["new_path"])
        if not current.exists():
            raise SafetyError(f"O ficheiro já não está em: {current}")
        if original.exists():
            raise SafetyError(f"Já existe um ficheiro no local original: {original}")
        new_op = self.safe_move(current, original, "revert",
                                reason=f"Reposição de {op_id}",
                                details={"reverts": op_id})
        if new_op["status"] == COMPLETED:
            self.ops.mark_reverted(op_id, new_op["operation_id"])
            if op["operation"] == "rename":
                self._mark_media_status(current, original, "ok", reset_mtime=False)
            else:
                self._mark_media_status(current, original, "pending")
            # manifesto de quarentena deixa de ser necessário: marcado, não apagado
            if op["operation"] == "quarantine":
                mf = current.parent / f"{op_id}.json"
                if mf.exists():
                    try:
                        data = json.loads(mf.read_text(encoding="utf-8"))
                        data.update({"restorable": False, "restored_by": new_op["operation_id"],
                                     "restored_at": now_iso()})
                        mf.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
                    except (OSError, json.JSONDecodeError):
                        pass
        return new_op

    def revert_batch(self, batch_id: str) -> tuple[int, list[str]]:
        """Reverte, pela ordem inversa, todas as operações concluídas de um lote."""
        ops = self.db.query(
            "SELECT operation_id FROM operations WHERE status='completed' "
            "AND operation IN ('rename', 'move', 'quarantine', 'create', 'copy') AND details LIKE ? "
            "ORDER BY id DESC", (f'%"batch": "{batch_id}"%',))
        done, errors = 0, []
        created_dirs: set[Path] = set()
        for o in ops:
            op = self.ops.get(o["operation_id"])
            try:
                self.revert(o["operation_id"])
                done += 1
                created_dirs.add(Path(op["new_path"]).parent)
            except (SafetyError, OSError) as e:
                errors.append(f"{o['operation_id']}: {e}")
        # pastas criadas pelo lote e que ficaram completamente vazias
        for d in sorted(created_dirs, key=lambda x: len(str(x)), reverse=True):
            try:
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass
        return done, errors

    def _mark_media_status(self, old: Path, new: Path, status: str,
                           reset_mtime: bool = True) -> None:
        """Mantém o inventário coerente depois de mover um ficheiro."""
        for table in ("movies", "music"):
            row = self.db.query_one(f"SELECT id FROM {table} WHERE path=?", (str(old),))
            if row:
                if self.db.query_one(f"SELECT id FROM {table} WHERE path=?", (str(new),)):
                    self.db.execute(f"DELETE FROM {table} WHERE path=?", (str(new),))
                mt = "NULL" if reset_mtime else "mtime"
                self.db.execute(
                    f"UPDATE {table} SET path=?, folder=?, filename=?, mtime={mt}, status=? "
                    f"WHERE id=?", (str(new), str(new.parent), new.name, status, row["id"]))
