import logging
from typing import Any, Dict, List

from .utils import swap

_log = logging.getLogger("userbot")


TRANSLATE: Dict[str, str] = {
    "f_offering_name": "Наименование вакансии",
    "createdAt": "Дата создания",
    "updatedAt": "Дата обновления",
    "f_min_age": "Минимальный возраст",
    "f_offering_max_age": "Максимальный возраст",
    "current_age": "Возраст",
    "f_offering_gender": "Пол",
    "f_offering_min_price": "Минимальная оплата",
    "f_offering_max_price": "Максимальная оплата",
    "f_offering_men_needed": "Требуется мужчин",
    "f_offering_women_needed": "Требуется женщин",
    "f_offering_description": "Описание старое",
    "f_offering_new_description": "Описание новое",
    "f_778clr1gcvp": "Область",
    "f_offering_nationality": "Гражданство",
    "f_offering_offering": "Категория работы",
    "f_offering_rate": "Тип оплаты",
}


POSSIBLE_FILTERS: Dict[str, Any] = {
    "current_age": None,
    "f_offering_gender": None,
    "f_offering_offering": None,
    "f_778clr1gcvp": None,
    "f_offering_nationality": None,
    "f_offering_rate": None,
}


GENDERS: Dict[str, str] = {"08i2iwrzqi2": "женщина", "q3slmijbifh": "мужчина"}
GENDER_CHOICES: List[tuple[str, str]] = [
    ("q3slmijbifh", "мужчина"),
    ("08i2iwrzqi2", "женщина"),
]
CATEGORY: Dict[str, str] = {"m686ynzq3hk": "Склад", "egphzfob65p": "Производство"}
OFFERING_RATE: Dict[str, str] = {"0xzahoxb7p6": "Выработка", "yumhk3a93le": "Фикс"}
NATIONALITY: Dict[str, str] = {
    "gcqez27y5f4": "РФ",
    "34ttqq61lvg": "Узбекистан",
    "gk7e2465a07": "Белоруссия",
    "kl361vufv57": "Таджикистан",
    "sc291qbzdg3": "Молдова",
    "ntk2lrx6fex": "Армения",
    "111501hylor": "Азербайджан",
    "mng5b3rqyq0": (
        "Дагестан | Ингушетия | Кабардино-Балкария "
        "| Карачаево-Черкессия | Чечня | Адыгея | Алания "
        "| Кавказский федеральный округ | Абхазия | Осетия"
    ),
}


