"""
Опросник: состояние по кандидату, report, red_flags, оценка ответов, итог.
"""

import asyncio
import json
import logging
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
    setup_logging,
)
from . import openai_client
from .vacancies import (
    enrich_offerings,
    filter_from_short,
    format_top_vacancies_report,
    generate_filter,
    get_job_offerings,
    get_places,
)

setup_logging()
log = logging.getLogger("userbot")

UTC_PLUS_3 = timezone(timedelta(hours=3))

# Состояние опросника по user_id (int)
_state: dict[int, dict[str, Any]] = {}

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
    return (f"Вопрос 1.\n{first_q}", False)


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
    num = state["current_q_index"] + 1
    return (f"Вопрос {num}.\n{next_q}", False)


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
        try:
            short_path = RESULTS_JSON_DIR / f"short_{user_label}_{safe_ts}.json"
            with open(short_path, "w", encoding="utf-8") as f:
                json.dump(short, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.exception("Save short summary failed: %s", e)

    # Автозагрузка вакансий по short: описание 1-й вакансии — HR напрямую; сохранение в файл только для истории
    if short is not None and VACANCY_API_KEY and hr and client:
        try:
            def _fetch_and_report() -> tuple[list, str | None, int]:
                places_resp = get_places()
                places = places_resp.get("data", [])
                flat = filter_from_short(short, places)
                if not flat:
                    return [], None, 0
                filter_dict = generate_filter(flat)
                raw = get_job_offerings(filter_dict=filter_dict)
                offerings = enrich_offerings(raw, places)
                meta = raw.get("meta") or {}
                total_count = meta.get("totalCount") or len(offerings)
                report = format_top_vacancies_report(offerings, top_n=VACANCY_TOP_N) if offerings else None
                return offerings, report, total_count

            offerings, report_text, total_count = await asyncio.to_thread(_fetch_and_report)
            print(f"Всего найдено вакансий: {total_count}")
            if report_text:
                candidate_display = result.get("user", "unknown")
                if candidate_display and not str(candidate_display).startswith("@"):
                    candidate_display = f"@{candidate_display}"
                full_fio, name_patronymic = _get_fio_from_short(short)
                date_str = _format_report_date(result.get("date"))
                hr_fio_part = f" ({full_fio})" if full_fio else ""
                msg_hr = (
                    f"Вакансия для кандидата {candidate_display}{hr_fio_part}. "
                    f"Дата опроса: {date_str}. Всего найдено вакансий: {total_count}.\n\n"
                    f"{report_text}"
                )
                await client.send_message(hr, msg_hr)
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
                msg_candidate = f"{candidate_intro}\n\n{report_text}"
                if candidate_entity is not None and client:
                    try:
                        await client.send_message(candidate_entity, msg_candidate)
                        print(f"Отчёт по вакансиям отправлен кандидату {candidate_entity.username}")
                    except Exception as e:
                        log.exception("Send vacancy report to candidate failed: %s", e)
            if SAVE_RESULTS_TO_FILES and offerings:
                vac_path = RESULTS_JSON_DIR / f"vacancies_{user_label}_{safe_ts}.json"
                try:
                    with open(vac_path, "w", encoding="utf-8") as f:
                        json.dump(offerings, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    log.exception("Save vacancies.json failed: %s", e)
        except Exception as e:
            log.exception("Vacancy fetch/report failed: %s", e)

    return str(text_path)


def finish_session(user_id: int) -> dict[str, Any] | None:
    """Взять результат и очистить сессию. Возвращает questionnaire_result или None."""
    state = _state.pop(user_id, None)
    if not state:
        return None
    return build_questionnaire_result_from_state(state)
