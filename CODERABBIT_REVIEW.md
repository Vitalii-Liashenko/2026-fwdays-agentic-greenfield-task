# CodeRabbit Code Review — Список Виявлених Проблем

**Дата**: 2026-07-12  
**Курс**: Agentic Engineering: Greenfield  
**Проект**: Expense Tracker (Telegram Bot)

---

## 📋 Правила Робити З Цим Документом

1. **Послідовність**: Виправляти пункти в порядку (1→2→3... за категоріями Critical → High → Medium)
2. **Апрув**: Кожен пункт потребує явного апруву перед виправленням
3. **Тестування**: Після кожного виправлення запустити `pytest tests/ -m "not live_api"`
4. **Без автокоміту**: Коміти лише після явного запиту
5. **Документування**: В коміт-месіджі посилатися на пункт (наприклад, "Fix issue #1: DB_PASSWORD hardcoding")

---

## 🔴 CRITICAL ISSUES

### Issue #1: Hardcoded `DB_PASSWORD` (SECRET LEAK)

**Файл**: [src/config.py:20](src/config.py#L20)  
**Severity**: 🔴 CRITICAL  
**Category**: Security  

#### Проблема
```python
DB_PASSWORD = os.getenv("DB_PASSWORD", "tracker_password")
```
- Дефолтне значення `"tracker_password"` знаходиться в git-коді
- Навіть якщо `.env` не встановлено, цей пароль буде використаний
- Це нарушає принцип "secrets never in code"

#### Імпакт
- 🔓 Потенційна Security уязвимість: пароль DB видимий в історії git
- Будь-хто зі доступом до репозиторію може отримати дефолтний пароль

#### Виправлення
Зробити пароль обов'язковим, без дефолту:

```python
# Заміна:
DB_PASSWORD = os.getenv("DB_PASSWORD", "tracker_password")

# На:
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise ValueError("DB_PASSWORD is not set in .env")
```

#### Verification Checklist
- [ ] Код змінений
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] При запуску без .env файлу → `ValueError` з повідомленням
- [ ] Коміт зроблений з посиланням на Issue #1

#### Status
⏳ **Pending Approval**

---

### Issue #2: Race Condition у Langsmith Client Initialization

