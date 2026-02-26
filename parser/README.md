# Загрузка вакансий VaxtaRekrut

Скрипт скачивает вакансии с API платформы VaxtaRekrut с фильтрами и сохраняет результат в `results/results.json`.

## Требования

- Python 3.9+
- Зависимости: `requests`, `beautifulsoup4`

## Настройка

В корне проекта создайте `.env`:

```
VACANCY_API_URL=https://platform.vaxtarekrut.ru/api/
VACANCY_API_KEY=<ваш Bearer-токен>
```

## Запуск

Перед запуском загрузите переменные окружения, например:

```bash
export $(grep -v '^#' .env | xargs)
```

**Интерактивный режим** (выбор фильтров по меню):

```bash
python download_vacancies.py
```

**С готовым JSON-фильтром:**

```bash
python download_vacancies.py --filter-json '{"$and":[...]}'
```

**Опции:** `--limit N` — сколько вакансий вывести в консоль (по умолчанию 10); `--no-print` — не выводить в консоль, только сохранить в файл.
