"""
Конфигурация из переменных окружения и базовые пути/логирование.
"""

import os
import logging
from pathlib import Path


def _truthy(val: str) -> bool:
    if val is None or val == "":
        return False
    return str(val).strip().lower() in ("1", "true", "yes", "on")


# Telegram API
TG_API_ID = int(os.environ.get("TG_API_ID", "0"))
TG_API_HASH = os.environ.get("TG_API_HASH", "")
TG_PHONE = os.environ.get("TG_PHONE", "")

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Telegram аккаунты
HR_ACCOUNT = os.environ.get("HR_ACCOUNT", "")
CANDIDATE_USERNAME = os.environ.get("CANDIDATE_USERNAME", "")

# VaxtaRekrut API (опционально; при отсутствии автозагрузка вакансий не выполняется)
VACANCY_API_URL = os.environ.get("VACANCY_API_URL", "https://platform.vaxtarekrut.ru/api/")
VACANCY_API_KEY = os.environ.get("VACANCY_API_KEY", "")

# Сохранение в файлы — только для истории; основной флоу не зависит от записи.
# При "0"/"false" все сохранения (questionnaire result json/txt, short.json, vacancies.json) отключены.
SAVE_RESULTS_TO_FILES = _truthy(os.environ.get("SAVE_RESULTS_TO_FILES", "1"))

# Режим команд: при True бот ждёт команды в ЛС после аутентификации по паролю (переопределяется из main при --command_mode).
COMMAND_MODE = _truthy(os.environ.get("COMMAND_MODE", "0"))
# Пароль для входа в режим команд (проверка при /command_mode).
COMMAND_MODE_PASSWORD = os.environ.get("COMMAND_MODE_PASSWORD", "")


# --- Базовые пути проекта ---

BASE_DIR = Path(__file__).resolve().parent

# Ресурсы
RESOURCE_DIR = BASE_DIR / "resource"
GREETINGS_PATH = RESOURCE_DIR / "json" / "greetings.json"
COMPANY_DATA_PATH = RESOURCE_DIR / "json" / "company_data.json"
QUESTIONS_PATH = RESOURCE_DIR / "json" / "questions.json"

# Результаты опросника
RESULTS_BASE_DIR = BASE_DIR / "questionnaire_results"
RESULTS_JSON_DIR = RESULTS_BASE_DIR / "json"
RESULTS_TEXT_DIR = RESULTS_BASE_DIR / "text"

# Результаты вакансий (CLI)
VACANCY_RESULTS_DIR = BASE_DIR / "results"

# Логи
LOG_DIR = BASE_DIR / os.environ.get("LOG_DIR", "logs")
LOG_FILE = LOG_DIR / os.environ.get("LOG_FILE", "errors.log")


def setup_logging() -> None:
    """
    Минимальная настройка логирования:
    - один файл LOG_FILE
    - формат: timestamp | LEVEL | message
    Вызывается по месту (userbot, CLI); idempotent.
    """
    LOG_DIR.mkdir(exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh.setFormatter(fmt)
    root.addHandler(fh)

