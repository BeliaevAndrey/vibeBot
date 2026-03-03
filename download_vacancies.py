#!/usr/bin/env python3
"""
CLI: загрузка вакансий с платформы VaxtaRekrut с применением фильтров.
Запуск из корня проекта: python download_vacancies.py
"""
import argparse
import json
import os
import logging
from typing import Any, Dict

from config import VACANCY_RESULTS_DIR, setup_logging
from src.vacancies import (
    choose_filters,
    enrich_offerings,
    generate_filter,
    get_job_offerings,
    get_places,
    print_offerings,
)

setup_logging()
log = logging.getLogger("userbot")
RESULTS_DIR = VACANCY_RESULTS_DIR
RESULTS_FILE = "results.json"


def ensure_results_dir() -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    return os.path.join(RESULTS_DIR, RESULTS_FILE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Загрузка вакансий с платформы VaxtaRekrut с применением фильтров."
    )
    parser.add_argument(
        "--filter-json",
        type=str,
        help="JSON-строка с фильтром в формате API (как в параметре filter).",
    )
    parser.add_argument(
        "--no-print",
        action="store_true",
        help="Не выводить вакансии в консоль, только сохранить в файл.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Сколько вакансий выводить в консоль (по умолчанию 10).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        places_response = get_places()
        places = places_response.get("data", [])

        filter_dict: Dict[str, Any] | None = None

        if args.filter_json:
            try:
                filter_dict = json.loads(args.filter_json)
            except json.JSONDecodeError as exc:
                log.exception("Некорректный JSON в --filter-json: %s", exc)
                raise SystemExit(f"Некорректный JSON в --filter-json: {exc}") from exc
        else:
            chosen_filters = choose_filters(places)
            if chosen_filters:
                filter_dict = generate_filter(chosen_filters)

        raw_data = get_job_offerings(filter_dict=filter_dict)
        offerings = enrich_offerings(raw_data, places)

        if not args.no_print:
            print_offerings(offerings, limit=args.limit)

        out_path = ensure_results_dir()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(offerings, f, ensure_ascii=False, indent=4)

        total = len(offerings)
        print(f"\nВсего найдено: {total} вакансий. Сохранено в файл: {out_path}")
    except Exception as e:
        log.exception("Ошибка загрузки вакансий: %s", e)
        raise


if __name__ == "__main__":
    main()
