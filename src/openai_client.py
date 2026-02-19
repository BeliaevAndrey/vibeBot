"""
Интеграция с OpenAI для получения ответов в диалоге.
"""

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