def generate_filter(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Построение фильтра в формате API.
    """
    main_conditions: List[Dict[str, Any]] = []

    for key, value in filters.items():
        if value is None:
            continue

        if key == "current_age" and isinstance(value, int):
            main_conditions.append({"f_min_age": {"$lte": value}})
            main_conditions.append({"f_offering_max_age": {"$gte": value}})
            continue

        if key == "f_778clr1gcvp" and isinstance(value, int):
            main_conditions.append(
                {
                    "f_offering_city": {
                        "id": {"$eq": value},
                    }
                }
            )
            continue

        if isinstance(value, int):
            main_conditions.append({key: {"$gte": value}})
        elif isinstance(value, str):
            main_conditions.append({key: {"$gte": value}})
        elif isinstance(value, list):
            if key == "f_offering_offering":
                main_conditions.append({key: {"$in": value}})
            elif key == "f_offering_rate" and len(value) == 1:
                main_conditions.append({key: {"$eq": value[0]}})
            elif key == "f_offering_gender":
                main_conditions.append({key: {"$anyOf": value}})
                if "q3slmijbifh" in value:
                    main_conditions.append({"f_offering_men_needed": {"$gte": 1}})
                if "08i2iwrzqi2" in value:
                    main_conditions.append({"f_offering_women_needed": {"$gte": 1}})
            else:
                main_conditions.append({key: {"$anyOf": value}})

    status_block = {
        "$and": [
            {"f_offering_status": {"$eq": "2vi89elxqk9"}}
        ]
    }

    return {
        "$and": [
            {"$and": main_conditions},
            status_block,
        ]
    }


def filter_from_short(short: Dict[str, Any], places: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """
    Построить плоский словарь условий для generate_filter из выжимки опроса (short).
    short: full_name, gender, birth_date, age, job_type, region (и др.).
    places: список из get_places()["data"].
    Возвращает None, если нет ни одного применимого условия (например, регион не найден и остальное пусто).
    """
    filters: Dict[str, Any] = {}

    # Регион: short["region"] — строка, ищем в places по f_places_name
    region_name = short.get("region") if isinstance(short.get("region"), str) else None
    if region_name and places:
        for p in places:
            if p.get("f_places_name") == region_name:
                place_id = p.get("id")
                if isinstance(place_id, int):
                    filters["f_778clr1gcvp"] = place_id
                break

    # Пол: short["gender"] — "мужчина" / "женщина"
    gender_label = short.get("gender") if isinstance(short.get("gender"), str) else None
    if gender_label:
        rev = swap(GENDERS)
        code = rev.get(gender_label.strip())
        if code:
            filters["f_offering_gender"] = [code]

    # Возраст
    age = short.get("age")
    if isinstance(age, int) and age > 0:
        filters["current_age"] = age

    # Категория (job_type): short["job_type"] — строка, маппим через CATEGORY
    job_type = short.get("job_type") if isinstance(short.get("job_type"), str) else None
    if job_type and job_type.strip():
        rev_cat = swap(CATEGORY)
        code = rev_cat.get(job_type.strip())
        if code:
            filters["f_offering_offering"] = [code]

    if not filters:
        return None
    return filters


def get_int() -> int:
    """Ввод целого числа с повтором при неверном вводе (без try/except)."""
    prompt = "Введите целое число:\n_> "
    while True:
        s = input(prompt).strip()
        if s.lstrip("-").isdigit() and s not in ("", "-"):
            return int(s)
        print("Введите, пожалуйста, число.")


def choose_places(places: list[dict[str, Any]]) -> int:
    print("Выберите область")
    for d in places:
        print(f'{d.get("id")}\t{d.get("f_places_name")}')
    print("Выбрать (0 -- завершить): ")
    place_id = get_int()
    return place_id


def choose_nationality() -> list[str]:
    nation_nums = list(NATIONALITY.values())
    chosen: list[str] = []
    print("Выберите гражданство:")
    for i, nation in enumerate(nation_nums, start=1):
        print(f"{i}.\t{nation}")
    while True:
        print("Добавить (0 -- завершить)")
        num = get_int()
        if num == 0:
            break
        if num < 0 or num > len(nation_nums):
            print("Неверный ввод.")
            continue
        chosen.append(swap(NATIONALITY)[nation_nums[num - 1]])
    return chosen


def choose_gender() -> list[str]:
    print("Выберите пол:")
    for i, (code, label) in enumerate(GENDER_CHOICES, start=1):
        print(f"{i}.\t{label}")
    num = get_int()
    if 1 <= num <= len(GENDER_CHOICES):
        return [GENDER_CHOICES[num - 1][0]]
    print("Неверный ввод. Будет использован любой пол.")
    return []


def choose_category() -> list[str]:
    category_nums = list(CATEGORY.values())
    print("Выберите категорию")
    for i, c in enumerate(category_nums, start=1):
        print(f"{i}.\t{c}")
    while True:
        num = get_int()
        if num < 1 or num > len(category_nums):
            print("Неверный ввод.")
        else:
            return [swap(CATEGORY)[category_nums[num - 1]]]


def choose_rate() -> list[str]:
    rate = input("Выберите тип оплаты:\n1. Выработка\n2. Фикс\n_>:")
    match rate:
        case "1":
            return [swap(OFFERING_RATE)["Выработка"]]
        case "2":
            return [swap(OFFERING_RATE)["Фикс"]]
        case _:
            print("Неверный ввод. Тип оплаты выбран не будет.")
            return []


def choose_filters(places: list[dict[str, Any]]) -> Dict[str, Any]:
    """
    Интерактивный выбор фильтров. Возвращает словарь полей и значений для generate_filter.
    """
    filters: Dict[str, Any] = {}
    filters_list: List[str] = list(POSSIBLE_FILTERS.keys())

    while True:
        print("Выберите фильтр:")
        for idx, key in enumerate(filters_list, start=1):
            print(f"{idx}.\t{TRANSLATE.get(key, key)}")
        print("0.\tЗавершить")

        filter_num = get_int()
        
        if filter_num == 0:
            return filters
        if filter_num < 0 or filter_num > len(filters_list):
            print("Неверный номер фильтра.")
            continue

        key = filters_list[filter_num - 1]

        match key:
            case "current_age":
                filters[key] = get_int()
            case "f_offering_gender":
                filters[key] = choose_gender()
            case "f_offering_offering":
                filters[key] = choose_category()
            case "f_778clr1gcvp":
                filters[key] = choose_places(places)
            case "f_offering_nationality":
                filters[key] = choose_nationality()
            case "f_offering_rate":
                filters[key] = choose_rate()
