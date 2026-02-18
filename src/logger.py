"""
Логгер: ошибки в logs/, дамп контекста в dumps/.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
DUMP_DIR = Path("dumps")
LOG_FILE = LOG_DIR / "errors.log"

_EXCHANGE_COUNT = 0
DUMP_EVERY = 10


def _ensure_dirs() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    DUMP_DIR.mkdir(exist_ok=True)


def setup() -> logging.Logger:
    """Настроить и вернуть логгер для ошибок."""
    _ensure_dirs()
    logger = logging.getLogger("userbot")
    if not logger.handlers:
        logger.setLevel(logging.ERROR)
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.ERROR)
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


def dump_context(store: dict) -> None:
    """Дамп контекста в dumps/ в формате JSON."""
    _ensure_dirs()
    data: dict = {}
    for user_id, pairs in store.items():
        data[str(user_id)] = [
            {
                "user": p["user"],
                "assistant": p["assistant"],
                "datetime": p["datetime"].isoformat() if hasattr(p["datetime"], "isoformat") else str(p["datetime"]),
            }
            for p in pairs
        ]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DUMP_DIR / f"context_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def on_exchange_added(store: dict) -> None:
    """Вызвать после добавления пары: дамп каждые DUMP_EVERY пар."""
    global _EXCHANGE_COUNT
    _EXCHANGE_COUNT += 1
    if _EXCHANGE_COUNT >= DUMP_EVERY:
        _EXCHANGE_COUNT = 0
        dump_context(store)
