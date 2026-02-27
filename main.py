#!/usr/bin/env python3
"""
Точка входа: Telegram UserBot с ответами через OpenAI.
"""

import argparse
import os

# При --command_mode не используем CANDIDATE_USERNAME из env (оставляем пустым до /set_candidate).
def _parse_args():
    p = argparse.ArgumentParser(description="Telegram UserBot, опросник с OpenAI.")
    p.add_argument("--command_mode", action="store_true", help="Режим команд: ждать команды в ЛС после аутентификации.")
    return p.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    if args.command_mode:
        os.environ["COMMAND_MODE"] = "1"
        os.environ["CANDIDATE_USERNAME"] = ""
    # Импорт после возможного изменения env
    from src.userbot import run_userbot
    run_userbot(command_mode=args.command_mode)
