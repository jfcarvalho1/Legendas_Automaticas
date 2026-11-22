"""Sistema de registos (ficheiro rotativo em logs/)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOGS_DIR

_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _configured
    logger = logging.getLogger("mediaorganizer")
    if _configured:
        return logger
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = RotatingFileHandler(LOGS_DIR / "mediaorganizer.log", maxBytes=2_000_000,
                             backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.setLevel(level)
    logger.addHandler(fh)
    logger.addHandler(sh)
    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"mediaorganizer.{name}")
