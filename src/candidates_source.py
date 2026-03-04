"""
Источник списка кандидатов для опроса.

Пока заглушка: возвращает хардкоженный список пар (username, phone).
В дальнейшем реализацию можно заменить на чтение из файла/БД без
изменений основного кода.
"""

from typing import List, Optional, Tuple

import json


def get_candidates() -> List[Tuple[Optional[str], Optional[str]]]:
    """
    Вернуть список кандидатов для опроса.

    Каждый элемент — кортеж (username, phone):
    - username: строка с @ или без, либо None;
    - phone: строка с телефоном в произвольном формате, либо None.
    В позиции не должны одновременно отсутствовать и username, и phone.
    """
    # TODO: заменить на чтение из внешнего источника (CSV/JSON/БД).
    # Формат возвращаемого списка: [("@username", "+7 123 456 78 90"), ]
    try:
        with open("resource/json/contacts.json", "r", encoding="utf-8") as fi:
                contacts = json.load(fi)
            return contacts
    except FileNotFoundError:
        print("File not found")
        return [(None, None)]
    except json.JSONDecodeError as err:
        print(f"JSON decode error: {err}")
        return [(None, None)]
