# UserBot — опросник в Telegram с OpenAI и вакансиями VaxtaRekrut

Telegram **UserBot** (учётная запись, не бот): ведёт сценарий опроса в личных сообщениях, проверяет ответы через OpenAI,
делает краткую выжимку (short), подбирает вакансии через VaxtaRekrut API и отправляет описание вакансии HR и кандидату.
Ответы кандидату дополнены реалистичными задержками и индикатором «печатает» (можно отключить флагом).

## Требования

- Python 3.10+
- Учётка Telegram (API: `my.telegram.org`)
- OpenAI API key
- VaxtaRekrut API (для автоподбора вакансий по результатам опроса)

## Установка

```bash
pip install -r requirements.txt
```

Конфигурация — через **переменные окружения** (см. `.env.example`, `config.py`). Основные:

- Telegram: `TG_API_ID`, `TG_API_HASH`, `TG_PHONE`
- OpenAI: `OPENAI_API_KEY`, `OPENAI_MODEL` (например `gpt-4o-mini`)
- HR: `HR_ACCOUNT` — @username, куда уходят отчёты
- Вакансии: `VACANCY_API_URL`, `VACANCY_API_KEY`, `VACANCY_TOP_N` (по умолчанию 1)
- Логи/файлы:
  - `SAVE_RESULTS_TO_FILES` (1/0) — сохранить ли json/txt отчёта, short, vacancies, processed_users
  - `LOG_DIR`, `LOG_FILE` (по умолчанию `logs/`, `errors.log`)
- Режим команд: `COMMAND_MODE_PASSWORD`
- Задержки ответов кандидату:
  - `TOGGLE_DELAY` — `"ON"` (по умолчанию) или `"OFF"` (полностью отключить human-like задержки)
  - `TYPING_CHARS_PER_MIN`, `THINK_DELAY_MIN`, `THINK_DELAY_MAX`, `HUMAN_DELAY_MAX_TYPING_SEC`

## Запуск

### Обычный режим (опрос по списку кандидатов)

При старте бот берёт список кандидатов из `src/candidates_source.get_candidates()` (заглушка в коде)
и последовательно опрашивает каждого: приветствие → опрос → отчёт HR → отправка вакансии кандидату.

```bash
python main.py
```

Список кандидатов (username / телефон) и журнал обработанных сохраняются только если включён `SAVE_RESULTS_TO_FILES`.
Для каждого кандидата запись попадает в `questionnaire_results/processed_users.json`.

### Режим команд (command_mode)

В этом режиме бот **не шлёт приветствие сам** — оператор управляет опросом через команды в ЛС:

- `/command_mode` → запрос пароля (`COMMAND_MODE_PASSWORD`), после успешного ввода `authenticated=True`
- `/set_hr` → задать HR (`@username`)
- `/set_candidate` → задать кандидата (`@username`)
- `/start_questions` → запустить опрос (только после `/set_hr` и `/set_candidate`)
- `/cancel` → выйти из режима ожидания команд

Режим включается флагом:

```bash
python main.py --command_mode
```

Если после напоминания вместо команды приходят обычные сообщения, бот пишет «Выхожу из режима команд» и
сбрасывает аутентификацию; `--command_mode` остаётся активным до остановки процесса, можно снова войти по паролю.

## Структура проекта

| Путь | Назначение |
|------|------------|
| `main.py` | Точка входа, парсинг `--command_mode`, запуск `run_userbot()` |
| `config.py` | Чтение env, пути, флаги (включая TOGGLE_DELAY, SAVE_RESULTS_TO_FILES), `setup_logging()` |
| `src/userbot.py` | Telethon-клиент, обработка ЛС, режим команд, массовый опрос кандидатов |
| `src/questionnaire.py` | Сценарий опроса, работа с OpenAI, формирование текстового отчёта, short и блока вакансий |
| `src/openai_client.py` | `validate_answer`, `summarize_questionnaire` (генерация short с ФИО, регионом и т.п.) |
| `src/vacancies/` | API VaxtaRekrut, фильтры, обогащение, форматирование описаний вакансий и разбиение сообщений |
| `src/human_delay.py` | Human-like задержки и typing-индикатор перед ответами кандидату (управляется TOGGLE_DELAY) |
| `src/candidates_source.py` | Временный модуль-источник списка кандидатов (заглушка, легко заменить на файл/БД) |
| `src/candidates_utils.py` | Нормализация телефонов, подготовка записей кандидатов, журнал `processed_users.json` |
| `resource/json/` | `questions.json`, `greetings.json`, `company_data.json` для текстов и подстановок |
| `questionnaire_results/` | JSON/TXT отчёты, short, вакансии, `processed_users.json` (если включён SAVE_RESULTS_TO_FILES) |

Логи:

- Общие ошибки и информационные сообщения — в `LOG_FILE` (по умолчанию `logs/errors.log`).
- Специальный лог режима команд — в `logs/command_mode.log` (назначение HR/кандидата, оператор, ошибки пароля).