**Файл**: [src/agent.py:18-38](src/agent.py#L18-L38)  
**Severity**: 🔴 CRITICAL  
**Category**: Concurrency  

#### Проблема
```python
langsmith_client = None

def _init_langsmith_client():
    global langsmith_client
    # ... initialization at module load time
    langsmith_client = LangsmithClientClass(...)

_init_langsmith_client()
```

- Global variable ініціалізується при import модуля
- У многопоточному сценарії (async Telegram handlers) можлива race condition
- Якщо два потоки одночасно читають/пишуть в `langsmith_client`, це потенційно небезпечно

#### Імпакт
- 🧵 Race condition при конкурентному доступі
- Можлива невизначена поведінка у production з багатьма користувачами
- Незначна вірогідність, але не варто ризикувати

#### Виправлення
Використати thread-safe singleton з lock:

```python
import threading

_langsmith_client = None
_langsmith_lock = threading.Lock()

def _get_langsmith_client():
    """Thread-safe getter for Langsmith client."""
    global _langsmith_client
    if _langsmith_client is not None:
        return _langsmith_client
    
    with _langsmith_lock:
        if _langsmith_client is None:
            api_key = os.environ.get("LANGSMITH_API_KEY")
            project = os.environ.get("LANGSMITH_PROJECT")
            if not api_key or not project:
                return None
            try:
                from langsmith import Client as LangsmithClientClass
                endpoint = os.environ.get("LANGSMITH_ENDPOINT")
                _langsmith_client = LangsmithClientClass(api_key=api_key, api_url=endpoint)
                logger.info(f"Langsmith tracing enabled for project: {project}")
            except Exception as e:
                logger.warning(f"Langsmith initialization failed: {e}")
        return _langsmith_client
```

Замінити `langsmith_client` на `_get_langsmith_client()` скрізь у коді.

#### Verification Checklist
- [ ] Код змінений (додано lock і getter)
- [ ] Усі посилання на глобальну змінну замінені на функцію
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Langsmith functionality все ще працює (evals тести)
- [ ] Коміт зроблений з посиланням на Issue #2

#### Status
⏳ **Pending Approval**

---

### Issue #3: Incomplete Error Handling (Generic `psycopg2.Error`)

**Файл**: [src/storage.py:65-67](src/storage.py#L65-L67)  
**Severity**: 🔴 CRITICAL  
**Category**: Error Handling  

#### Проблема
```python
except psycopg2.Error as e:
    conn.rollback()
    raise StorageError(f"Failed to store expense: {e}")
```

- Ловимо generic `psycopg2.Error`, але не розрізняємо типи помилок
- `IntegrityError` (CHECK constraint violation) потребує інших лог-уванння/дій ніж `OperationalError` (connection loss)
- Користувачу складно розібратись, у чому проблема

#### Імпакт
- 🔧 Складна діагностика багів у production
- Користувачу видовується неправильна помилка
- Не можна відрізнити "плоха дата" від "БД упала"

#### Виправлення
Специфікувати виключення:

```python
from psycopg2 import IntegrityError, OperationalError, DatabaseError

def store_expense(self, expense: Expense, validation_errors: Optional[str] = None) -> int:
    """Store an expense in PostgreSQL."""
    conn = self._conn_factory()
    try:
        with conn.cursor() as cur:
            cur.execute("""...""", (...,))
            expense_id = cur.fetchone()[0]
            conn.commit()
            return expense_id
    except IntegrityError as e:
        # CHECK constraint violation (amount > 0, category in enum, etc.)
        conn.rollback()
        raise StorageError(f"Invalid expense data: {e}") from e
    except OperationalError as e:
        # Connection issues
        conn.rollback()
        raise StorageError(f"Database connection error: {e}") from e
    except DatabaseError as e:
        # Other database errors
        conn.rollback()
        raise StorageError(f"Database error: {e}") from e
    finally:
        conn.close()
```

Те ж саме у `store_expenses()` та інших методах, де ловимо `psycopg2.Error`.

#### Verification Checklist
- [ ] Код змінений (специфіковані виключення)
- [ ] Import додані в top of file
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Тести storage все ще покривають error paths
- [ ] Коміт зроблений з посиланням на Issue #3

#### Status
⏳ **Pending Approval**

---

## 🟠 HIGH PRIORITY ISSUES

### Issue #4: Missing `validation_logs` Cleanup Implementation

**Файл**: [src/storage.py](src/storage.py)  
**Severity**: 🟠 HIGH  
**Category**: Data Retention / Privacy  

#### Проблема
- Документована 30-day retention policy для `validation_logs` таблиці
- Але немає методу `clean_old_validation_logs()` в `ExpenseStore`
- Логи утримуватимуть інформацію про витрати без ліміту часу

#### Імпакт
- 📝 Дані користувача утримуються довше, ніж планується
- Нарушення GDPR/privacy policy (якщо така є)
- Технічний боргу для future cleanup

#### Виправлення
Додати метод очистки (ІЛИ позначити як OUT OF SCOPE для MVP):

**OPTION A: Додати cleanup метод** (Recommended)
```python
def clean_old_validation_logs(self, days: int = 30) -> int:
    """Delete validation logs older than N days. Returns count of deleted rows."""
    conn = self._conn_factory()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM validation_logs
                WHERE created_at < NOW() - INTERVAL '%s days'
                """,
                (days,)
            )
            deleted = cur.rowcount
            conn.commit()
            logger.info(f"Deleted {deleted} old validation logs (older than {days} days)")
            return deleted
    except DatabaseError as e:
        conn.rollback()
        raise StorageError(f"Failed to clean validation logs: {e}") from e
    finally:
        conn.close()
```

**OPTION B: Позначити як OUT OF SCOPE** (Quick fix for MVP)
- Додати в README § "Future Work / Out of Scope":
  ```markdown
  ### Out of Scope (Future Work)
  - Automatic cleanup of `validation_logs` (30-day retention): requires background job or cron scheduler
  - This is currently NOT implemented; logs persist indefinitely
  - **Recommendation**: Deploy a cron job or use a task scheduler (e.g., APScheduler) to call cleanup daily
  ```

#### Verification Checklist (if implementing cleanup)
- [ ] Код змінений (додана функція cleanup)
- [ ] Метод має proper error handling (DatabaseError vs OperationalError)
- [ ] Тести написані для cleanup (test_storage.py)
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Коміт зроблений з посиланням на Issue #4

#### Verification Checklist (if OUT OF SCOPE)
- [ ] README.md оновлений з новим розділом "Out of Scope"
- [ ] Потому на документування added (що потребується для implementation)
- [ ] Коміт зроблений з посиланням на Issue #4

#### Status
⏳ **Pending Approval** — Need decision: Implement or Out-of-Scope?

---

### Issue #5: Logger Configuration Duplication

**Файл**: [src/bot.py:14-17](src/bot.py#L14-L17)  
**Severity**: 🟠 HIGH  
**Category**: Code Quality / Logging  

#### Проблема
```python
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
```

- `basicConfig` викликається на рівні модуля, але `bot.py` не обов'язково main entry point
- Якщо інший модуль імпортує `bot.py`, конфіг може виконатися несподівано
- `basicConfig` встановлює глобальне логування, що може конфліктувати з іншими логерами

#### Імпакт
- 📝 Непередбачувана поведінка логування
- Якщо використовується асинх runtime або test runner, конфіг може не застосуватися
- Потенційна конфліктність з ботом Telegram (він теж має логування)

#### Виправлення
Перенести `basicConfig` в `__main__` блок:

```python
# src/bot.py — видалити на top level, залишити лише logger creation
logger = logging.getLogger(__name__)

# ... решта кода ...

if __name__ == "__main__":
    # Setup logging only when running as main
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger.info("Starting bot...")
    main()
```

#### Verification Checklist
- [ ] Код змінений (basicConfig перенесена в __main__)
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Логування все ще працює при запуску `python -m src.bot`
- [ ] Тести не мають побічних ефектів від basicConfig
- [ ] Коміт зроблений з посиланням на Issue #5

#### Status
⏳ **Pending Approval**

---

### Issue #6: Error Messages in Mixed Languages (UX Inconsistency)

**Файл**: [src/agent.py:40-83](src/agent.py#L40-L83), [src/processor.py:50-102](src/processor.py#L50-L102)  
**Severity**: 🟠 HIGH  
**Category**: UX / Localization  

#### Проблема
- Одні помилки українською (в bot.py: "❌ Помилка обробки")
- Інші англійською (Exception messages: "Invalid ISO 8601 datetime")
- Користувачу видовується мішана мова

#### Імпакт
- 🌐 Непрофесійна UX для користувача
- Складніше тестувати помилки (regex matching)
- Якщо додається локалізація, це буде технічний борг

#### Виправлення
Централізовані повідомлення про помилки у константи:

```python
# src/config.py — додати в end of file

# Error messages (Ukrainian)
ERROR_MESSAGES = {
    "AMOUNT_REQUIRED": "Сума витрати не вказана або некоректна. Будь ласка, надайте число > 0.",
    "INVALID_CATEGORY": "Категорія витрати не розпізнана. Скористайтеся однією з 8 стандартних.",
    "INVALID_DATETIME": "Дата/час некоректна. Будь ласка, вкажіть у форматі ISO 8601 або відносно (наприклад, 'годину назад').",
    "EMPTY_DESCRIPTION": "Опис витрати не може бути порожнім.",
    "PARSE_FAILED": "Не вдалось розпізнати витрату. Будь ласка, надайте суму та категорію більш чітко.",
    "VALIDATION_FAILED": "Помилка валідації витрати. Спробуйте ще раз.",
    "DB_CONNECTION_ERROR": "Помилка підключення до БД. Спробуйте пізніше.",
    "DB_INTEGRITY_ERROR": "Некоректні дані витрати. Перевірте суму та категорію.",
    "PROCESSING_FAILED": "Не вдалось обробити витрату після 3 спроб. Спробуйте ще раз або надайте більше деталей.",
}
```

Потім замінити hardcoded messages на посилання до констант:

```python
# src/processor.py
if not expenses:
    feedback = ERROR_MESSAGES["PARSE_FAILED"]
    # ...

# src/validator.py
raise ValueError(ERROR_MESSAGES["AMOUNT_REQUIRED"])
```

#### Verification Checklist
- [ ] Константи додані в config.py
- [ ] Усі hardcoded messages замінені на посилання
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Всі повідомлення про помилки українською
- [ ] Коміт зроблений з посиланням на Issue #6

#### Status
⏳ **Pending Approval**

---

### Issue #7: No Validation of LLM Output Structure Before Use

**Файл**: [src/agent.py:100, 154-159](src/agent.py#L100,#L154-L159)  
**Severity**: 🟠 HIGH  
**Category**: Error Handling / Observability  

#### Проблема
```python
result = active_chain.invoke({"received_at": now.isoformat(), "user_input": expense_input})
logger.debug(f"Chain returned ExpenseList: {result}")
expenses = result.expenses
```

- `llm.with_structured_output(ExpenseList)` гарантує структуру, але при помилці LLM
- Немає явного логування JSON-структури перед парсингом
- Якщо структурний output не спрацює, помилка буде неясна

#### Імпакт
- 🔍 Складна діагностика LLM помилок
- Важко traceback, що повернув LLM при hard-fail
- Не можна верифікувати, що LLM дійсно повернув JSON

#### Виправлення
Додати деталізоване логування LLM output:

```python
def extract_expense(user_input: str, feedback: Optional[str] = None, chain=None) -> list[Expense]:
    """Extract structured expenses from user input using LangChain."""
    logger.debug(f"extract_expense called with input: {user_input}, feedback: {feedback}")
    now = datetime.now()

    expense_input = user_input
    if feedback:
        expense_input = f"{user_input}\n\nValidation feedback: {feedback}\n\nPlease retry and correct the issue."

    active_chain = chain or _get_chain()
    logger.debug(f"Invoking chain with received_at={now.isoformat()}, user_input={expense_input}")
    
    try:
        result = active_chain.invoke({"received_at": now.isoformat(), "user_input": expense_input})
        
        # Log raw structure for debugging
        logger.debug(f"Chain returned type: {type(result)}, value: {result}")
        
        if not isinstance(result, ExpenseList):
            logger.error(f"Unexpected chain output type: {type(result)}")
            raise ValueError(f"Expected ExpenseList, got {type(result)}")
        
        expenses = result.expenses
        logger.debug(f"Extracted {len(expenses)} expense(s): {[e.dict() for e in expenses]}")
        _add_langsmith_metadata(expenses)
        return expenses
        
    except Exception as e:
        logger.error(f"Chain invocation failed: {e}", exc_info=True)
        raise
```

#### Verification Checklist
- [ ] Код змінений (додано детальне логування)
- [ ] Type check добавлен після invoke
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Agent еще работает правильно с ланчейном
- [ ] Логування відображає очікуваний ExpenseList
- [ ] Коміт зроблений з посиланням на Issue #7

#### Status
⏳ **Pending Approval**

---

## 🟡 MEDIUM PRIORITY ISSUES

### Issue #8: Confidence Score Logic Not Documented

**Файл**: [src/agent.py:78-81](src/agent.py#L78-L81)  
**Severity**: 🟡 MEDIUM  
**Category**: Documentation  

#### Проблема
```python
8. Confidence: 0.9-1.0 for clear input, 0.7-0.8 for slightly ambiguous, 0.3-0.6 for vague, less than 0.3 for too vague.
```

- Діапазони вказані, але немає пояснення логіки
- Як LLM має розраховувати? Що означає "clear"?
- Складно верифікувати, що LLM робить це правильно

#### Імпакт
- 🤔 LLM може використовувати інші шкали
- Невизначена поведінка (nondeterministic)
- Складна еваліація

#### Виправлення
Додати детальний docstring до системного промпту:

```python
SYSTEM_PROMPT = """You are an expense parser agent...

CONFIDENCE SCORING RULES:
Your confidence score (0.0–1.0) reflects how certain you are in the extraction:
- 0.9–1.0: Clear, unambiguous input with explicit amount and category. Example: "купив каву за 50" → 0.95
- 0.8–0.89: Mostly clear but some minor ambiguity (time not specified, slight category overlap). Example: "50 на каву сьогодні" → 0.85
- 0.7–0.79: Slightly ambiguous but resolvable. Example: "витратив 50 на дрібниці" (category could be Покупки or Інше) → 0.75
- 0.5–0.69: Ambiguous category but a real amount is present. Example: "купив якусь дрібницю за 20" → 0.55
- 0.3–0.49: Very vague; category is essentially a guess. Example: "витратив на якусь річ" + amount from context → 0.35
- < 0.3: Reserved for cases where you genuinely cannot determine category BUT a valid amount exists. DO NOT use this as substitute for missing amount.

SCORING ALGORITHM:
1. Start at 1.0
2. Deduct 0.05 for each ambiguous element (no time, unclear category, typo in amount)
3. Deduct 0.2 if category is Інше (catch-all)
4. Deduct 0.3 if amount required inference (e.g., user said "біля 50" instead of "50")
5. Final score = max(0.0, min(1.0, base - deductions))
"""
```

#### Verification Checklist
- [ ] Код змінений (SYSTEM_PROMPT розширений)
- [ ] Логіка scoring явно описана
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Reasoning evals перевіряють, що confidence відповідає логіці
- [ ] Коміт зроблений з посиланням на Issue #8

#### Status
⏳ **Pending Approval**

---

### Issue #9: No Explicit Timezone Handling / Comment Missing

**Файл**: [src/agent.py:144](src/agent.py#L144)  
**Severity**: 🟡 MEDIUM  
**Category**: Code Clarity  

#### Проблема
```python
now = datetime.now()
```

- `datetime.now()` повертає наївну дату (без timezone info)
- Коректно за спецом, але легко помилитися при міграції
- Немає коментаря про припущення щодо timezone

#### Імпакт
- 🌍 Якщо буде потреба в UTC в майбутньому, буде difficult migration
- Інший розробник може не зрозуміти, чому это наївне
- Потенційні bugs при міграції

#### Виправлення
Додати коментар про припущення:

```python
def extract_expense(user_input: str, feedback: Optional[str] = None, chain=None) -> list[Expense]:
    """
    Extract structured expenses from user input using LangChain.
    
    Note: All timestamps are assumed to be in LOCAL timezone (naive datetime).
    The system does NOT use UTC; migration to UTC would require schema changes.
    """
    logger.debug(f"extract_expense called with input: {user_input}, feedback: {feedback}")
    # Naive datetime in local timezone. This matches the spec: datetimes are inferred
    # relative to "Message received at" which is generated locally (not in UTC).
    now = datetime.now()
```

#### Verification Checklist
- [ ] Код змінений (коментар додан)
- [ ] Docstring розширений з timezone notes
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Коміт зроблений з посиланням на Issue #9

#### Status
⏳ **Pending Approval**

---

### Issue #10: Type Hints Could Be More Specific

**Файл**: [src/processor.py:4, 16](src/processor.py#L4,#L16)  
**Severity**: 🟡 MEDIUM  
**Category**: Code Quality / Type Safety  

#### Проблема
```python
from typing import Optional, Callable, List

def process_expense(
    raw_text: str,
    extract_fn: Callable = None,
    validate_fn: Callable = None,
) -> ProcessExpenseResult:
```

- `Callable` без специфікації сигнатури (args/return type)
- IDE не може робити type checking для inject-ed функцій
- Інший розробник не знає, які args очікуються

#### Імпакт
- 🔧 Слабше type checking у IDE
- Складніше писати тести з mock функціями
- Потенційні runtime errors

#### Виправлення
Додати Protocol для типу:

```python
from typing import Optional, List, Callable, Protocol
from .models import Expense, ProcessExpenseResult

class ExpenseExtractor(Protocol):
    """Signature for expense extraction function."""
    def __call__(self, user_input: str, feedback: Optional[str] = None) -> List[Expense]: ...

class ExpenseValidator(Protocol):
    """Signature for expense validation function."""
    def __call__(self, expenses: List[Expense]) -> "ValidationResult": ...

def process_expense(
    raw_text: str,
    extract_fn: Optional[ExpenseExtractor] = None,
    validate_fn: Optional[ExpenseValidator] = None,
) -> ProcessExpenseResult:
    """
    Process a raw user input: parse with agent, validate with checker, retry on hard-fail.
    
    Args:
        raw_text: User input text to process.
        extract_fn: Optional custom expense extractor (for testing). Defaults to extract_expense.
        validate_fn: Optional custom expense validator (for testing). Defaults to validate_expenses.
    
    Returns:
        ProcessExpenseResult with success flag, expenses list, and message.
    """
```

#### Verification Checklist
- [ ] Код змінений (Protocol додані)
- [ ] Type hints оновлені на функціях
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] IDE type checking працює
- [ ] Коміт зроблений з посиланням на Issue #10

#### Status
⏳ **Pending Approval**

---

### Issue #11: Missing Docstring on `extract_expense` `chain` Parameter

**Файл**: [src/agent.py:128-142](src/agent.py#L128-L142)  
**Severity**: 🟡 MEDIUM  
**Category**: Documentation  

#### Проблема
```python
def extract_expense(user_input: str, feedback: Optional[str] = None, chain=None) -> list[Expense]:
    """
    Extract structured expenses from user input using LangChain.
    
    Args:
        user_input: Free-form Ukrainian text describing one or more expenses.
        feedback: Optional validation feedback from a prior failed attempt.
        chain: Optional LangChain chain to use. Defaults to lazily-initialized module chain.
    """
```

- Параметр `chain` задокументований, але його назначення (для testing!) не пояснене
- Не зрозуміло, чому це експортується як public parameter
- Розробник може помилитися, використовуючи його

#### Імпакт
- 🧪 Неясна testability
- Складніше писати unit тести
- Потенційний misuse

#### Виправлення
Розширити docstring:

```python
def extract_expense(user_input: str, feedback: Optional[str] = None, chain=None) -> list[Expense]:
    """
    Extract structured expenses from user input using LangChain.

    Args:
        user_input: Free-form Ukrainian text describing one or more expenses.
        feedback: Optional validation feedback from a prior failed attempt.
                 When provided, appended to user_input to guide LLM retry.
        chain: Optional LangChain chain to use (for testing only; allows injection of mock).
               Defaults to lazily-initialized module chain from _get_chain().
               DO NOT use in production; use only in unit tests to inject test doubles.

    Returns:
        List of Expense objects (one per detected purchase).

    Raises:
        ValueError: If LLM response is malformed or validation fails.
    """
```

#### Verification Checklist
- [ ] Код змінений (docstring розширений)
- [ ] Пояснено, що це для testing
- [ ] Тести проходять: `pytest tests/ -m "not live_api"` — ✅ all pass
- [ ] Коміт зроблений з посиланням на Issue #11

#### Status
⏳ **Pending Approval**

---

## ✅ VERIFIED CORRECT (No Changes Needed)

The following practices are correctly implemented:

- ✓ **Pydantic validators on hard-fail rules** — amount, category, datetime, description, confidence validation at construction
- ✓ **Two-level retry architecture** — chain-level (LangChain with tenacity) + processor-level (explicit loop with feedback)
- ✓ **Langsmith integration with optional config** — properly guards with API key checks
- ✓ **Test coverage** — happy path + edge cases (49 tests passing)
- ✓ **Async/await correct** — bot.py uses `asyncio.to_thread()` for sync operations properly
- ✓ **Injection-friendly design** — conn_factory, extract_fn, validate_fn allow testing

---

## 📊 Summary

| Category | Count | Status |
|----------|-------|--------|
| 🔴 Critical | 3 | ⏳ Pending |
| 🟠 High | 4 | ⏳ Pending |
| 🟡 Medium | 4 | ⏳ Pending |
| ✅ Correct | 6 | ✓ No changes needed |

**Total Issues**: 11 + 6 verified correct

---

## 🚀 Workflow

1. Present each issue to user (Critical first)
2. User approves/rejects
3. If approved: implement fix
4. Run: `pytest tests/ -m "not live_api"`
5. If tests pass: Mark issue as **✅ Fixed**
6. If tests fail: Revert and investigate
7. Commit (only when user asks)

**Current Status**: Ready for Issue #1 review

