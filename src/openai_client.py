"""
Интеграция с OpenAI для получения ответов в диалоге.
"""

import json
from openai import OpenAI


def get_reply(messages: list[dict], system_prompt: str = "") -> str:
    """
    Получить ответ от OpenAI на основе истории сообщений.
    messages: [{"role": "user"|"assistant", "content": "..."}, ...]
    system_prompt: опциональное системное сообщение.
    """
    from config import OPENAI_API_KEY, OPENAI_MODEL

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


def get_completion(prompt: str) -> str:
    """
    Один запрос к модели (без истории).
    Используется для оценки ответа по промпту из question_prompt.txt.
    """
    from config import OPENAI_API_KEY, OPENAI_MODEL

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def evaluate_agreement(user_message: str) -> bool:
    """
    Определить, согласен ли пользователь отвечать на вопросы (утвердительно/положительно).
    Возвращает True при согласии, False при отказе.
    """
    system = (
        "Ты ассистент. Пользователь ответил на приглашение пройти опрос. "
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
    from config import OPENAI_API_KEY, OPENAI_MODEL

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
        import logging
        logging.getLogger("userbot").exception("Ошибка валидации: %s", e)
        return (True, "")
