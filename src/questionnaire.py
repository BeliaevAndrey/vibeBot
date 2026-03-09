"""
Опросник: состояние по кандидату, report, red_flags, оценка ответов, итог.
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Any

from config import (
    HR_ACCOUNT,
    CANDIDATE_USERNAME,
    SAVE_RESULTS_TO_FILES,
    VACANCY_API_KEY,
    VACANCY_TOP_N,
    GREETINGS_PATH,
    COMPANY_DATA_PATH,
    QUESTIONS_PATH,
    RESULTS_JSON_DIR,
    RESULTS_TEXT_DIR,
    TOGGLE_DELAY,
    setup_logging,
)
from . import openai_client
from .human_delay import human_like_delay
from .vacancies import (
    enrich_offerings,
    filter_from_short,
    format_top_vacancies_report,
    generate_filter,
    get_job_offerings,
    get_places,
    split_vacancy_messages,
)

setup_logging()
log = logging.getLogger("userbot")

UTC_PLUS_3 = timezone(timedelta(hours=3))

# Состояние опросника по user_id (int)
_state: dict[int, dict[str, Any]] = {}

# Состояние диалога по вакансиям после отправки описания (по user_id)
# Содержит:
# - appropriate: id подходящей вакансии или None
# - inappropriate: список id явно неподходящих вакансий
# - vacancies_by_id: словарь {id: вакансия}
# - ordered_ids: список id в порядке выдачи
# - current_index/current_vacancy_id: позиция текущей вакансии
# - history: список событий (кандидат/LLM, текст, vacancy_id, analysis_result, timestamp)
# - dump_meta: данные для сохранения (id_value, ts_key, started_at)
_dialogue_state: dict[int, dict[str, Any]] = {}

# Тексты для ответов бота
GOODBYE_DECLINED = "Спасибо за ответ. Если передумаете — мы всегда рады. Всего доброго!"
GOODBYE_EARLY = "К сожалению, мы вынуждены завершить опрос. Спасибо за уделенное время."
REPEAT_ANSWER = "Пожалуйста, ответьте ещё раз, избегая грубых выражений."


def _load_greetings() -> list[str]:
    """Загрузить приветствия: файл — объект {"1": текст, "2": текст, ...}, возвращаем список текстов."""
    with open(GREETINGS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return list(data.values())
    return list(data)


def _load_company_data() -> dict[str, str]:
    """Загрузить company_data.json (company, position, hr_name)."""
    with open(COMPANY_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _substitute_greeting_placeholders(text: str, candidate_username: str | None = None) -> str:
    """
    Подставить в приветствие плейсхолдеры:
    {name} — @username кандидата (если передан candidate_username);
    {company}, {position}, {hr_name} — из resource/json/company_data.json.
    """
    company_data = _load_company_data()
    name_value = f"@{candidate_username}" if candidate_username else ""
    replacements = {
        "{name}": name_value,
        "{company}": company_data.get("company", ""),
        "{position}": company_data.get("position", ""),
        "{hr_name}": company_data.get("hr_name", ""),
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text


def _load_questions() -> list[dict[str, Any]]:
    """Вопросы: массив [ {"question": "...", "acceptance": "..."}, ... ]."""
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []


def _ensure_results_dirs() -> None:
    RESULTS_JSON_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_TEXT_DIR.mkdir(parents=True, exist_ok=True)


def _append_dialogue_history(
    user_id: int,
    *,
    author: str,
    text: str,
    vacancy_id: int | None = None,
    analysis_result: int | None = None,
) -> None:
    """Добавить событие в историю диалога по вакансиям."""
    state = _dialogue_state.get(user_id)
    if not state:
        return
    history: list[dict[str, Any]] = state.setdefault("history", [])
    history.append(
        {
            "timestamp": datetime.now(UTC_PLUS_3).isoformat(),
            "author": author,
            "text": text,
            "vacancy_id": vacancy_id,
            "analysis_result": analysis_result,
        }
    )


def get_dialogue_state(user_id: int) -> dict[str, Any] | None:
    """Получить состояние диалога по вакансиям для пользователя, если оно есть."""
    return _dialogue_state.get(user_id)


def _get_fio_from_short(short: dict[str, Any]) -> tuple[str, str]:
    """Из выжимки short (full_name, first_name, patronymic) — полное ФИО и обращение «Имя Отчество»."""
    full = (short.get("full_name") or "").strip()
    first = (short.get("first_name") or "").strip()
    pat = (short.get("patronymic") or "").strip()
    name_pat = f"{first} {pat}".strip() or full
    return full, name_pat


def _format_report_date(iso_date: str | None) -> str:
    """Преобразовать дату из ISO в вид 'YYYY-mm-dd HH:MM (МСК)' для отчёта."""
    if not iso_date:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M") + " (МСК)"
    except (ValueError, TypeError):
        return iso_date or "—"


_MAX_VACANCY_MSG_LEN = 4000  # оставлен на случай дальнейшего использования в этом модуле


def get_greeting(candidate_username: str | None = None) -> str:
    """
    Случайное приветствие с подстановкой плейсхолдеров.
    candidate_username — username кандидата без @ для подстановки в {name}.
    """
    import random
    greetings = _load_greetings()
    text = random.choice(greetings)
    return _substitute_greeting_placeholders(text, candidate_username)


def get_question_keys() -> list[str]:
    """Индексы вопросов: ["0", "1", ...]."""
    questions = _load_questions()
    return [str(i) for i in range(len(questions))]


def get_question_text(q_key: str) -> str:
    questions = _load_questions()
    idx = int(q_key)
    if idx < 0 or idx >= len(questions):
        return ""
    return questions[idx].get("question", "")


def get_question_full(q_key: str) -> dict[str, Any]:
    questions = _load_questions()
    idx = int(q_key)
    if idx < 0 or idx >= len(questions):
        return {}
    return questions[idx]


def is_candidate(user_id: int, username: str | None) -> bool:
    """Проверить, что пользователь — текущий кандидат (по CANDIDATE_USERNAME)."""
    if not CANDIDATE_USERNAME:
        return False
    ref = CANDIDATE_USERNAME.lstrip("@").lower()
    if username:
        if username.lower() == ref:
            return True
    # По user_id мы не можем сопоставить без entity; вызывающий код передаёт username
    return False


def get_state(user_id: int) -> dict[str, Any] | None:
    return _state.get(user_id)


def init_session(user_id: int, username: str | None = None) -> None:
    """Начать сессию опросника для пользователя (после отправки приветствия)."""
    _state[user_id] = {
        "state": "greeting_sent",
        "report": [],
        "red_flags": 0,
        "current_q_index": 0,
        "question_keys": get_question_keys(),
        "username": username,
    }


async def handle_agreement(user_id: int, username: str | None, message_text: str) -> tuple[str, bool]:
    """
    Обработать ответ после приветствия (согласие/отказ).
    Возвращает (текст ответа бота, закончена_ли сессия).
    """
    state = _state.get(user_id)
    if not state or state["state"] != "greeting_sent":
        return ("", False)

    state["username"] = username or state.get("username")
    agreed = await asyncio.to_thread(openai_client.evaluate_agreement, message_text)
    if not agreed:
        state["state"] = "declined"
        return (GOODBYE_DECLINED, True)

    state["state"] = "asking"
    state["current_q_index"] = 0
    keys = state["question_keys"]
    if not keys:
        state["state"] = "completed"
        return ("Вопросов нет. Спасибо!", True)
    first_q = get_question_text(keys[0])
    # В диалоге отправляем только текст вопроса (без префикса «Вопрос N»)
    return (first_q, False)


async def handle_answer(
    user_id: int,
    username: str | None,
    message_text: str,
) -> tuple[str, bool]:
    """
    Обработать ответ на вопрос через validate_answer.
    Возвращает (текст ответа бота, закончена_ли сессия).
    """
    state = _state.get(user_id)
    if not state or state["state"] != "asking":
        return ("", False)

    state["username"] = username or state.get("username")
    idx = state["current_q_index"]
    keys = state["question_keys"]
    if idx >= len(keys):
        state["state"] = "completed"
        return ("", True)

    q_key = keys[idx]
    q_full = get_question_full(q_key)
    question_text = q_full.get("question", "")
    acceptance_criteria = q_full.get("acceptance", "")

    valid, human_response = await asyncio.to_thread(
        openai_client.validate_answer,
        question_text,
        message_text,
        acceptance_criteria,
    )

    state["report"].append({
        "q_number": q_key,
        "question": question_text,
        "answer": message_text,
        "comment": human_response if not valid else "",
        "profanity_detected": False,
        "invalid": not valid,
    })

    if not valid:
        return (human_response or REPEAT_ANSWER, False)

    state["current_q_index"] = idx + 1
    if state["current_q_index"] >= len(keys):
        state["state"] = "completed"
        return ("Спасибо! Опрос завершён.", True)

    next_q_key = keys[state["current_q_index"]]
    next_q = get_question_text(next_q_key)
    # В диалоге отправляем только текст вопроса
    return (next_q, False)


def build_questionnaire_result_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Собрать итоговый словарь questionnaire_result из state."""
    report = state.get("report", [])
    questions_dict = {}
    for r in report:
        qn = r["q_number"]
        if qn not in questions_dict:
            questions_dict[qn] = {
                "question": r["question"],
                "answer": r["answer"],
            }
        else:
            questions_dict[qn]["answer"] = r["answer"]
        # comment добавляем только если он непустой
        comment = r.get("comment") or ""
        if comment:
            questions_dict[qn]["comment"] = comment
        if r.get("profanity_detected") or r.get("invalid"):
            questions_dict[qn]["rejected_answer"] = r["answer"]

    profanity_detected = state.get("red_flags", 0) > 1 or any(
        r.get("profanity_detected") for r in report
    )
    if state.get("state") == "early_exit":
        profanity_detected = True

    now = datetime.now(UTC_PLUS_3)
    return {
        "user": state.get("username") or "unknown",
        "date": now.isoformat(),
        "questions": questions_dict,
        "profanity_detected": profanity_detected,
    }


