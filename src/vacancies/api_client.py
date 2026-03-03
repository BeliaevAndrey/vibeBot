import json
import logging
from typing import Any, Dict, Optional

import requests

try:
    from config import VACANCY_API_KEY, VACANCY_API_URL
except ImportError:
    import os
    VACANCY_API_URL = os.environ.get("VACANCY_API_URL", "https://platform.vaxtarekrut.ru/api/")
    VACANCY_API_KEY = os.environ.get("VACANCY_API_KEY", "")

_log = logging.getLogger("userbot")

JOBS_DATA = "t_job_offerings"
JOBS_PLACES = "t_places"


def _get_headers() -> Dict[str, str]:
    if not VACANCY_API_KEY:
        msg = "VACANCY_API_KEY не установлен. Загрузите переменные окружения из .env."
        _log.error(msg)
        raise RuntimeError(msg)
    return {
        "Authorization": f"Bearer {VACANCY_API_KEY}",
        "Accept": "application/json",
    }


def get_places(page_size: int = 120) -> Dict[str, Any]:
    """
    Получить список регионов (t_places) для выбора области.
    """
    url = f"{VACANCY_API_URL.rstrip('/')}/{JOBS_PLACES}"
    params: Dict[str, Any] = {"pageSize": page_size}
    resp = requests.get(url, headers=_get_headers(), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    meta = data.get("meta") or {}
    _log.info("Places API meta (page 1): %s", meta)

    total_pages = meta.get("totalPages") or meta.get("totalPage") or 1
    try:
        total_pages_int = int(total_pages)
    except (TypeError, ValueError):
        total_pages_int = 1

    if total_pages_int > 1:
        all_items = list(data.get("data") or [])
        for page in range(2, total_pages_int + 1):
            page_params = dict(params)
            page_params["page"] = page
            page_resp = requests.get(
                url, headers=_get_headers(), params=page_params, timeout=30
            )
            page_resp.raise_for_status()
            page_json = page_resp.json()
            page_meta = page_json.get("meta") or {}
            _log.info("Places API meta (page %s): %s", page, page_meta)
            page_items = page_json.get("data") or []
            all_items.extend(page_items)

        data["data"] = all_items

    return data


def get_job_offerings(
    filter_dict: Optional[Dict[str, Any]] = None,
    page_size: int = 12,
) -> Dict[str, Any]:
    """
    Получить список вакансий t_job_offerings с опциональным фильтром.

    - filter_dict должен соответствовать формату API, например: {"$and":[{...},{...}]}
    - page_size — количество вакансий на страницу (для тестирования по умолчанию 12).
    - Если в ответе meta.totalPages (или meta.totalPage) > 1, автоматически
      догружаем остальные страницы и объединяем их в одном словаре.
    """
    url = f"{VACANCY_API_URL.rstrip('/')}/{JOBS_DATA}"

    params: Dict[str, Any] = {"pageSize": page_size}
    if filter_dict:
        params["filter"] = json.dumps(filter_dict, separators=(",", ":"))

    resp = requests.get(url, headers=_get_headers(), params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    meta = data.get("meta") or {}
    _log.info("Vacancy API meta (page 1): %s", meta)
    # В разных версиях API ключ может называться totalPages или totalPage
    total_pages = meta.get("totalPages") or meta.get("totalPage") or 1
    try:
        total_pages_int = int(total_pages)
    except (TypeError, ValueError):
        total_pages_int = 1

    # Если страниц больше одной — догружаем остальные и объединяем "data"
    if total_pages_int > 1:
        all_items = list(data.get("data") or [])
        for page in range(2, total_pages_int + 1):
            page_params = dict(params)
            page_params["page"] = page
            page_resp = requests.get(
                url, headers=_get_headers(), params=page_params, timeout=60
            )
            page_resp.raise_for_status()
            page_json = page_resp.json()
            page_meta = page_json.get("meta") or {}
            _log.info("Vacancy API meta (page %s): %s", page, page_meta)
            page_items = page_json.get("data") or []
            all_items.extend(page_items)

        data["data"] = all_items

    return data
