"""
Простой логгер: ошибки и INFO в файл logs/errors.log.
"""

import logging
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "errors.log"


def _ensure_dir() -> None:
    LOG_DIR.mkdir(exist_ok=True)


def setup() -> logging.Logger:
    """Настроить и вернуть логгер."""
    _ensure_dir()
    logger = logging.getLogger("userbot")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def get_logger() -> logging.Logger:
    """Получить логгер (вызов setup() при первом обращении)."""
    logger = logging.getLogger("userbot")
    if not logger.handlers:
        return setup()
    return logger


def on_exchange_added(store: dict) -> None:
    """Совместимость: сейчас ничего не делает."""
    return None
