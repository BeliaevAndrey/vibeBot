"""
UserBot — учётная запись Telegram, опросник с OpenAI.
Пишет первым кандидату (CANDIDATE_USERNAME), обрабатывает ответы по сценарию опросника.
"""

import asyncio
from telethon.sync import TelegramClient
from telethon import events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    FloodWaitError,
)

from config import API_ID, API_HASH, PHONE, CANDIDATE_USERNAME
from . import questionnaire
from .logger import setup

SESSION_NAME = "userbot_session"
log = setup()


def run_userbot() -> None:
    """Запуск UserBot: приветствие кандидату, затем опросник по входящим ЛС."""
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    try:
        try:
            client.start(phone=PHONE)
        except SessionPasswordNeededError:
            client.sign_in(password=input("Введите пароль 2FA: "))
        me = client.get_me()
        print(f"Авторизован: {me.first_name} (@{me.username})")

        candidate_user_id: int | None = None
        if CANDIDATE_USERNAME:
            try:
                entity = client.get_entity(CANDIDATE_USERNAME)
                candidate_user_id = entity.id
                candidate_username = getattr(entity, "username", None)
                greeting = questionnaire.get_greeting(candidate_username)
                client.send_message(entity, greeting)
                questionnaire.init_session(candidate_user_id, getattr(entity, "username", None))
                print(f"Отправлено приветствие кандидату {CANDIDATE_USERNAME}")
            except Exception as e:
                log.exception("Не удалось отправить приветствие кандидату: %s", e)
                print(f"Ошибка приветствия: {e}")

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
                if candidate_user_id is not None and sender_id != candidate_user_id:
                    return

                sender = await event.get_sender()
                username = getattr(sender, "username", None)
                username_str = f"@{username}" if username else None

                state = questionnaire.get_state(sender_id)
                if not state:
                    return

                if state["state"] == "greeting_sent":
                    reply_text, done = await questionnaire.handle_agreement(
                        sender_id, username_str, text
                    )
                elif state["state"] == "asking":
                    reply_text, done = await questionnaire.handle_answer(
                        sender_id, username_str, text
                    )
                else:
                    return

                if reply_text:
                    await event.reply(reply_text)

                if done:
                    result = questionnaire.finish_session(sender_id)
                    if result:
                        questionnaire.dump_result_and_save_text(result, client)
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
