---
name: ""
overview: ""
todos: []
isProject: false
---

# Интеграция validate_answer

## Уточнение по resource/json/questions.json

Файл [resource/json/questions.json](resource/json/questions.json) изменён:

- **Формат**: массив объектов `[ { "question": "...", "acceptance": "..." }, ... ]`.
- **Критерии**: поле называется `**acceptance`** (одна строка), не `criteria` (массив).
- **Параметр `title`**: удалён, не используется.

При интеграции учесть:

- В questionnaire при работе с вопросами: загружать список, индексировать по номеру (0, 1, 2, …). Функции `get_question_keys()` / `get_question_text()` / `get_question_full()` должны работать с массивом (ключи — индексы).
- Для `validate_answer(question, answer, acceptance_criteria="")` передавать в `acceptance_criteria` значение `**q_full.get("acceptance", "")**` (одна строка), без сборки из массива критериев и без использования `title`.

---

## Текущее состояние

- **[src/validate.py](src/validate.py)**: функция `validate_answer(question, answer, acceptance_criteria="")` возвращает `(valid: bool, human_response: str)`. Использует OpenAI с tool calling. Ошибки: обращение к `openai_client.chat.completions.create` (ожидается объект клиента), синтаксис `except Exception as e:print(...)`.
- **[src/questionnaire.py](src/questionnaire.py)** (handle_answer): промпт из question_prompt.txt, get_completion, парсинг JSON, profanity_detected / compliance_percent / summary_comment; при оценке используются `question_title`, `criteria` (массив) — заменить на работу с массивом вопросов и полем `acceptance`.
- **[src/openai_client.py](src/openai_client.py)**: get_completion, get_reply, evaluate_agreement; клиент через config.

## План действий

### 1. Адаптация к новому questions.json (в questionnaire.py)

- `_load_questions()`: возвращать список (array), тип `list[dict]`.
- `get_question_keys()`: возвращать список индексов, например `[str(i) for i in range(len(questions))]` или `list(range(len(questions)))` в зависимости от того, как хранится `current_q_index` (если по индексу int — оставить int).
- `get_question_text(q_key)` и `get_question_full(q_key)`: обращение к элементу по индексу `questions[int(q_key)]`, без использования `title`; в full только `question` и `acceptance`.

### 2. validate_answer в openai_client.py

- Добавить `validate_answer(question: str, answer: str, acceptance_criteria: str = "") -> tuple[bool, str]`.
- Клиент и модель из config; тот же system/user messages и tools/tool_choice, что в validate.py.
- Парсинг tool_calls → valid, human_response; при ошибке возвращать `(True, "")` и логировать.

### 3. Замена обработки ответа в handle_answer

- Убрать загрузку промпта, get_completion, _parse_llm_json, использование question_title и criteria (массива).
- Вызов: `valid, human_response = await asyncio.to_thread(openai_client.validate_answer, question_text, message_text, acceptance_criteria)` где `acceptance_criteria = q_full.get("acceptance", "")`.
- Report: compliance_percent 100/0, comment = human_response при не valid, поле `invalid`: True при не valid; profanity_detected: False.
- При не valid: ответить human_response, не увеличивать current_q_index. При valid: увеличить индекс и перейти к следующему вопросу или завершить.

### 4. Отчёт и rejected_answer

- В build_questionnaire_result_from_state: сохранять rejected_answer при `r.get("profanity_detected")` или `r.get("invalid")`.

### 5. Удаление

- Удалить [src/validate.py](src/validate.py) после переноса. Убрать использование _load_prompt_template / разбор шаблона из handle_answer.

