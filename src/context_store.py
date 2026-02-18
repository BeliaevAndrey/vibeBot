"""
Хранение контекста беседы: 10 пар сообщений на пользователя.
Ключ — user_id (int). MVP: только ЛС.
"""

from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Any

from . import logger as _logger

MAX_PAIRS = 10
UTC_PLUS_3 = timezone(timedelta(hours=3))

_store: dict[int, deque[dict[str, Any]]] = {}


def add_exchange(user_id: int, user_msg: str, assistant_msg: str) -> None:
    """Добавить пару сообщений в контекст пользователя."""
    if user_id not in _store:
        _store[user_id] = deque(maxlen=MAX_PAIRS)
    pair = {
        "user": user_msg,
        "assistant": assistant_msg,
        "datetime": datetime.now(UTC_PLUS_3),
    }
    _store[user_id].append(pair)
    _logger.on_exchange_added(_store)


def get_messages_for_openai(user_id: int) -> list[dict[str, str]]:
    """
    Возвращает историю в формате для OpenAI Chat Completions.
    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    """
    if user_id not in _store or not _store[user_id]:
        return []
    result: list[dict[str, str]] = []
    for pair in _store[user_id]:
        result.append({"role": "user", "content": pair["user"]})
        result.append({"role": "assistant", "content": pair["assistant"]})
    return result
