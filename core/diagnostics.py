"""Diagnóstico das ferramentas externas (só verifica, nunca instala)."""
from __future__ import annotations

import importlib
import platform
import sqlite3
import subprocess
import sys
from dataclasses import dataclass

from .mediainfo import find_tool, run_quiet

WIN = sys.platform.startswith("win")


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
        r = run_quiet(cmd, 10)
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
                          "python.org" if WIN else "sudo apt install python3", True))
    res.append(ToolStatus("SQLite", True, sqlite3.sqlite_version, "Base de dados", "", True))
    v = _module_version("PySide6")
    res.append(ToolStatus("PySide6", v is not None, v or "em falta", "Interface gráfica",
                          "instalar.bat" if WIN else "bash instalar.sh", True))
    for exe, purpose in (("ffprobe", "Análise técnica de vídeo e áudio"),
                         ("ffmpeg", "Conversões futuras (legendas, etc.)")):
        p = find_tool(exe)
        res.append(ToolStatus(exe.upper() if exe == "ffmpeg" else "FFprobe", p is not None,
                              _cmd_version([p, "-version"]).replace(f"{exe} version ", "")
                              .split(" Copyright")[0] if p else "em falta",
                              purpose, "winget install Gyan.FFmpeg" if WIN else "sudo apt install ffmpeg", exe == "ffprobe"))
    v = _module_version("mutagen")
    res.append(ToolStatus("Mutagen", v is not None, v or "em falta",
                          "Leitura de tags musicais", "instalar.bat" if WIN else "bash instalar.sh"))
    p = find_tool("beet")
    res.append(ToolStatus("Beets", p is not None,
                          _cmd_version([p, "version"]) if p else "em falta (Fase 7)",
                          "Organização musical", "pip install beets" if WIN else "sudo apt install beets"))
    p = find_tool("czkawka_cli") or find_tool("czkawka_gui") or find_tool("czkawka")
    res.append(ToolStatus("Czkawka", p is not None, "instalado" if p else "em falta (Fase 8)",
                          "Duplicados e ficheiros semelhantes", "github.com/qarmin/czkawka" if WIN else "flatpak install czkawka"))
    v = _module_version("argostranslate")
    res.append(ToolStatus("Argos Translate", v is not None, v or "em falta (Fase 5)",
                          "Tradução local de legendas", "pip install argostranslate"))
    p = find_tool("ollama")
    res.append(ToolStatus("Ollama", p is not None, "instalado" if p else "opcional",
                          "IA local (opcional)", "ollama.com"))
    return res
