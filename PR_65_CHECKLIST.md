# PR #65 — Чеклист Релевантних Зауважень

## 🔴 Критичні Проблеми (Перед Мерджем)

### Опис PR
- [ ] Додати повне ім'я автора
- [ ] Додати посилання на демо-відео (1–2 хвилини)
- [ ] Описати практики Agentic Engineering, які застосовані
- [ ] Вказати використані інструменти й MCP
- [ ] Описати розподіл роботи між студентом і агентом

### Безпека & Конфігурація
- [ ] Замінити `tracker_password` в `.env.example` на пусту строку або плейсхолдер
- [ ] Вилучити жорстко задані PostgreSQL credentials з `docker-compose.yml`; отримувати з змінних середовища
- [ ] Додати валідацію обов'язкових API ключів в `src/config.py` при стартапі
- [ ] Перенести логування фінансових даних користувача з INFO на DEBUG рівень у `src/bot.py` та `src/agent.py`; або редагувати чутливі дані

### Приватність & Утримання Даних
- [ ] Додати retention policy для validation_logs у `migrations/init.sql`
- [ ] Забезпечити explicit opt-in контроль для LangSmith трейсингу
- [ ] Редагувати фінансові/особисті дані перед відправкою в LangSmith
- [ ] Додати контроль доступу на таблицю `validation_logs`

## 🟠 Крупні Функціональні Проблеми

### Архітектура Retry
- [ ] Визначити, чи обидва рівні retry (LangChain chain-level + processor loop) навмисні
- [ ] Оновити дизайн-документацію, якщо потрібна зміна архітектури

### Multi-Expense Контракт
- [ ] Синхронізувати специфікацію: AGENTS.md — джерело істини
- [ ] Уточнити, чи підтримується один input = один expense або більше
- [ ] Оновити всі посилання (parser, validator, тести, storage)

### Валідація Amount
- [ ] Змінити логіку на: відхилити null amounts, запросити уточнення у користувача
- [ ] Прибрати "best guess" fallback для відсутніх сум

### Інваріанти БД
- [ ] Додати CHECK constraint: `currency='UAH'`
- [ ] Додати CHECK constraint: `category IN (8 canonical values)`
- [ ] Додати CHECK constraint: `confidence IN [0,1]`
- [ ] Додати CHECK constraint: `amount > 0`

## 📋 Документація & Специфікація

### Консолідація
- [ ] Уніфікувати "9 reasoning evals" vs "10 test cases" в PRD
- [ ] Визначити одне число для evals/tests

### Datetime Inference
- [ ] Уточнити, що дата повинна браться з message receipt timestamp, а не "сьогодні"

### ExpenseStore Design
- [ ] Розв'язати конфлікти на backward-compatibility для wrappers

### Метрики評valuation
- [ ] Додати детерміністичні формули для Amount accuracy
- [ ] Покрити multi-expense partial matches

## 🔧 Якість Коду

### Документація
- [ ] Досягти 80% docstring покриття (поточно 0%)

### Type Annotations
- [ ] Виправити return type для `_store_with()` (задекларовано `ExpenseStore`, повертає tuple)

### Constants
- [ ] Замінити hardcoded `0.7` на named constant для confidence threshold

### Cleanup
- [ ] Видалити неиспользуемі metadata assignment в `evals.py`

## ⚙️ Процес & Тестування

### Тести
- [ ] Замокувати зовнішні LLM calls в unit тестах (flaky CI)
- [ ] Витягти live API тести в окремий набір
- [ ] Добавити verify retry in `test_integration_hard_fail_retry` (mock call count)
- [ ] Добавити failure state assertion в `test_integration_error_message`
- [ ] Верифікувати feedback injection на retry attempt в `test_processor.py`

### Доказ
- [ ] Додати воспроизводимые evidence для completed tasks
- [ ] Включити реальні команди тестування й результати pass rates

### Spec Sync
- [ ] Прояснити OpenSpec sync rules (ADDED requirements не повинні молча перезаписувати)
- [ ] Потребувати explicit confirmation перед overwrite існуючих specs
