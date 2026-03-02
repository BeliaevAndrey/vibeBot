"""
Разбиение текста описания вакансии на части, чтобы укладываться в лимит Telegram.
"""

from __future__ import annotations

from typing import List, Tuple

_MAX_VACANCY_MSG_LEN = 4000


def split_vacancy_and_footer(text: str) -> Tuple[str, str]:
    """
    Разделить текст отчёта по вакансии на «вакансию» и футер.
    Футер начинается с последней строки «Пол: ...» (footer из description_formatter).
    """
    marker = "\nПол:"
    idx = text.rfind(marker)
    if idx == -1:
        return text, ""
    vacancy = text[: idx + 1].rstrip()
    footer = text[idx + 1 :].lstrip()
    return vacancy, footer


def split_vacancy_messages(body: str) -> List[str]:
    """
    Разбить тело вакансии (report_text) на 1–несколько сообщений с учётом лимита.

    Правила:
    - если длина <= 4000 — одно сообщение;
    - если длина (вакансия+футер) > 4000 и сама вакансия <= 4000 — два сообщения (вакансия, футер);
    - если длина «чистой вакансии» > 4000 — разбить по ключам (заголовкам), стараясь не превышать лимит.
    """
    text = body or ""
    if len(text) <= _MAX_VACANCY_MSG_LEN:
        return [text]

    vacancy, footer = split_vacancy_and_footer(text)
    vacancy = vacancy.rstrip()
    footer = footer.rstrip()

    if footer:
        combined = f"{vacancy}\n\n{footer}"
    else:
        combined = vacancy

    if len(combined) <= _MAX_VACANCY_MSG_LEN:
        return [combined]

    # Вариант 1: вакансия влезает, footer отдельно
    if len(vacancy) <= _MAX_VACANCY_MSG_LEN and footer:
        if len(footer) <= _MAX_VACANCY_MSG_LEN:
            return [vacancy, footer]

    # Вариант 2: вакансия > лимита — разбиваем по ключам (заголовкам секций)
    lines = combined.splitlines(keepends=True)
    cum_len = 0
    split_idx = None
    for i, ln in enumerate(lines):
        cum_len += len(ln)
        if cum_len > _MAX_VACANCY_MSG_LEN:
            # Ищем вверх заголовок вида "KEY:" (верхний регистр, заканчивается на ':')
            for j in range(i, -1, -1):
                candidate = lines[j].lstrip()
                stripped = candidate.strip()
                if stripped.isupper() and stripped.endswith(":"):
                    split_idx = j
                    break
            if split_idx is None:
                split_idx = i
            break

    if split_idx is None:
        # fallback: делим примерно пополам
        split_idx = len(lines) // 2

    first = "".join(lines[:split_idx]).rstrip()
    second = "".join(lines[split_idx:]).lstrip()

    parts: List[str] = []
    if first:
        if len(first) <= _MAX_VACANCY_MSG_LEN:
            parts.append(first)
        else:
            for start in range(0, len(first), _MAX_VACANCY_MSG_LEN):
                parts.append(first[start : start + _MAX_VACANCY_MSG_LEN])

    if second:
        if len(second) <= _MAX_VACANCY_MSG_LEN:
            parts.append(second)
        else:
            for start in range(0, len(second), _MAX_VACANCY_MSG_LEN):
                parts.append(second[start : start + _MAX_VACANCY_MSG_LEN])

    return parts

