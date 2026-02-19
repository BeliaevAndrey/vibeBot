"""
Опросник: состояние по кандидату, report, red_flags, оценка ответов, итог.
"""

import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from config import HR_ACCOUNT, CANDIDATE_USERNAME
from . import openai_client
from .logger import get_logger

log = get_logger()

_RESOURCE_DIR = Path(__file__).resolve().parent.parent / "resource"
_GREETINGS_PATH = _RESOURCE_DIR / "json" / "greetings.json"
_COMPANY_DATA_PATH = _RESOURCE_DIR / "json" / "company_data.json"
_QUESTIONS_PATH = _RESOURCE_DIR / "json" / "questions.json"
_PROMPT_PATH = _RESOURCE_DIR / "prompts" / "question_prompt.txt"
_RESULTS_JSON_DIR = Path("questionnaire_results") / "json"
_RESULTS_TEXT_DIR = Path("questionnaire_results") / "text"

UTC_PLUS_3 = timezone(timedelta(hours=3))

# Состояние опросника по user_id (int)
_state: dict[int, dict[str, Any]] = {}

# Тексты для ответов бота
GOODBYE_DECLINED = "Спасибо за ответ. Если передумаете — мы всегда рады. Всего доброго!"
GOODBYE_EARLY = "К сожалению, мы вынуждены завершить опрос. Спасибо за уделенное время."
REPEAT_ANSWER = "Пожалуйста, ответьте ещё раз, избегая грубых выражений."


def _load_greetings() -> list[str]:
    """Загрузить приветствия: файл — объект {"1": текст, "2": текст, ...}, возвращаем список текстов."""
    with open(_GREETINGS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return list(data.values())
    return list(data)


def _load_company_data() -> dict[str, str]:
    """Загрузить company_data.json (company, position, hr_name)."""
    with open(_COMPANY_DATA_PATH, encoding="utf-8") as f:
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


def _load_questions() -> dict[str, Any]:
    with open(_QUESTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_prompt_template() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def _ensure_results_dirs() -> None:
    _RESULTS_JSON_DIR.mkdir(parents=True, exist_ok=True)
    _RESULTS_TEXT_DIR.mkdir(parents=True, exist_ok=True)


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Извлечь JSON из ответа LLM (возможен блок ```json ... ```)."""
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if match:
        raw = match.group(1).strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        return json.loads(match.group(0))
    return json.loads(raw)


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
    return sorted(_load_questions().keys(), key=int)


def get_question_text(q_key: str) -> str:
    q = _load_questions()[q_key]
    return q.get("question", "")


def get_question_full(q_key: str) -> dict[str, Any]:
    return _load_questions()[q_key]


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
    Обработать ответ на вопрос. Вызов LLM через asyncio.to_thread.
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
    question_title = q_full.get("title", q_key)
    criteria = q_full.get("criteria", [])
    criteria_list = "\n".join(f"- {c}" for c in criteria)

    template = _load_prompt_template()
    prompt = template.format(
        question_title=question_title,
        question_text=question_text,
        candidate_answer=message_text,
        criteria_list=criteria_list,
    )

    raw = await asyncio.to_thread(openai_client.get_completion, prompt)
    try:
        parsed = _parse_llm_json(raw)
    except (json.JSONDecodeError, KeyError) as e:
        log.exception("LLM JSON parse error: %s", e)
        return ("Произошла ошибка при оценке ответа. Пожалуйста, ответьте ещё раз.", False)

    profanity = parsed.get("profanity_detected", False)
    compliance_percent = int(parsed.get("compliance_percent", 0))
    summary_comment = parsed.get("summary_comment", "") or ""

    state["report"].append({
        "q_number": q_key,
        "question": question_text,
        "answer": message_text,
        "compliance_percent": compliance_percent,
        "comment": summary_comment,
        "profanity_detected": profanity,
    })

    if profanity:
        state["red_flags"] = state.get("red_flags", 0) + 1
        if state["red_flags"] > 1:
            state["state"] = "early_exit"
            return (GOODBYE_EARLY, True)
        return (REPEAT_ANSWER, False)

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
        questions_dict[qn] = {
            "question": r["question"],
            "answer": r["answer"],
            "compliance": r["compliance_percent"],
            "comment": r.get("comment") or "",
        }

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


def dump_result_and_save_text(
    result: dict[str, Any],
    client: Any,
    send_to_hr: bool = True,
) -> str:
    """
    Дамп questionnaire_result в questionnaire_results/json,
    сформировать текст отчёта, сохранить в questionnaire_results/text/,
    при необходимости переслать в ЛС HR. Возвращает путь к сохранённому txt.
    """
    _ensure_results_dirs()
    user_label = result.get("user", "unknown").replace("@", "")
    now = datetime.now(UTC_PLUS_3)
    ts = now.strftime("%Y_%m_%d-%H_%M")

    json_path = _RESULTS_JSON_DIR / f"{user_label}_{ts.replace('-', '_')}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    lines = [
        f"Опросник: {result.get('user')}",
        f"Дата: {result.get('date')}",
        "",
    ]
    if result.get("profanity_detected"):
        lines.append("Причина раннего завершения: грубость/брань в ответах.")
        lines.append("")

    for q_num, q_data in result.get("questions", {}).items():
        lines.append(f"Вопрос {q_num}: {q_data.get('question', '')}")
        lines.append(f"Ответ: {q_data.get('answer', '')}")
        lines.append(f"Соответствие: {q_data.get('compliance', 0)}%")
        if q_data.get("comment"):
            lines.append(f"Комментарий: {q_data['comment']}")
        lines.append("")

    text_body = "\n".join(lines)
    text_filename = f"{user_label}_{ts}.txt"
    text_path = _RESULTS_TEXT_DIR / text_filename
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text_body)

    if send_to_hr and HR_ACCOUNT and client:
        try:
            client.send_message(HR_ACCOUNT, text_body)
        except Exception as e:
            log.exception("Send to HR failed: %s", e)

    return str(text_path)


def finish_session(user_id: int) -> dict[str, Any] | None:
    """Взять результат и очистить сессию. Возвращает questionnaire_result или None."""
    state = _state.pop(user_id, None)
    if not state:
        return None
    return build_questionnaire_result_from_state(state)
