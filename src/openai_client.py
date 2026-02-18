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