async def dump_result_and_save_text(
    result: dict[str, Any],
    client: Any,
    send_to_hr: bool = True,
    hr_account: str | None = None,
    candidate_entity: int | str | None = None,
    candidate_phone: str | None = None,
) -> str:
    """
    Дамп questionnaire_result в questionnaire_results/json,
    сформировать текст отчёта, сохранить в questionnaire_results/text/,
    при необходимости переслать в ЛС HR; отчёт по 1 вакансии — также кандидату (отдельным текстом), если передан candidate_entity.
    Возвращает путь к сохранённому txt.
    """
    _ensure_results_dirs()
    user_label = result.get("user", "unknown").replace("@", "")
    now = datetime.now(UTC_PLUS_3)
    ts = now.strftime("%Y_%m_%d-%H_%M")
    safe_ts = ts.replace("-", "_")

    lines = [
        f"Опросник: {result.get('user')}",
        f"Дата: {_format_report_date(result.get('date'))}",
        "",
    ]
    if result.get("profanity_detected"):
        lines.append("Причина раннего завершения: грубость/брань в ответах.")
        lines.append("")

    for q_num, q_data in result.get("questions", {}).items():
        num_display = int(q_num) + 1 if str(q_num).isdigit() else q_num
        lines.append(f"Вопрос {num_display}: {q_data.get('question', '')}")
        lines.append(f"Ответ: {q_data.get('answer', '')}")
        if q_data.get("rejected_answer"):
            lines.append(f"Некорректный ответ (red_flag): {q_data['rejected_answer']}")
        if q_data.get("comment"):
            lines.append(f"Комментарий: {q_data['comment']}")
        lines.append("")

    text_body = "\n".join(lines)
    text_filename = f"{user_label}_{ts}.txt"
    text_path = RESULTS_TEXT_DIR / text_filename

    if SAVE_RESULTS_TO_FILES:
        json_path = RESULTS_JSON_DIR / f"{user_label}_{safe_ts}.json"
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.exception("Save questionnaire JSON failed: %s", e)
        try:
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(text_body)
        except Exception as e:
            log.exception("Save questionnaire TXT failed: %s", e)

    hr = (hr_account or HR_ACCOUNT) or ""
    if send_to_hr and hr and client:
        try:
            await client.send_message(hr, text_body)
        except Exception as e:
            log.exception("Send to HR failed: %s", e)
            print(f"Отчёт не отправлен HR_ACCOUNT={hr}: {e}")
    else:
        if not send_to_hr:
            print("Отчёт не отправлен: отправка отключена (send_to_hr=False)")
        elif not hr:
            print("Отчёт не отправлен: не задан HR_ACCOUNT")
        elif not client:
            print("Отчёт не отправлен: клиент Telegram не инициализирован")

    # Короткая выжимка (short) — передаём напрямую в загрузку вакансий; сохранение в файл только для истории
    short = None
    try:
        short = await asyncio.to_thread(openai_client.summarize_questionnaire, result)
        print("Краткая выжимка опроса:", short)
    except Exception as e:
        log.exception("Short summary failed: %s", e)

    if SAVE_RESULTS_TO_FILES and short is not None:
        # Старый формат: один файл на запуск (для истории)
        try:
            short_path = RESULTS_JSON_DIR / f"short_{user_label}_{safe_ts}.json"
            with open(short_path, "w", encoding="utf-8") as f:
                json.dump(short, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.exception("Save short summary failed: %s", e)

        # Новый агрегированный формат: { (id, datetime): short_with_phone }
        try:
            agg_path = RESULTS_JSON_DIR / "short.json"
            if agg_path.exists():
                with open(agg_path, "r", encoding="utf-8") as f:
                    agg: dict[str, Any] = json.load(f)
            else:
                agg = {}

            # Идентификатор кандидата в ключе: @username или телефон, если username нет
            id_value = result.get("user") or candidate_phone or "unknown"
            # Дата-время в ключе: "YYYY-mm-dd HH:MM"
            ts_key = now.strftime("%Y-%m-%d %H:%M")
            dict_key = f"({id_value}, {ts_key})"

            entry = dict(short)
            if candidate_phone:
                entry["phone"] = candidate_phone

            agg[dict_key] = entry
            with open(agg_path, "w", encoding="utf-8") as f:
                json.dump(agg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.exception("Save aggregated short.json failed: %s", e)

    # Автозагрузка вакансий по short: описание 1-й вакансии — HR напрямую; сохранение в файл только для истории
    offerings: list[dict[str, Any]] = []
    report_text: str | None = None
    total_count: int = 0

    if short is not None and VACANCY_API_KEY and hr and client:
        def _fetch_and_report() -> tuple[list, str | None, int]:
            places_resp = get_places()
            places = places_resp.get("data", [])
            flat = filter_from_short(short, places)
            if not flat:
                return [], None, 0
            filter_dict = generate_filter(flat)
            raw = get_job_offerings(filter_dict=filter_dict)
            offerings_local = enrich_offerings(raw, places)
            meta = raw.get("meta") or {}
            print(meta)
            total_count_local = meta.get("count") or len(offerings_local)
            report_local = (
                format_top_vacancies_report(offerings_local, top_n=VACANCY_TOP_N)
                if offerings_local
                else None
            )
            return offerings_local, report_local, total_count_local

        try:
            offerings, report_text, total_count = await asyncio.to_thread(_fetch_and_report)
        except Exception as e:
            log.exception("Vacancy fetch failed: %s", e)
            offerings = []
            report_text = None
            total_count = 0

        print(f"Всего найдено вакансий: {total_count}")

        if not offerings or total_count == 0:
            try:
                # TODO: заменить на более содержательное уведомление HR
                # о причинах отсутствия подходящих вакансий и вариантах дальнейших действий.
                await client.send_message(hr, "Подходящие вакансии не найдены.")
            except Exception as e:
                log.exception("Send 'no vacancies found' notice to HR failed: %s", e)

        if report_text:
            try:
                candidate_display = result.get("user", "unknown")
                if candidate_display and not str(candidate_display).startswith("@"):
                    candidate_display = f"@{candidate_display}"
                full_fio, name_patronymic = _get_fio_from_short(short)
                date_str = _format_report_date(result.get("date"))
                hr_fio_part = f" ({full_fio})" if full_fio else ""
                hr_header = (
                    f"Вакансия для кандидата {candidate_display}{hr_fio_part}. "
                    f"Дата опроса: {date_str}. Всего найдено вакансий: {total_count}."
                )
                # Шапка отдельным сообщением
                await client.send_message(hr, hr_header)
                print(f"Отчёт по вакансиям (шапка) отправлен HR {hr}")

                # Тело вакансии (вакансия + футер) — отдельное сообщение/сообщения
                vacancy_parts = split_vacancy_messages(report_text)
                # Задержка между шапкой и телом 5–10 секунд
                await asyncio.sleep(random.randint(5, 10))
                for idx_part, part in enumerate(vacancy_parts):
                    await client.send_message(hr, part)
                    if idx_part < len(vacancy_parts) - 1:
                        # Задержка между сообщениями тела 4–5 секунд
                        await asyncio.sleep(random.randint(4, 5))
                print(f"Отчёт по вакансиям отправлен HR {hr}")
                if name_patronymic:
                    candidate_intro = (
                        f"{name_patronymic}, подобрали Вам вакансию, высылаем описание. "
                        "Можем обсудить другие варианты вакансий."
                    )
                else:
                    candidate_intro = (
                        "Подобрали Вам вакансию, высылаем описание. "
                        "Можем обсудить другие варианты вакансий."
                    )

                vacancy_parts_candidate = split_vacancy_messages(report_text)

                if candidate_entity is not None and client:
                    try:
                        if name_patronymic:
                            wait_msg = (
                                f"{name_patronymic}, подождите 2-3 минуты, пожалуйста. "
                                "Подберу Вам образец вакансии."
                            )   # TODO: уточнить формулировку!
                        else:
                            wait_msg = (
                                "Подождите 2-3 минуты, пожалуйста. "
                                "Подберу Вам образец вакансии."
                            )   # TODO: уточнить формулировку!
                        # Сообщение «подождите 2–3 минуты» с human_like_delay
                        await human_like_delay(client, candidate_entity, wait_msg)
                        await client.send_message(candidate_entity, wait_msg)

                        # Задержка на «поиск вакансии» остаётся
                        if TOGGLE_DELAY != "OFF":
                            wait_sec = random.randint(120, 180) + random.randint(1, 40)
                            await asyncio.sleep(wait_sec)

                        # Шапка кандидату отдельным сообщением
                        if TOGGLE_DELAY != "OFF":
                            await human_like_delay(client, candidate_entity, candidate_intro)
                        await client.send_message(candidate_entity, candidate_intro)

                        # Задержка 5–10 сек как на вставку из буфера
                        await asyncio.sleep(random.randint(5, 10))

                        # Тело вакансии (вакансия + футер) — одно или несколько сообщений,
                        # без имитации набора (HR не «перепечатывает» текст вакансии).
                        for idx_part, part in enumerate(vacancy_parts_candidate):
                            await client.send_message(candidate_entity, part)
                            if idx_part < len(vacancy_parts_candidate) - 1:
                                # Задержка между сообщениями тела 4–5 секунд (как «вставка из буфера»)
                                await asyncio.sleep(random.randint(4, 5))

                        print(f"Отчёт по вакансиям отправлен кандидату {candidate_entity}")
                        # Инициализируем диалог по вакансиям для кандидата:
                        # список найденных вакансий, текущая (первая) вакансия,
                        # история сообщений и метаданные для дампа.
                        try:
                            if isinstance(candidate_entity, int):
                                user_id_for_dialogue = candidate_entity
                            else:
                                # Если идентификатор не int, диалог по user_id не ведём
                                user_id_for_dialogue = None
                            if user_id_for_dialogue is not None and offerings:
                                id_value = result.get("user") or candidate_phone or "unknown"
                                started_at = datetime.now(UTC_PLUS_3)
                                ts_key = started_at.strftime("%Y-%m-%d %H:%M")
                                vacancies_by_id: dict[int, dict[str, Any]] = {}
                                ordered_ids: list[int] = []
                                for vac in offerings:
                                    vid = vac.get("id")
                                    if isinstance(vid, int):
                                        vacancies_by_id[vid] = vac
                                        ordered_ids.append(vid)
                                current_vacancy_id = ordered_ids[0] if ordered_ids else None
                                _dialogue_state[user_id_for_dialogue] = {
                                    "appropriate": None,
                                    "inappropriate": [],
                                    "vacancies_by_id": vacancies_by_id,
                                    "ordered_ids": ordered_ids,
                                    "current_index": 0,
                                    "current_vacancy_id": current_vacancy_id,
                                    "history": [],
                                    "pending_next_vacancy": False,
                                    "dump_meta": {
                                        "id_value": id_value,
                                        "ts_key": ts_key,
                                        "started_at": started_at.isoformat(),
                                    },
                                }
                                # Сохраняем факт отправки вводного сообщения кандидату
                                _append_dialogue_history(
                                    user_id_for_dialogue,
                                    author="system",
                                    text=wait_msg,
                                    vacancy_id=None,
                                )
                                _append_dialogue_history(
                                    user_id_for_dialogue,
                                    author="system",
                                    text=candidate_intro,
                                    vacancy_id=current_vacancy_id,
                                )
                                # Первый вопрос об удовлетворённости вакансией — сразу после отправки описания
                                try:
                                    satisfaction_question = openai_client.generate_satisfaction_question(
                                        report_text
                                    )
                                except Exception as e:
                                    log.exception(
                                        "Generate satisfaction question failed: %s", e
                                    )
                                    satisfaction_question = (
                                        "Как вы оцениваете эту вакансию по условиям работы и требованиям? "
                                        "Подходит ли она вам?"
                                    )
                                _append_dialogue_history(
                                    user_id_for_dialogue,
                                    author="llm",
                                    text=satisfaction_question,
                                    vacancy_id=current_vacancy_id,
                                )
                                if TOGGLE_DELAY != "OFF":
                                    await human_like_delay(
                                        client, candidate_entity, satisfaction_question
                                    )
                                await client.send_message(
                                    candidate_entity, satisfaction_question
                                )
                        except Exception as e:
                            log.exception("Init vacancy dialogue state failed: %s", e)
                    except Exception as e:
                        log.exception("Send vacancy report to candidate failed: %s", e)
            except Exception as e:
                log.exception("Vacancy report send failed: %s", e)

    # Dump вакансий — полностью отвязано от отправки сообщений
    if SAVE_RESULTS_TO_FILES and offerings:
        # Старый формат: список вакансий для одного запуска
        vac_path = RESULTS_JSON_DIR / f"vacancies_{user_label}_{safe_ts}.json"
        try:
            with open(vac_path, "w", encoding="utf-8") as f:
                json.dump(offerings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.exception("Save vacancies.json failed: %s", e)

        # Новый агрегированный формат: { (id, datetime): [вакансии] }
        try:
            agg_vac_path = RESULTS_JSON_DIR / "vacancies.json"
            if agg_vac_path.exists():
                with open(agg_vac_path, "r", encoding="utf-8") as f:
                    agg_vac: dict[str, Any] = json.load(f)
            else:
                agg_vac = {}

            id_value = result.get("user") or candidate_phone or "unknown"
            ts_key = now.strftime("%Y-%m-%d %H:%M")
            dict_key = f"({id_value}, {ts_key})"

            agg_vac[dict_key] = offerings
            with open(agg_vac_path, "w", encoding="utf-8") as f:
                json.dump(agg_vac, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.exception("Save aggregated vacancies.json failed: %s", e)

    return str(text_path)


def finish_session(user_id: int) -> dict[str, Any] | None:
    """Взять результат и очистить сессию. Возвращает questionnaire_result или None."""
    state = _state.pop(user_id, None)
    if not state:
        return None
    return build_questionnaire_result_from_state(state)


def _dump_dialogue_to_file(user_id: int) -> None:
    """Сохранить состояние диалога по вакансиям в JSON (агрегированный формат)."""
    state = _dialogue_state.get(user_id)
    if not state:
        return
    if not SAVE_RESULTS_TO_FILES:
        return
    try:
        RESULTS_JSON_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_JSON_DIR / "vacancy_dialogues.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        else:
            data = {}
        dump_meta = state.get("dump_meta", {})
        id_value = dump_meta.get("id_value", "unknown")
        ts_key = dump_meta.get("ts_key") or datetime.now(UTC_PLUS_3).strftime("%Y-%m-%d %H:%M")
        dict_key = f"({id_value}, {ts_key})"
        # Подготовим компактное состояние для дампа
        to_save = {
            "appropriate": state.get("appropriate"),
            "inappropriate": state.get("inappropriate", []),
            "ordered_ids": state.get("ordered_ids", []),
            "history": state.get("history", []),
        }
        # Для vacancies_by_id сохраняем как словарь {id: {...}}
        vacancies_by_id = state.get("vacancies_by_id") or {}
        to_save["vacancies_by_id"] = vacancies_by_id
        data[dict_key] = to_save
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.exception("Save vacancy_dialogues.json failed: %s", e)


def _log_dialogue_finished(user_id: int, reason: str) -> None:
    """Логирование полного окончания диалога по вакансиям с кандидатом."""
    msg = f"Диалог по вакансиям с кандидатом user_id={user_id} завершён: {reason}"
    log.info(msg)
    print(msg)


async def handle_vacancy_dialogue_message(
    user_id: int,
    message_text: str,
    client: Any,
) -> bool:
    """
    Обработать сообщение кандидата в рамках диалога по вакансиям.
    Возвращает True, если сообщение обработано как часть диалога.
    """
    state = _dialogue_state.get(user_id)
    if not state:
        return False

    current_vacancy_id = state.get("current_vacancy_id")
    ordered_ids: list[int] = state.get("ordered_ids") or []
    vacancies_by_id: dict[int, dict[str, Any]] = state.get("vacancies_by_id") or {}

    # Записываем сообщение кандидата в историю
    _append_dialogue_history(
        user_id,
        author="candidate",
        text=message_text,
        vacancy_id=current_vacancy_id,
    )

    if current_vacancy_id is None or current_vacancy_id not in vacancies_by_id:
        # Нет актуальной вакансии — завершим диалог
        _dump_dialogue_to_file(user_id)
        _dialogue_state.pop(user_id, None)
        _log_dialogue_finished(user_id, "нет актуальной вакансии в состоянии диалога")
        return True

    vacancy = vacancies_by_id[current_vacancy_id]
    vacancy_desc = vacancy.get("description_text") or ""

    # Анализируем ответ кандидата через LLM
    analysis = openai_client.analyze_vacancy_reply(
        vacancy_description=vacancy_desc,
        candidate_message=message_text,
        history=state.get("history"),
    )
    analysis_result = int(analysis.get("analysis_result", 4))
    reply_text = analysis.get("reply_text", "") or ""

    # Сохраняем ответ LLM в историю
    _append_dialogue_history(
        user_id,
        author="llm",
        text=reply_text,
        vacancy_id=current_vacancy_id,
        analysis_result=analysis_result,
    )

    # Отправляем ответ кандидату
    try:
        await client.send_message(user_id, reply_text)
    except Exception as e:
        log.exception("Send dialogue reply to candidate failed: %s", e)

    inappropriate: list[int] = state.setdefault("inappropriate", [])

    # Обработка результата анализа
    if analysis_result == 1:
        # Чёткий отказ — помечаем вакансию как неподходящую и ждём пояснения кандидата.
        # Новую вакансию НЕ отправляем сразу, только после следующего сообщения.
        if current_vacancy_id not in inappropriate:
            inappropriate.append(current_vacancy_id)
        state["pending_next_vacancy"] = True
        return True

    if analysis_result == 3:
        # Явное удовлетворение — фиксируем вакансию как подходящую и завершаем диалог
        state["appropriate"] = current_vacancy_id
        _dump_dialogue_to_file(user_id)
        _dialogue_state.pop(user_id, None)
        _log_dialogue_finished(user_id, "кандидат явно удовлетворён вакансией")
        return True

    # Если ранее был зафиксирован отказ и мы ожидали пояснение,
    # а сейчас пришёл очередной ответ (analysis_result != 1),
    # можно переходить к следующей вакансии (если она есть).
    if state.get("pending_next_vacancy") and analysis_result != 1:
        next_id: int | None = None
        for vid in ordered_ids:
            if vid == current_vacancy_id:
                continue
            if vid in inappropriate:
                continue
            if state.get("appropriate") == vid:
                continue
            next_id = vid
            break

        if next_id is None:
            # Вакансий больше нет — отправляем вежливое сообщение и завершаем диалог
            no_more = openai_client.generate_no_more_vacancies_message()
            _append_dialogue_history(
                user_id,
                author="llm",
                text=no_more,
                vacancy_id=None,
                analysis_result=None,
            )
            try:
                await client.send_message(user_id, no_more)
            except Exception as e:
                log.exception("Send 'no more vacancies' message failed: %s", e)
            _dump_dialogue_to_file(user_id)
            _dialogue_state.pop(user_id, None)
            _log_dialogue_finished(user_id, "подходящих вакансий больше нет")
            return True

        state["pending_next_vacancy"] = False
        # Предлагаем следующую вакансию и задаём новый вопрос об удовлетворённости
        state["current_vacancy_id"] = next_id
        vacancy_next = vacancies_by_id[next_id]
        report_for_next = format_top_vacancies_report([vacancy_next], top_n=1)
        vacancy_parts = split_vacancy_messages(report_for_next)
        try:
            for idx, part in enumerate(vacancy_parts):
                await client.send_message(user_id, part)
                if idx < len(vacancy_parts) - 1:
                    await asyncio.sleep(random.randint(4, 5))
        except Exception as e:
            log.exception("Send next vacancy to candidate failed: %s", e)

        question = openai_client.generate_satisfaction_question(report_for_next)
        _append_dialogue_history(
            user_id,
            author="llm",
            text=question,
            vacancy_id=next_id,
            analysis_result=None,
        )
        try:
            await client.send_message(user_id, question)
        except Exception as e:
            log.exception("Send satisfaction question for next vacancy failed: %s", e)
        return True

    # 2 — ответ на вопросы, 4 — требуется пояснение:
    # просто продолжаем диалог по той же вакансии
    return True
