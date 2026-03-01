"""
Интеграция с OpenAI для получения ответов в диалоге и вспомогательные вызовы LLM.
"""

import json
import logging
from datetime import date, datetime
from typing import Any, Dict

from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL


def get_reply(messages: list[dict], system_prompt: str = "") -> str:
    """
    Получить ответ от OpenAI на основе истории сообщений.
    messages: [{"role": "user"|"assistant", "content": "..."}, ...]
    system_prompt: опциональное системное сообщение.
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    api_messages: list[dict] = []
    if system_prompt:
        api_messages.append({"role": "system", "content": system_prompt})
    api_messages.extend(messages)

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=api_messages,
    )
    return response.choices[0].message.content or ""


def evaluate_agreement(user_message: str) -> bool:
    """
    Определить, согласен ли пользователь отвечать на вопросы (утвердительно/положительно).
    Возвращает True при согласии, False при отказе.
    """
    system = (
        "Ты рекрутер/менеджер по найму (живой человек) для массового найма вахтовиков/сменщиков." 
        "Ты ведешь диалог с кандидатом в WhatsApp, собираешь информацию для подбора вакансии."
        "Краткие ответы ok, ок, yes, да, нет, no - это ВАЛИДНЫЕ ответы!"
        "Брань - невалидный ответ!"
        "Ответь строго одним словом: YES — если согласен/готов отвечать (утвердительно, положительно); "
        "NO — если отказывается или отвечает отрицательно. Без пояснений."
    )
    reply = get_reply([{"role": "user", "content": user_message}], system_prompt=system)
    return reply.strip().upper().startswith("YES")


def validate_answer(
    question: str, answer: str, acceptance_criteria: str = ""
) -> tuple[bool, str]:
    """
    Валидирует ответ кандидата и генерирует человеческий ответ рекрутера.
    Возвращает (valid: bool, human_response: str).
    """
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        acceptance_text = (
            f"\n\nКритерии приемлемости ответа: {acceptance_criteria}"
            if acceptance_criteria
            else ""
        )
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Ты рекрутер/менеджер по найму (живой человек) для массового найма вахтовиков/сменщиков. Ты ведешь диалог с кандидатом в WhatsApp, собираешь информацию для подбора вакансии. КРИТИЧЕСКИ ВАЖНО: Веди диалог как живой человек-рекрутер. Никогда не говори и не намекай, что ты ИИ/бот/автоматизация. Язык: русский. Тон: вежливо-деловой, коротко, без воды. КРИТИЧЕСКИ ВАЖНО: Если вопрос спрашивает 'был ли опыт' или 'есть ли что-то', то ответы 'нет', 'не было', 'не было опыта' - это ВАЛИДНЫЕ ответы! Не требуй деталей, если человек говорит что опыта нет. БУДЬ ЩЕДРЫМ - если ответ содержит хоть какую-то информацию по теме или отрицательный ответ на вопрос 'был ли' - считай валидным. НЕВАЛИДЕН только полный отказ, полная ерунда не по теме или пустой ответ. Если ответ невалиден (ерунда/отказ) - сгенерируй человеческий ответ рекрутера, который объяснит проблему и склонит кандидата ответить нормально. КРИТИЧЕСКИ ВАЖНО: НЕ здоровайся, НЕ начинай с приветствий - мы УЖЕ в диалоге! Общайся естественно, как живой человек-рекрутер, не формально. Не повторяй одни и те же фразы - будь разнообразным. Если человек задал уточняющий вопрос, зачем эта информация или на что она влияет - придумай что-нибудь релевантное и убедительное, чтобы УБЕДИТЬ человека ответить. НЕ используй фразы типа 'Ваш ответ не содержит', 'Пожалуйста уточните' - это палит бота! Говори как живой рекрутер.",
                },
                {
                    "role": "user",
                    "content": f"Вопрос: {question}\nОтвет кандидата: {answer}{acceptance_text}",
                },
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "validate_answer",
                        "description": "Валидирует ответ кандидата и генерирует человеческий ответ для отправки",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "valid": {
                                    "type": "boolean",
                                    "description": "True если: ответ содержит информацию по теме ИЛИ отрицательный ответ на вопрос 'был ли' ('нет', 'не было', 'не было опыта' - ВСЕГДА валидны). False только если полный отказ, полная ерунда не по теме или пустой ответ. КРИТИЧЕСКИ ВАЖНО: если вопрос спрашивает 'был ли опыт', то 'нет' = валидно!",
                                },
                                "human_response": {
                                    "type": "string",
                                    "description": "Если valid=false - естественный ответ рекрутера, который объяснит проблему и склонит ответить. Будь разнообразным, неформальным, как живой человек-рекрутер. НЕ используй фразы типа 'Ваш ответ не содержит', 'Пожалуйста уточните' - это палит бота! Говори естественно, как рекрутер, например: 'Понял, но мне нужно уточнение...', 'Не совсем понял, можете пояснить...', 'Хм, не совсем ясно...', 'Чтобы подобрать вам подходящий вариант, мне нужно знать...'. НЕ повторяй вопрос дословно - переформулируй своими словами. Если valid=true - пустая строка.",
                                },
                            },
                            "required": ["valid", "human_response"],
                        },
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "validate_answer"}},
            temperature=0.7,
        )
        if response.choices[0].message.tool_calls:
            result = json.loads(
                response.choices[0].message.tool_calls[0].function.arguments
            )
            valid = result.get("valid", False)
            human_response = (
                result.get("human_response", "") if not valid else ""
            )
            return (valid, human_response)
        return (True, "")
    except Exception as e:
        logging.getLogger("userbot").exception("Ошибка валидации: %s", e)
        return (True, "")


def summarize_questionnaire(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Сформировать короткую выжимку из результата опроса для дальнейшей передачи в parser.
    Возвращает словарь вида:
    {
      "full_name": str | None,
      "last_name": str | None,   # фамилия (из разбора ФИО)
      "first_name": str | None,  # имя
      "patronymic": str | None,  # отчество (может отсутствовать)
      "gender": str | None,      # "мужчина"/"женщина" или None
      "birth_date": str | None,  # ISO YYYY-MM-DD или None
      "age": int | None,         # возраст в годах, вычисляется в скрипте
      "job_type": str | None,    # "склад"/"производство" или None
      "region": str | None
    }
    """
    client = OpenAI(api_key=OPENAI_API_KEY)

    user_content = (
        "Вот полный JSON результата опроса кандидата.\n"
        "Сформируй выжимку по правилам из системного сообщения.\n\n"
        f"{json.dumps(result, ensure_ascii=False)}"
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты HR-специалист по анализу анкет.\n"
                        "На вход ты получаешь JSON с результатами опроса кандидата "
                        "(пары question-answer).\n\n"

                        "Твоя задача — извлечь ТОЛЬКО явно присутствующую информацию "
                        "и вернуть структурированные данные.\n\n"

                        "КРИТИЧЕСКИЕ ПРАВИЛА:\n"
                        "- Ничего не додумывай.\n"
                        "- Не делай предположений.\n"
                        "- Не интерпретируй косвенные намёки.\n"
                        "- Если нет прямого указания — возвращай null.\n"
                        "- Если есть малейшая неопределённость — возвращай null.\n\n"

                        "Правила извлечения:\n"
                        "1. full_name — ФИО целиком, если явно указано.\n"
                        "   Дополнительно разбери ФИО на компоненты (порядок в русском: Фамилия Имя Отчество, или Имя Отчество Фамилия):\n"
                        "   - last_name — фамилия;\n"
                        "   - first_name — имя;\n"
                        "   - patronymic — отчество (если есть, иначе null).\n"
                        "   Если ФИО неполное (например, только имя) — заполни только известные поля, остальные null.\n"
                        "2. gender — только если:\n"
                        "   - явно указан пол\n"
                        "   - или однозначно определяется по ФИО.\n"
                        "   Иначе null.\n"
                        "3. birth_date — дата рождения строго в формате YYYY-MM-DD.\n"
                        "   - если указан только год → YYYY-01-01\n"
                        "   - если формат невозможно определить точно → null\n"
                        "4. age — только если возраст явно указан числом.\n"
                        "   Не вычислять возраст из даты рождения.\n"
                        "5. job_type — только 'склад' или 'производство', "
                        "если это прямо указано.\n"
                        "   Иначе null.\n"
                        "6. region — город или регион проживания, если явно указан.\n\n"

                        "Ответ должен быть строго через вызов функции."
                    )
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "generate_brief",
                        "description": "Извлекает структурированные данные кандидата",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "full_name": {
                                    "type": ["string", "null"],
                                    "description": "ФИО целиком"
                                },
                                "last_name": {
                                    "type": ["string", "null"],
                                    "description": "Фамилия"
                                },
                                "first_name": {
                                    "type": ["string", "null"],
                                    "description": "Имя"
                                },
                                "patronymic": {
                                    "type": ["string", "null"],
                                    "description": "Отчество (если нет — null)"
                                },
                                "gender": {
                                    "type": ["string", "null"],
                                    "enum": ["мужчина", "женщина"]
                                },
                                "birth_date": {
                                    "type": ["string", "null"],
                                    "description": "YYYY-MM-DD"
                                },
                                "age": {
                                    "type": ["number", "null"]
                                },
                                "job_type": {
                                    "type": ["string", "null"],
                                    "enum": ["склад", "производство"]
                                },
                                "region": {
                                    "type": ["string", "null"]
                                }
                            },
                            "required": [
                                "full_name",
                                "last_name",
                                "first_name",
                                "patronymic",
                                "gender",
                                "birth_date",
                                "age",
                                "job_type",
                                "region"
                            ],
                            "additionalProperties": False
                        }
                    }
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "generate_brief"}
            }
        )
        tool_calls = resp.choices[0].message.tool_calls
        if not tool_calls:
            logging.getLogger("userbot").error(
                "summarize_questionnaire: no tool_calls in response"
            )
            raise ValueError("summarize_questionnaire: no tool_calls in response")
        args_json = tool_calls[0].function.arguments
        data = json.loads(args_json)
    except Exception as e:
        logging.getLogger("userbot").exception("Ошибка выжимки опроса: %s", e)
        return {
            "full_name": None,
            "last_name": None,
            "first_name": None,
            "patronymic": None,
            "gender": None,
            "birth_date": None,
            "age": None,
            "job_type": None,
            "region": None,
        }

    birth_date_str = data.get("birth_date")
    birth_date_iso: str | None = None
    age: int | None = None
    if isinstance(birth_date_str, str) and birth_date_str:
        try:
            dt = datetime.fromisoformat(birth_date_str).date()
            birth_date_iso = dt.isoformat()
            today = date.today()
            age = today.year - dt.year - (
                (today.month, today.day) < (dt.month, dt.day)
            )
        except ValueError as e:
            logging.getLogger("userbot").exception(
                "summarize_questionnaire: неверный birth_date: %s", e
            )
            birth_date_iso = None
            age = None

    return {
        "full_name": data.get("full_name"),
        "last_name": data.get("last_name"),
        "first_name": data.get("first_name"),
        "patronymic": data.get("patronymic"),
        "gender": data.get("gender"),
        "birth_date": birth_date_iso,
        "age": age,
        "job_type": data.get("job_type"),
        "region": data.get("region"),
    }
