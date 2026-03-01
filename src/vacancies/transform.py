from typing import Any, Dict, List

from bs4 import BeautifulSoup
import logging

from config import VACANCY_TOP_N    # top N vacancies to send to HR
from .description_formatter import format_vacancy_description
from .filter_builder import (
    CATEGORY,
    GENDERS,
    NATIONALITY,
    OFFERING_RATE,
    TRANSLATE,
)


def _build_places_index(places: List[Dict[str, Any]] | None) -> Dict[int, str]:
    index: Dict[int, str] = {}
    if not places:
        return index
    for p in places:
        pid = p.get("id")
        name = p.get("f_places_name")
        if isinstance(pid, int) and isinstance(name, str):
            index[pid] = name
    return index


def enrich_offerings(
    raw_data: Dict[str, Any],
    places: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """
    Обогащает вакансии дополнительной человеко-читаемой информацией.
    """
    offerings: List[Dict[str, Any]] = []
    places_index = _build_places_index(places or [])

    for vacancy in raw_data.get("data", []):
        item: Dict[str, Any] = dict(vacancy)

        genders_needed = vacancy.get("f_offering_gender") or []
        if genders_needed:
            item["gender_human"] = ", ".join(
                [GENDERS.get(code, code) for code in genders_needed]
            )

        nationals = vacancy.get("f_offering_nationality") or []
        if nationals:
            item["nationality_human"] = [
                NATIONALITY.get(code, code) for code in nationals
            ]

        category_code = vacancy.get("f_offering_offering")
        if category_code:
            item["category_human"] = CATEGORY.get(category_code, category_code)

        rate_code = vacancy.get("f_offering_rate")
        if rate_code:
            item["rate_human"] = OFFERING_RATE.get(rate_code, rate_code)

        region_id = vacancy.get("f_778clr1gcvp")
        if isinstance(region_id, int):
            item["region_name"] = places_index.get(region_id, f"Область {region_id}")

        desc_html = vacancy.get("f_offering_new_description")
        if desc_html is None or not isinstance(desc_html, str):
            item["description_text"] = ""
        else:
            try:
                soup = BeautifulSoup(desc_html, "lxml")
                # Подставляем полный URL из href в текст, чтобы в выводе была ссылка (не только «Google диск» и т.п.)
                for a in soup.find_all("a", href=True):
                    a.replace_with(a.get("href", ""))
                item["description_text"] = soup.get_text(separator="\n", strip=True)
            except Exception as e:
                logging.getLogger("userbot").exception(
                    "Ошибка парсинга описания вакансии (HTML): %s", e
                )
                item["description_text"] = desc_html

        # Форматированное описание (секции + футер) — для кандидата и для сохранения в description_text
        raw_desc = item.get("description_text") or ""
        item["description_text"] = format_vacancy_description(raw_desc, item)

        offerings.append(item)

    return offerings


def format_top_vacancies_report(
    offerings: List[Dict[str, Any]],
    top_n: int = VACANCY_TOP_N,
) -> str:
    """
    Формирует человеко-читаемый отчёт по топ-N вакансиям для отправки HR и кандидату.
    description_text уже содержит форматированное описание (заголовок, секции, футер).
    """
    lines = ["Вакансия:", ""]
    for idx, item in enumerate(offerings[:top_n], start=1):
        name = item.get("f_offering_name") or "—"
        lines.append(f"{idx}. {name}")

        vid = item.get("id")
        lines.append(f"ID вакансии: {vid if vid is not None else '—'}")

        date_val = item.get("updatedAt") if item.get("updatedAt") is not None else item.get("createdAt")
        lines.append(f"Вакансия от: {date_val if date_val is not None else '—'}")

        region = item.get("region_name") or "—"
        lines.append(f"Регион: {region}")

        gender = item.get("gender_human") or "—"
        nat = item.get("nationality_human")
        if isinstance(nat, list):
            nat_str = ", ".join(str(x) for x in nat) if nat else "—"
        else:
            nat_str = nat if nat else "—"
        lines.append(f"Пол: {gender}. Гражданство: {nat_str}")

        cat = item.get("category_human") or "—"
        rate = item.get("rate_human") or "—"
        lines.append(f"Категория: {cat}. Оплата: {rate}")

        desc = item.get("description_text") or ""
        lines.append("Описание:")
        if desc:
            lines.append(desc)
        else:
            lines.append("—")

        lines.append("")
        if idx < min(len(offerings), top_n):
            lines.append("---")
            lines.append("")

    return "\n".join(lines).rstrip()


def print_offerings(offerings: List[Dict[str, Any]], limit: int = 10) -> None:
    """Печатает в консоль человеко-читаемый текст по вакансиям."""
    for idx, item in enumerate(offerings[:limit], start=1):
        print(f"=== Вакансия #{idx} (ID={item.get('id')}) ===")
        print(f"{TRANSLATE['f_offering_name']}: {item.get('f_offering_name')}")
        print(f"{TRANSLATE['createdAt']}: {item.get('createdAt')}")
        print(f"{TRANSLATE['updatedAt']}: {item.get('updatedAt')}")
        print(f"{TRANSLATE['f_min_age']}: {item.get('f_min_age')}")
        print(f"{TRANSLATE['f_offering_max_age']}: {item.get('f_offering_max_age')}")
        print(f"{TRANSLATE['f_offering_gender']}: {item.get('gender_human', '—')}")
        print(f"{TRANSLATE['f_offering_min_price']}: {item.get('f_offering_min_price')}")
        print(f"{TRANSLATE['f_offering_max_price']}: {item.get('f_offering_max_price')}")
        print(f"{TRANSLATE['f_offering_men_needed']}: {item.get('f_offering_men_needed')}")
        print(f"{TRANSLATE['f_offering_women_needed']}: {item.get('f_offering_women_needed')}")
        print(f"{TRANSLATE['f_778clr1gcvp']}: {item.get('region_name', '—')}")
        print(f"{TRANSLATE['f_offering_nationality']}: {item.get('nationality_human', '—')}")
        print(f"{TRANSLATE['f_offering_offering']}: {item.get('category_human', '—')}")
        print(f"{TRANSLATE['f_offering_rate']}: {item.get('rate_human', '—')}")
        desc = item.get("description_text") or ""
        print(f"{TRANSLATE['f_offering_new_description']}: {desc or ''}")
        print("\n" + "=" * 40 + "\n")
