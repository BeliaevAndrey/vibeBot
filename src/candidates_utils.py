"""
Утилиты работы с кандидатами для массового опроса.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from config import SAVE_RESULTS_TO_FILES, PROCESSED_USERS_PATH

UTC_PLUS_3 = timezone(timedelta(hours=3))


def _normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Нормализовать телефон: оставить цифры и ведущий '+', привести к формату +7... там, где это уместно."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    cleaned: list[str] = []
    for i, ch in enumerate(s):
        if ch.isdigit():
            cleaned.append(ch)
        elif ch == "+" and i == 0:
            cleaned.append(ch)
    if not cleaned:
        return None
    val = "".join(cleaned)
    if val.startswith("+"):
        base = val
    else:
        digits = val
        if digits.startswith("8"):
            base = "+7" + digits[1:]
        elif digits[0] in ("7", "9"):
            base = "+7" + digits
        else:
            # Не узнаём формат — считаем номер некорректным
            return None
    digits_only = "".join(ch for ch in base if ch.isdigit())
    if len(digits_only) < 10:
        return None
    return base


def _prepare_candidate_entry(username: Optional[str], phone_raw: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    """Нормализовать username/phone; если оба отсутствуют или некорректны — вернуть None."""
    uname = (username or "").strip()
    if uname and not uname.startswith("@"):
        uname = f"@{uname}"
    else:
        uname = uname or None
    phone = _normalize_phone(phone_raw)
    if not uname and not phone:
        return None
    return {"username": uname, "phone": phone}


def _record_processed(
    processed_users: Dict[int, Dict[str, Any]],
    user_id: Optional[int],
    username: Optional[str],
    phone: Optional[str],
    success: bool,
    error: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Зафиксировать результат обработки кандидата и сохранить в processed_users.json (если включено).
    """
    if not SAVE_RESULTS_TO_FILES:
        return
    key: int
    if user_id is not None:
        key = int(user_id)
    else:
        key = -(len(processed_users) + 1)
    processed_users[key] = {
        "username": username,
        "phone": phone,
        "processed": datetime.now(UTC_PLUS_3).isoformat(),
        "success": success,
        "error": error,
    }
    try:
        PROCESSED_USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PROCESSED_USERS_PATH, "w", encoding="utf-8") as f:
            json.dump(processed_users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        (logger or logging.getLogger("userbot")).exception("Save processed_users failed: %s", e)

