"""
UserBot — учётная запись Telegram, опросник с OpenAI.
Пишет первым кандидату (из списка или /set_candidate в command_mode), обрабатывает ответы по сценарию опросника.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta

from telethon.sync import TelegramClient
from telethon import events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    FloodWaitError,
)

from config import (
    TG_API_ID,
    TG_API_HASH,
    TG_PHONE,
    HR_ACCOUNT,
    COMMAND_MODE_PASSWORD,
    SAVE_RESULTS_TO_FILES,
    PROCESSED_USERS_PATH,
    setup_logging,
)
from . import questionnaire
from .human_delay import human_like_delay
from .candidates_source import get_candidates
from .candidates_utils import _prepare_candidate_entry, _record_processed

SESSION_NAME = "userbot_session"
setup_logging()
log = logging.getLogger("userbot")
UTC_PLUS_3 = timezone(timedelta(hours=3))

# Тексты для режима команд
CMD_LIST = (
    "/set_hr — задать @username HR. После команды дождаться запроса @username HR\n"
    "/set_candidate — задать @username кандидата. После команды дождаться запроса @username кандидата\n"
    "/start_questions — запустить опрос (после set_hr и set_candidate)\n"
    "/cancel — выйти из режима команд"
)


def _normalize_username(s: str) -> str:
    s = (s or "").strip()
    if s and not s.startswith("@"):
        return f"@{s}"
    return s or ""


def _is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in ("да", "yes", "y", "1")


def run_userbot(command_mode: bool = False) -> None:
    """Запуск UserBot. При command_mode=True — режим команд (ожидание команд в ЛС после аутентификации)."""
    client = TelegramClient(SESSION_NAME, TG_API_ID, TG_API_HASH)

    # Состояние режима команд (мутируемое из хендлера)
    cmd_state = {
        "authenticated": False,
        "operator_user_id": None,
        "pending_operator_id": None,
        "waiting_for": None,
        "hr_override": None,
        "candidate_override": None,
        "hr_set_this_session": False,
        "candidate_set_this_session": False,
        "non_command_count": -1,
        "questionnaire_running": False,
        "candidate_user_id": None,
    }

    # Состояние массового опроса (обычный режим)
    candidates_list: list[dict] = []
    current_candidate_index: int | None = None
    processed_users: dict[int, dict] = {}

    cmd_log = None
    try:
        try:
            client.start(phone=TG_PHONE)
        except SessionPasswordNeededError:
            log.warning("Требуется пароль 2FA")
            client.sign_in(password=input("Введите пароль 2FA: "))
        me = client.get_me()
        print(f"Авторизован: {me.first_name} (@{me.username})")

        candidate_user_id: int | None = None
        if command_mode:
            cmd_log = logging.getLogger("command_mode")
            cmd_log.info("начало сеанса command_mode")
        else:
            # Обычный режим: получаем список кандидатов из источника
            raw_candidates = get_candidates()
            for username, phone in raw_candidates:
                entry = _prepare_candidate_entry(username, phone)
                if entry is not None:
                    candidates_list.append(entry)
            if not candidates_list:
                print("Список кандидатов пуст, опрос не запущен.")

        if command_mode:
            print("Режим команд. Ожидаю команды в ЛС... (Ctrl+C для выхода)\n")
        else:
            print("Ожидаю сообщения в ЛС... (Ctrl+C для выхода)\n")

        @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def handler(event: events.NewMessage.Event):
            try:
                await _handle_message(event, client, command_mode, cmd_state, candidate_user_id)
            except Exception:
                log.exception("Handler error")
                raise

        async def _start_next_candidate() -> None:
            """Запустить опрос следующего кандидата из списка (обычный режим)."""
            nonlocal candidate_user_id, current_candidate_index
            if command_mode or not candidates_list:
                return
            idx = (current_candidate_index if current_candidate_index is not None else -1) + 1
            while idx < len(candidates_list):
                entry = candidates_list[idx]
                username = entry.get("username")
                phone = entry.get("phone")
                peer = username or phone
                if not peer:
                    _record_processed(processed_users, None, username, phone, False, "empty peer after normalization", logger=log)
                    idx += 1
                    continue
                try:
                    entity = await client.get_entity(peer)
                    candidate_user_id = entity.id
                    uname = getattr(entity, "username", None)
                    greeting = questionnaire.get_greeting(uname)
                    await human_like_delay(client, entity, greeting)
                    await client.send_message(entity, greeting)
                    questionnaire.init_session(candidate_user_id, uname)
                    current_candidate_index = idx
                    print(f"Опрос запущен. Кандидат: {username or phone}.")
                    return
                except Exception as e:
                    log.exception("Не удалось запустить опрос для кандидата %s: %s", peer, e)
                    _record_processed(processed_users, None, username, phone, False, str(e), logger=log)
                    idx += 1
            print("Кандидаты закончились, новых опросов нет.")

        async def _handle_message(event, client, command_mode, cmd_state, candidate_user_id):
            text = (event.text or "").strip()
            if not text:
                return
            sender_id = event.sender_id
            if not sender_id:
                return

            # ----- Режим команд: опрос идёт — обрабатываем только кандидата -----
            if command_mode and cmd_state["questionnaire_running"]:
                if sender_id != cmd_state["candidate_user_id"]:
                    return
                sender = await event.get_sender()
                username_str = f"@{sender.username}" if getattr(sender, "username", None) else None
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
                    await human_like_delay(client, event.chat_id, reply_text)
                    await event.reply(reply_text)
                if done:
                    result = questionnaire.finish_session(sender_id)
                    if result:
                        hr = cmd_state["hr_override"] or HR_ACCOUNT
                        await questionnaire.dump_result_and_save_text(
                            result, client, hr_account=hr or None,
                            candidate_entity=cmd_state.get("candidate_user_id"),
                        )
                        _record_processed(
                            processed_users,
                            sender_id,
                            username_str or cmd_state.get("candidate_override"),
                            None,
                            True,
                            None,
                            logger=log,
                        )
                    cmd_state["questionnaire_running"] = False
                    cmd_state["authenticated"] = False
                return

            # ----- Режим команд: ожидание команд от оператора -----
            if command_mode:
                is_operator = cmd_state["authenticated"] and sender_id == cmd_state["operator_user_id"]
                is_cmd = text.startswith("/")
                waiting = cmd_state["waiting_for"]

                # Ожидание ввода (пароль, username, подтверждение)
                if waiting == "password":
                    if sender_id != cmd_state.get("pending_operator_id"):
                        return
                    if text == COMMAND_MODE_PASSWORD:
                        cmd_state["authenticated"] = True
                        cmd_state["operator_user_id"] = sender_id
                        cmd_state["waiting_for"] = None
                        cmd_state["pending_operator_id"] = None
                        cmd_state["non_command_count"] = -1
                        sender = await event.get_sender()
                        op_username = getattr(sender, "username", None)
                        op_label = f"@{op_username}" if op_username else str(sender_id)
                        cmd_log.info("operator = %s", op_label)
                        await event.reply(f"Доступ разрешён.\n\n{CMD_LIST}\n\nОжидаю команду.")
                    else:
                        sender = await event.get_sender()
                        op_username = getattr(sender, "username", None)
                        op_label = f"@{op_username}" if op_username else str(sender_id)
                        cmd_log.warning("неверный пароль, от %s", op_label)
                        cmd_state["waiting_for"] = None
                        cmd_state["pending_operator_id"] = None
                        await event.reply("Неверный пароль.")
                    return

                if waiting == "hr_username" and is_operator:
                    hr_val = _normalize_username(text) or None
                    cmd_state["hr_override"] = hr_val
                    cmd_state["hr_set_this_session"] = True
                    cmd_state["waiting_for"] = None
                    cmd_state["non_command_count"] = -1
                    cmd_log.info("hr = %s", hr_val or "—")
                    await event.reply("HR установлен.")
                    return

                if waiting == "candidate_username" and is_operator:
                    cand_val = _normalize_username(text) or None
                    cmd_state["candidate_override"] = cand_val
                    cmd_state["candidate_set_this_session"] = True
                    cmd_state["waiting_for"] = None
                    cmd_state["non_command_count"] = -1
                    cmd_log.info("candidate = %s", cand_val or "—")
                    await event.reply("Кандидат установлен.")
                    return

                if waiting == "start_confirmation" and is_operator:
                    if _is_yes(text):
                        hr = cmd_state["hr_override"] or HR_ACCOUNT
                        cand = cmd_state["candidate_override"]
                        if not cand:
                            await event.reply("Кандидат не задан. Выполните /set_candidate.")
                            cmd_state["waiting_for"] = None
                            return
                        try:
                            entity = await client.get_entity(cand)
                            candidate_user_id = entity.id
                            uname = getattr(entity, "username", None)
                            greeting = questionnaire.get_greeting(uname)
                            await human_like_delay(client, entity, greeting)
                            await client.send_message(entity, greeting)
                            questionnaire.init_session(candidate_user_id, uname)
                            cmd_state["candidate_user_id"] = candidate_user_id
                            cmd_state["questionnaire_running"] = True
                            cmd_state["waiting_for"] = None
                            cmd_state["non_command_count"] = -1
                            await event.reply(f"Опрос запущен. Кандидат: {cand}.")
                        except Exception as e:
                            log.exception("Не удалось запустить опрос: %s", e)
                            await event.reply(f"Ошибка: {e}")
                            _record_processed(processed_users, None, cand, None, False, str(e), logger=log)
                            cmd_state["waiting_for"] = None
                    else:
                        cmd_state["waiting_for"] = None
                        cmd_state["non_command_count"] = -1
                        await event.reply("Запуск отменён.")
                    return

                # Команды (только от оператора, кроме /command_mode до аутентификации)
                if is_cmd:
                    cmd_state["non_command_count"] = -1
                    if text == "/command_mode":
                        if cmd_state["authenticated"] and sender_id == cmd_state["operator_user_id"]:
                            await event.reply(f"{CMD_LIST}\n\nОжидаю команду.")
                        else:
                            cmd_state["pending_operator_id"] = sender_id
                            cmd_state["waiting_for"] = "password"
                            await event.reply("Введите пароль для режима команд.")
                        return

                    if not is_operator:
                        await event.reply("Доступ только после команды перехода в \"режим команд\" и ввода пароля.")
                        return

                    if text == "/set_hr":
                        cmd_state["waiting_for"] = "hr_username"
                        await event.reply("Введите @username для HR.")
                        return
                    if text == "/set_candidate":
                        cmd_state["waiting_for"] = "candidate_username"
                        await event.reply("Введите @username кандидата.")
                        return
                    if text == "/cancel":
                        cmd_state["authenticated"] = False
                        cmd_state["hr_override"] = None
                        cmd_state["waiting_for"] = None
                        cmd_state["non_command_count"] = -1
                        await event.reply("Выхожу из режима команд.")
                        return
                    if text == "/start_questions":
                        if not cmd_state["hr_set_this_session"] or not cmd_state["candidate_set_this_session"]:
                            await event.reply("Сначала выполните /set_hr и /set_candidate.")
                            return
                        hr = cmd_state["hr_override"] or HR_ACCOUNT
                        cand = cmd_state["candidate_override"] or ""
                        await event.reply(
                            f"HR: {hr or '—'}, Кандидат: {cand or '—'}.\n"
                            "Подтвердить запуск опроса? (да / нет)"
                        )
                        cmd_state["waiting_for"] = "start_confirmation"
                        return

                    await event.reply("Неизвестная команда.")
                    return

                # Не команда от оператора в режиме ожидания команд
                if is_operator and waiting is None:
                    cmd_state["non_command_count"] += 1
                    if cmd_state["non_command_count"] == 0:
                        await event.reply(
                            "Ожидается команда (например /set_hr, /set_candidate, /start_questions, /cancel)."
                        )
                    elif cmd_state["non_command_count"] >= 1:
                        await event.reply("Выхожу из режима команд.")
                        cmd_state["authenticated"] = False
                        cmd_state["hr_override"] = None
                        cmd_state["waiting_for"] = None
                        cmd_state["non_command_count"] = -1
                return

            # ----- Обычный режим (не command_mode): один кандидат за раз из списка -----
            if candidate_user_id is not None and sender_id != candidate_user_id:
                return

            sender = await event.get_sender()
            username_str = f"@{sender.username}" if getattr(sender, "username", None) else None

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
                await human_like_delay(client, event.chat_id, reply_text)
                await event.reply(reply_text)

            if done:
                # Зафиксировать результат и перейти к следующему кандидату (обычный режим)
                username_src = username_str
                phone_src = None
                if current_candidate_index is not None and 0 <= current_candidate_index < len(candidates_list):
                    entry = candidates_list[current_candidate_index]
                    username_src = username_src or entry.get("username")
                    phone_src = entry.get("phone")

                _record_processed(processed_users, sender_id, username_src, phone_src, True, None, logger=log)

                result = questionnaire.finish_session(sender_id)
                if result:
                    await questionnaire.dump_result_and_save_text(
                        result, client, candidate_entity=candidate_user_id
                    )

                await _start_next_candidate()

        if not command_mode and candidates_list:
            # Старт первого кандидата после инициализации
            client.loop.create_task(_start_next_candidate())

        client.run_until_disconnected()

    except PhoneNumberInvalidError:
        log.error("Неверный формат номера телефона")
        print("Ошибка: неверный формат номера телефона.")
    except FloodWaitError as e:
        log.error("FloodWait: %s секунд", e.seconds)
        print(f"Ожидание {e.seconds} с (ограничение Telegram).")
    except KeyboardInterrupt:
        log.info("Остановлено по Ctrl+C")
        print("\nОстановлено.")
    except Exception as e:
        log.exception("Неожиданная ошибка")
        print(f"Ошибка: {e}")
    finally:
        if command_mode and cmd_log:
            cmd_log.info("конец сеанса command_mode")
        client.disconnect()
        print("Клиент отключён.")
