"""Parser agent: LLM-powered expense extraction from free-form Ukrainian text."""

import logging
import os
from datetime import datetime
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from tenacity import stop_after_attempt, retry_if_exception_type

from .config import OPENAI_API_KEY, LLM_MODEL
from .models import Expense, ExpenseList

logger = logging.getLogger(__name__)

# Langsmith client singleton — initialized at module load if credentials are set
langsmith_client = None


def _init_langsmith_client():
    """Initialize Langsmith client if LANGSMITH_API_KEY and LANGSMITH_PROJECT are set."""
    global langsmith_client
    api_key = os.environ.get("LANGSMITH_API_KEY")
    project = os.environ.get("LANGSMITH_PROJECT")
    if not api_key or not project:
        return
    try:
        from langsmith import Client as LangsmithClientClass
        endpoint = os.environ.get("LANGSMITH_ENDPOINT")
        langsmith_client = LangsmithClientClass(api_key=api_key, api_url=endpoint)
        logger.info(f"Langsmith tracing enabled for project: {project} (endpoint: {endpoint or 'default'})")
    except Exception as e:
        logger.warning(f"Langsmith initialization failed, tracing disabled: {e}")
        langsmith_client = None


_init_langsmith_client()

# System prompt for the LLM (refers to AGENTS.md content)
SYSTEM_PROMPT = """You are an expense parser agent. Your task is to extract structured expense data from free-form Ukrainian text.

You MUST return a valid JSON of expense objects. The response will be automatically parsed into structured format.

MULTIPLE EXPENSES: If the user describes more than one distinct purchase with separate amounts, return one object per purchase.
COMBINED TOTALS: If the user lists multiple items but gives only one total amount, return a single expense for that total amount.

EXAMPLES:
Input: "купив каву за 50 і хліб за 30"
Output: (expenses array with two objects: amount 50 and 30)

Input: "купив пиво і воду за 30"
Output: (expenses array with one object: amount 30)

Input: "купив каву за 50"
Output: (expenses array with one object: amount 50)

CATEGORY VOCABULARY (must be one of these 8):
- Продукти (groceries, food shopping)
- Транспорт (gas, transit, taxi)
- Кафе/Ресторани (dining out)
- Комуналки (utilities, rent)
- Розваги (entertainment, hobbies)
- Здоров'я (healthcare, pharmacy)
- Покупки (clothing, household goods)
- Інше (catch-all for unclear)

DATETIME INFERENCE RULES (apply in order, independently for each expense):
1. Explicit time given (e.g., о 18:30, в 14:00) -> use it. If no date given, use today's date from Message received at.
2. Relative time given (e.g., годину назад, 2 години тому, хвилину назад) -> subtract the offset from the Message received at timestamp.
3. Date only, no time (e.g., вчора, 2026-06-25, у п'ятницю) -> use midnight (00:00:00) of that date.
4. No date and no time at all -> copy the Message received at timestamp EXACTLY, character for character.

CRITICAL: NEVER use a date from your training data. The ONLY valid source of today's date is the Message received at field. If you are unsure, use Message received at verbatim.

OTHER RULES:
5. Always return ISO 8601 datetime without timezone suffix (e.g., 2026-06-28T14:30:00).
6. Amount must be > 0 or null if unknown.
7. Category must be one of the 8 above or null if too vague.
8. Confidence: 0.9-1.0 for clear input, 0.7-0.8 for slightly ambiguous, 0.3-0.6 for vague, less than 0.3 for too vague.
9. Do NOT add extra fields or omit required fields in any object.
10. Do NOT hallucinate categories outside the vocabulary.
11. Preserve original text in description unless normalizing for clarity."""

MAX_RETRIES = 3

# Initialize LLM
llm = ChatOpenAI(model=LLM_MODEL, temperature=0.3, api_key=OPENAI_API_KEY)

# Create prompt template
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "Message received at: {received_at}\nParse this expense: {user_input}"),
    ]
)

# Build LCEL chain with structured output and retry
chain = (prompt | llm.with_structured_output(ExpenseList)).with_retry(
    stop_after_attempt=MAX_RETRIES,
    retry_if_exception_type=(ValueError,)
)


def _add_langsmith_metadata(expenses: list[Expense]) -> None:
    """Attach extracted expense metadata to the current Langsmith run, if active."""
    if langsmith_client is None:
        return
    try:
        from langsmith import get_current_run_tree
        run = get_current_run_tree()
        if run is not None:
            run.metadata.update({
                "amounts": [e.amount for e in expenses],
                "categories": [e.category for e in expenses],
                "confidences": [e.confidence for e in expenses],
            })
    except Exception as e:
        logger.debug(f"Langsmith metadata update skipped: {e}")


def extract_expense(user_input: str, feedback: Optional[str] = None) -> list[Expense]:
    """
    Extract structured expenses from user input using LangChain.

    Decorated with @traceable when Langsmith is configured (LANGCHAIN_TRACING_V2=true).

    Args:
        user_input: Free-form Ukrainian text describing one or more expenses.
        feedback: Optional validation feedback from a prior failed attempt.

    Returns:
        List of Expense objects (one per detected purchase).

    Raises:
        ValueError: If LLM response is malformed or validation fails.
    """
    logger.info(f"extract_expense called with input: {user_input}, feedback: {feedback}")
    now = datetime.now()

    # Append feedback to user_input if provided
    expense_input = user_input
    if feedback:
        expense_input = f"{user_input}\n\nValidation feedback: {feedback}\n\nPlease retry and correct the issue."

    logger.debug(f"Invoking chain with received_at={now.isoformat()}, user_input={expense_input}")
    try:
        result = chain.invoke({"received_at": now.isoformat(), "user_input": expense_input})
        logger.info(f"Chain returned ExpenseList: {result}")
        expenses = result.expenses
        logger.info(f"Extracted {len(expenses)} expense(s)")
        _add_langsmith_metadata(expenses)
        return expenses
    except Exception as e:
        logger.error(f"Chain invocation failed: {e}")
        raise


def submit_feedback(
    run_id: str,
    expected_category: str,
    expected_amount: Optional[float],
    notes: str = "",
) -> None:
    """Submit a correction to Langsmith for evaluator training.

    Non-blocking: errors are logged and swallowed so callers are unaffected.
    """
    if langsmith_client is None:
        logger.debug("Langsmith not configured; feedback submission skipped")
        return
    try:
        langsmith_client.create_feedback(
            run_id=run_id,
            key="correction",
            score=0,
            value={
                "expected_category": expected_category,
                "expected_amount": expected_amount,
                "notes": notes,
            },
        )
        logger.info(f"Feedback submitted for run {run_id}")
    except Exception as e:
        logger.warning(f"Langsmith feedback submission failed: {e}")
