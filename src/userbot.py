"""
UserBot — учётная запись Telegram с ответами через OpenAI.
Только входящие ЛС, синхронные обёртки telethon.sync.
"""

import asyncio
from telethon.sync import TelegramClient
from telethon import events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    FloodWaitError,
)

from config import API_ID, API_HASH, PHONE
from .context_store import add_exchange, get_messages_for_openai
from . import openai_client
from .logger import setup

SESSION_NAME = "userbot_session"
log = setup()


def run_userbot() -> None:
    """Запуск UserBot: слушает входящие ЛС, отвечает через OpenAI."""
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    try:
        try:
            client.start(phone=PHONE)
        except SessionPasswordNeededError:
            client.sign_in(password=input("Введите пароль 2FA: "))
        me = client.get_me()
        print(f"Авторизован: {me.first_name} (@{me.username})")
        print("Ожидаю сообщения в ЛС... (Ctrl+C для выхода)\n")

        @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def handler(event: events.NewMessage.Event):
            try:
                text = event.text
                if not text or not text.strip():
                    return
                sender_id = event.sender_id
                if not sender_id:
                    return

                messages = get_messages_for_openai(sender_id)
                messages.append({"role": "user", "content": text})

                reply_text = await asyncio.to_thread(
                    openai_client.get_reply,
                    messages,
                )

                await event.reply(reply_text)
                add_exchange(sender_id, text, reply_text)
            except Exception:
                log.exception("Handler error")
                raise

        client.run_until_disconnected()

    except PhoneNumberInvalidError:
        log.error("Неверный формат номера телефона")
        print("Ошибка: неверный формат номера телефона.")
    except FloodWaitError as e:
        log.error("FloodWait: %s секунд", e.seconds)
        print(f"Ожидание {e.seconds} с (ограничение Telegram).")
    except KeyboardInterrupt:
        print("\nОстановлено.")
    except Exception as e:
        log.exception("Неожиданная ошибка")
        print(f"Ошибка: {e}")
    finally:
        client.disconnect()
        print("Клиент отключён.")
