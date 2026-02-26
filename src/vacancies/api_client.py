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
    params = {"pageSize": page_size}
    resp = requests.get(url, headers=_get_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_job_offerings(
    filter_dict: Optional[Dict[str, Any]] = None,
    page_size: int = 120,
) -> Dict[str, Any]:
    """
    Получить список вакансий t_job_offerings с опциональным фильтром.
    filter_dict должен соответствовать формату API, например:
    {"$and":[{...},{...}]}
    """
    url = f"{VACANCY_API_URL.rstrip('/')}/{JOBS_DATA}"

    params: Dict[str, Any] = {"pageSize": page_size}
    if filter_dict:
        params["filter"] = json.dumps(filter_dict, separators=(",", ":"))

    resp = requests.get(url, headers=_get_headers(), params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()
