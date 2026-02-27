# UserBot — опросник в Telegram с OpenAI

Telegram **UserBot** (учётная запись, не бот): ведёт опрос в личных сообщениях, проверяет ответы через OpenAI, формирует выжимку и подбор вакансий (VaxtaRekrut), отправляет отчёт HR.

## Требования

- Python 3.10+
- Учётка Telegram (API: [my.telegram.org](https://my.telegram.org))
- OpenAI API key
- Опционально: VaxtaRekrut API (для автоподбора вакансий по результатам опроса)

## Установка

```bash
pip install -r requirements.txt
```

Конфигурация — через **переменные окружения** (см. `config.example.py`). Минимум:

- `TG_API_ID`, `TG_API_HASH`, `TG_PHONE` — Telegram
- `OPENAI_API_KEY`, `OPENAI_MODEL` (например `gpt-4o-mini`)
- `HR_ACCOUNT` — @username HR, куда уходят отчёты
- `CANDIDATE_USERNAME` — @username кандидата (в обычном режиме)

Опционально: `VACANCY_API_URL`, `VACANCY_API_KEY`; `SAVE_RESULTS_TO_FILES=1` — сохранение результатов в `questionnaire_results/`; для режима команд — `COMMAND_MODE_PASSWORD`.

## Запуск

**Обычный режим** — один кандидат из конфига, при старте отправляется приветствие и запускается опросник:

```bash
python main.py
```

**Режим команд** — без приветствия при старте; в ЛС оператор вводит пароль (`/command_mode`), задаёт HR и кандидата (`/set_hr`, `/set_candidate`), запускает опрос (`/start_questions`). После опроса или двух не-команд подряд сессия сбрасывается, режим команд действует до остановки процесса:

```bash
python main.py --command_mode
```

**CLI вакансий** (независимо от UserBot) — загрузка вакансий VaxtaRekrut с фильтрами, результат в `results/results.json`:

```bash
python download_vacancies.py [--filter-json '...'] [--short-json path]
```

## Структура

| Путь | Назначение |
|------|------------|
| `main.py` | Точка входа, `--command_mode` |
| `config.py` | Чтение env, пути, `setup_logging()` |
| `src/userbot.py` | Telethon, ЛС, команды, вызов опросника |
| `src/questionnaire.py` | Сценарий опроса, OpenAI, отчёт HR, short/vacancies |
| `src/openai_client.py` | validate_answer, summarize_questionnaire |
| `src/vacancies/` | API VaxtaRekrut, фильтры, топ-3 в отчёте |
| `resource/json/` | questions.json, greetings.json, company_data.json |

Логи — в каталог из `LOG_DIR` (по умолчанию `logs/`), файл — `LOG_FILE` (по умолчанию `errors.log`).
