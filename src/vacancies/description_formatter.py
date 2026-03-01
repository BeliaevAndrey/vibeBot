"""
Форматирование description_text вакансии: разбор по секциям, порядок вывода, футер.
Используется в enrich_offerings — итог сохраняется в description_text и уходит кандидату.
"""

import re
from typing import Any

# Порядок вывода секций (сначала эти ключи, остальные — в конце)
ORDERED_SECTION_KEYS = [
    "ВАКАНСИЯ",
    "МЕСТНЫЙ ПЕРСОНАЛ",
    "СБ",
    "ОФОРМЛЕНИЕ",
    "ДОКУМЕНТЫ",
    "ОБЯЗАННОСТИ",
    "СТАВКА",
    "РАСЧЕТ",
    "АВАНС",
    "ПИТАНИЕ",
    "ГРАФИК",
    "УДЕРЖАНИЕ",
    "РЕГИСТРАЦИЯ",
    "ЗАСЕЛЕНИЕ",
    "АДРЕС РАБОТЫ",
    "ТРАНСПОРТ",
    "ФОТО ПРОЖИВАНИЯ",
]


def parse_description(text: str, section_keys: list[str]) -> dict[str, str]:
    """
    Разбить text на секции по ключам из section_keys.
    Ищет строки вида "KEY:" или "KEY" (в начале строки). Содержимое — до следующего заголовка.
    Возвращает словарь key -> content (content без ведущих/концевых пробелов по краям).
    """
    if not (text or "").strip():
        return {}
    lines = text.split("\n")
    key_patterns = [
        (k, re.compile(r"^\s*" + re.escape(k) + r"\s*:?\s*$", re.IGNORECASE))
        for k in section_keys
    ]
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is not None and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections[current_key] = content
        current_key = None
        current_lines = []

    for line in lines:
        stripped = line.strip()
        matched_key = None
        for key, pat in key_patterns:
            if pat.match(stripped):
                matched_key = key
                break
        if matched_key is not None:
            flush()
            current_key = matched_key
            after_colon = line.strip()
            if ":" in after_colon:
                idx = after_colon.index(":")
                tail = after_colon[idx + 1 :].strip()
                if tail:
                    current_lines.append(tail)
            continue
        if current_key is not None:
            if not current_lines and stripped.startswith(":"):
                current_lines.append(stripped.lstrip(":").strip())
            else:
                current_lines.append(line)
    flush()
    return sections


def _value_starts_with_number(value: str) -> bool:
    s = (value or "").strip()
    return bool(re.match(r"^\d", s))


def format_sections(
    sections: dict[str, str],
    section_keys: list[str] | None = None,
    order_override: list[str] | None = None,
) -> str:
    """
    Форматировать словарь секций в строку:
    - если значение начинается с числа — "Ключ: значение" в одну строку;
    - иначе "Ключ:\n\tтекст" (каждая строка текста с табуляцией).
    Порядок: order_override если задан, иначе section_keys, затем остальные ключи.
    """
    order = list(order_override) if order_override else (list(section_keys) if section_keys else [])
    for k in sections:
        if k not in order:
            order.append(k)
    out = []
    for key in order:
        value = sections.get(key)
        if value is None or value == "":
            continue
        if _value_starts_with_number(value):
            one_line = " ".join(value.split())
            out.append(f"{key}: {one_line}")
        else:
            prefixed = "\n".join("\t" + ln for ln in value.split("\n"))
            out.append(f"{key}:\n{prefixed}")
    return "\n".join(out)


def format_footer(item: dict[str, Any]) -> str:
    """
    В конце отчёта: только человеко-читаемые поля.
    При отсутствии — "неуказано" (Компания — "—"). Без кавычек.
    """
    gender = item.get("gender_human")
    if isinstance(gender, list):
        gender = ", ".join(str(x) for x in gender) if gender else None
    gender = (gender or "").strip() or "неуказано"

    nat = item.get("nationality_human")
    if isinstance(nat, list):
        nat = ", ".join(str(x) for x in nat) if nat else None
    nat = (nat or "").strip() or "неуказано"

    rate = (item.get("rate_human") or "").strip() or "неуказано"
    category = (item.get("category_human") or "").strip() or "неуказано"
    company = (item.get("f_offering_name") or "").strip() or "—"

    return (
        f"Пол: {gender}\n"
        f"Гражданство: {nat}\n"
        f"Компания: {company}\n"
        f"Фикс/Выработка: {rate}\n"
        f"Вакансия: {category}"
    )


def format_vacancy_description(
    raw_description_text: str,
    item: dict[str, Any],
    section_keys: list[str] | None = None,
) -> str:
    """
    Собрать итоговое описание вакансии для кандидата и для сохранения в description_text:
    заголовок (название + id) + секции по порядку + футер.
    """
    keys = section_keys or ORDERED_SECTION_KEYS
    name = (item.get("f_offering_name") or "").strip()
    vid = item.get("id")
    header = f"**{name}**\n(идентификатор {vid})\n\n"

    sections = parse_description(raw_description_text or "", keys)
    body = format_sections(sections, section_keys=keys, order_override=ORDERED_SECTION_KEYS)
    footer = format_footer(item)

    if body:
        return header + body + "\n\n" + footer
    return header.rstrip() + "\n\n" + footer
