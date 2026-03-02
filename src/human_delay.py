"""
Задержки ответов кандидату: имитация «обдумывания» и набора текста с индикатором «печатает».
"""

import asyncio
import random

from telethon import functions
from telethon.tl.types import SendMessageTypingAction

from config import (
    TOGGLE_DELAY,
    TYPING_CHARS_PER_MIN,
    THINK_DELAY_MIN,
    THINK_DELAY_MAX,
    HUMAN_DELAY_MAX_TYPING_SEC,
)

# Telegram сбрасывает индикатор «печатает» примерно через 5 сек — повторяем в цикле
TYPING_ACTION_INTERVAL_SEC = 5


def _typing_duration_sec(text: str) -> float:
    """Время «набора» текста в секундах (пропорционально длине, с cap)."""
    if not text:
        return 0.0
    chars_per_sec = TYPING_CHARS_PER_MIN / 60.0
    sec = len(text) / chars_per_sec
    return min(sec, HUMAN_DELAY_MAX_TYPING_SEC)


async def human_like_delay(client, entity, text: str) -> None:
    """
    Перед отправкой сообщения кандидату: пауза «обдумывание» + показ «печатает» на время,
    пропорциональное длине текста (200–300 симв/мин из config). Вызывать перед send_message / reply.
    """
    if TOGGLE_DELAY == "OFF":
        return

    think_sec = random.uniform(THINK_DELAY_MIN, THINK_DELAY_MAX)
    await asyncio.sleep(think_sec)

    typing_sec = _typing_duration_sec(text or "")
    while typing_sec > 0:
        try:
            await client(functions.messages.SetTypingRequest(
                peer=entity,
                action=SendMessageTypingAction(),
            ))
        except Exception:
            pass
        chunk = min(TYPING_ACTION_INTERVAL_SEC, typing_sec)
        await asyncio.sleep(chunk)
        typing_sec -= chunk
