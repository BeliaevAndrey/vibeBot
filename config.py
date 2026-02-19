"""
Конфигурация из переменных окружения.
"""

import os

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
PHONE = os.environ.get("PHONE", "")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

HR_ACCOUNT = os.environ.get("HR_ACCOUNT", "")
CANDIDATE_USERNAME = os.environ.get("CANDIDATE_USERNAME", "")
