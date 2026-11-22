"""Diagnóstico das ferramentas externas (só verifica, nunca instala)."""
from __future__ import annotations

import importlib
import platform
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class ToolStatus:
    name: str
    ok: bool
    version: str
    purpose: str
    install_hint: str
    required: bool = False


def _cmd_version(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        out = (r.stdout or r.stderr).strip().splitlines()
        return out[0][:80] if out else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _module_version(name: str) -> str | None:
    try:
        m = importlib.import_module(name)
    except Exception:  # noqa: BLE001
        return None
    return str(getattr(m, "__version__", getattr(m, "version", "instalado")))


def run_diagnostics() -> list[ToolStatus]:
    res: list[ToolStatus] = []
    res.append(ToolStatus("Python", sys.version_info >= (3, 10),
                          platform.python_version(), "Base da aplicação",
                          "sudo apt install python3", True))
    res.append(ToolStatus("SQLite", True, sqlite3.sqlite_version, "Base de dados", "", True))
    v = _module_version("PySide6")
    res.append(ToolStatus("PySide6", v is not None, v or "em falta", "Interface gráfica",
                          "bash instalar.sh", True))
    for exe, purpose in (("ffprobe", "Análise técnica de vídeo e áudio"),
                         ("ffmpeg", "Conversões futuras (legendas, etc.)")):
        p = shutil.which(exe)
        res.append(ToolStatus(exe.upper() if exe == "ffmpeg" else "FFprobe", p is not None,
                              _cmd_version([p, "-version"]).replace(f"{exe} version ", "")
                              .split(" Copyright")[0] if p else "em falta",
                              purpose, "sudo apt install ffmpeg", exe == "ffprobe"))
    v = _module_version("mutagen")
    res.append(ToolStatus("Mutagen", v is not None, v or "em falta",
                          "Leitura de tags musicais", "bash instalar.sh"))
    p = shutil.which("beet")
    res.append(ToolStatus("Beets", p is not None,
                          _cmd_version([p, "version"]) if p else "em falta (Fase 7)",
                          "Organização musical", "sudo apt install beets"))
    p = shutil.which("czkawka_cli") or shutil.which("czkawka_gui") or shutil.which("czkawka")
    res.append(ToolStatus("Czkawka", p is not None, "instalado" if p else "em falta (Fase 8)",
                          "Duplicados e ficheiros semelhantes", "flatpak install czkawka"))
    v = _module_version("argostranslate")
    res.append(ToolStatus("Argos Translate", v is not None, v or "em falta (Fase 5)",
                          "Tradução local de legendas", "pip install argostranslate"))
    p = shutil.which("ollama")
    res.append(ToolStatus("Ollama", p is not None, "instalado" if p else "opcional",
                          "IA local (opcional)", "ollama.com"))
    return res
