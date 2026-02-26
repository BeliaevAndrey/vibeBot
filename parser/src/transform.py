from typing import Any, Dict, List

from bs4 import BeautifulSoup

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

    - Сохраняет нативные ключи API без переименования.
    - Добавляет *_human поля (gender_human, category_human, rate_human, nationality_human, region_name, description_text).
    """
    offerings: List[Dict[str, Any]] = []
    places_index = _build_places_index(places or [])

    for vacancy in raw_data.get("data", []):
        # Копируем все нативные поля как есть
        item: Dict[str, Any] = dict(vacancy)

        # Пол
        genders_needed = vacancy.get("f_offering_gender") or []
        if genders_needed:
            item["gender_human"] = ", ".join(
                [GENDERS.get(code, code) for code in genders_needed]
            )

        # Национальность
        nationals = vacancy.get("f_offering_nationality") or []
        if nationals:
            item["nationality_human"] = [
                NATIONALITY.get(code, code) for code in nationals
            ]

        # Категория
        category_code = vacancy.get("f_offering_offering")
        if category_code:
            item["category_human"] = CATEGORY.get(category_code, category_code)

        # Тип оплаты
        rate_code = vacancy.get("f_offering_rate")
        if rate_code:
            item["rate_human"] = OFFERING_RATE.get(rate_code, rate_code)

        # Регион (название)
        region_id = vacancy.get("f_778clr1gcvp")
        if isinstance(region_id, int):
            item["region_name"] = places_index.get(region_id, f"Область {region_id}")

        # Описание из HTML (поле может быть None, не строка или битый HTML)
        desc_html = vacancy.get("f_offering_new_description")
        if desc_html is None or not isinstance(desc_html, str):
            item["description_text"] = ""
        else:
            try:
                soup = BeautifulSoup(desc_html, "html5lib")
                item["description_text"] = soup.get_text(separator="\n", strip=True)
            except Exception:
                item["description_text"] = desc_html

        offerings.append(item)

    return offerings


def _shorten_description(text: str, max_len: int = 100) -> str:
    """Заменяет переносы на пробел, обрезает до max_len и добавляет '...' при обрезке."""
    if not text:
        return ""
    one_line = text.replace("\n", " ").strip()
    if len(one_line) <= max_len:
        return one_line
    return one_line[:max_len].rstrip() + "..."


def print_offerings(offerings: List[Dict[str, Any]], limit: int = 10) -> None:
    """
    Печатает в консоль только человеко-читаемый текст по вакансиям.
    Описание в консоли сокращается до 100 символов с многоточием.
    """
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
        print(f"{TRANSLATE['f_offering_new_description']}: {_shorten_description(desc)}")
        print("\n" + "=" * 40 + "\n")

