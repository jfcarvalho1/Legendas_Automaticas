"""Agendamento diário da automatização (Agendador de Tarefas do Windows ou cron no Linux)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import APP_ROOT
from .mediainfo import NO_WINDOW

TASK = "MediaOrganizer"
MARK = "# MediaOrganizer"


def _python_gui() -> str:
    exe = Path(sys.executable)
    if sys.platform.startswith("win"):
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return str(exe)


def command(mode: str) -> list[str]:
    return [_python_gui(), str(APP_ROOT / "app.py"), "--auto", "--mode", mode]


def _run(cmd: list[str], inp: str | None = None) -> subprocess.CompletedProcess:
    # As ferramentas da consola do Windows (schtasks) respondem na codificação OEM
    # (cp850 em português: «não», «Próxima»…). Nunca falhar por causa de acentos.
    enc = "oem" if sys.platform.startswith("win") else "utf-8"
    return subprocess.run(cmd, capture_output=True, text=True, input=inp, encoding=enc,
                          errors="replace", creationflags=NO_WINDOW)


def install(hour: int, minute: int, mode: str) -> str:
    if sys.platform.startswith("win"):
        exe, app, *rest = command(mode)
        tr = f'"{exe}" "{app}" ' + " ".join(rest)
        r = _run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", TASK, "/TR", tr,
                  "/ST", f"{hour:02d}:{minute:02d}"])
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or r.stdout.strip())
        return f"Tarefa diária criada no Agendador do Windows às {hour:02d}:{minute:02d}."
    cur = _run(["crontab", "-l"])
    lines = [ln for ln in (cur.stdout or "").splitlines() if MARK not in ln]
    cmd = " ".join(f'"{c}"' for c in command(mode))
    lines.append(f"{minute} {hour} * * * cd \"{APP_ROOT}\" && {cmd} >/dev/null 2>&1 {MARK}")
    r = _run(["crontab", "-"], "\n".join(lines) + "\n")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return f"Tarefa diária criada (cron) às {hour:02d}:{minute:02d}."


def remove() -> str:
    if sys.platform.startswith("win"):
        _run(["schtasks", "/Delete", "/F", "/TN", TASK])
        return "Agendamento removido."
    cur = _run(["crontab", "-l"])
    lines = [ln for ln in (cur.stdout or "").splitlines() if MARK not in ln]
    _run(["crontab", "-"], "\n".join(lines) + ("\n" if lines else ""))
    return "Agendamento removido."


def status() -> str | None:
    try:
        if sys.platform.startswith("win"):
            r = _run(["schtasks", "/Query", "/TN", TASK, "/FO", "LIST"])
            if r.returncode != 0:
                return None
            nxt = [ln for ln in r.stdout.splitlines() if ":" in ln and ("Próxima" in ln or "Next" in ln)]
            return nxt[0].split(":", 1)[1].strip() if nxt else "activo"
        r = _run(["crontab", "-l"])
        ln = next((x for x in (r.stdout or "").splitlines() if MARK in x), None)
        if not ln:
            return None
        m, h = ln.split()[:2]
        return f"todos os dias às {int(h):02d}:{int(m):02d}"
    except Exception:  # noqa: BLE001 — o estado do agendamento nunca pode impedir o arranque
        return None
