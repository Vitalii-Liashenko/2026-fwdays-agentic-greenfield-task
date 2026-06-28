"""Expense processor: orchestrates agent → validator → storage."""

import logging
from typing import Optional

from .agent import extract_expense
from .validator import validate_expenses
from .models import Expense, ProcessExpenseResult
from .config import MAX_RETRIES

logger = logging.getLogger(__name__)


def process_expense(raw_text: str) -> ProcessExpenseResult:
    """
    Process a raw user input: parse with agent, validate with checker, retry on hard-fail.

    Orchestrates:
    1. Agent extracts a list of expenses from raw_text
    2. Validator checks all expenses in the list
    3. If hard-fail, agent retries (max 3 times) with combined feedback
    4. If soft-fail, expenses are marked but stored
    5. Returns result for storage/reply

    Args:
        raw_text: User input text to process.

    Returns:
        ProcessExpenseResult with success flag, expenses list, and message.
    """
    logger.info(f"Starting process_expense for input: {raw_text}")
    expenses: list[Expense] = []
    feedback: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Attempt {attempt}/{MAX_RETRIES}: extracting expenses...")
            expenses = extract_expense(raw_text, feedback=feedback)
            logger.info(f"Expenses extracted: {expenses}")

            logger.info("Validating expenses...")
            validation = validate_expenses(expenses)
            logger.info(f"Validation result: valid={validation.valid}, errors={validation.errors}")

            if validation.valid:
                count = len(expenses)
                message = f"✅ {'Витрата записана' if count == 1 else f'{count} витрати записано'}"
                if validation.errors:
                    message += " (низька впевненість)"
                    logger.info(f"Soft-fail with errors: {validation.errors}")
                    return ProcessExpenseResult(
                        success=True,
                        expenses=expenses,
                        errors=validation.errors,
                        message=message,
                        validation_errors="; ".join(validation.errors),
                    )
                else:
                    logger.info("Validation passed")
                    return ProcessExpenseResult(
                        success=True,
                        expenses=expenses,
                        message=message,
                    )
            else:
                logger.warning(f"Validation hard-fail: {validation.errors}")
                feedback = validation.feedback
                if attempt == MAX_RETRIES:
                    logger.error(f"Max retries reached. Errors: {validation.errors}")
                    return ProcessExpenseResult(
                        success=False,
                        errors=validation.errors,
                        message="❌ Не вдалось обробити після 3 спроб. Спробуйте ще раз або надайте більше деталей.",
                    )

        except Exception as e:
            logger.exception(f"Exception on attempt {attempt}: {e}")
            if attempt == MAX_RETRIES:
                logger.error(f"Max retries reached with exception: {e}")
                return ProcessExpenseResult(
                    success=False,
                    errors=[str(e)],
                    message=f"❌ Помилка обробки: {str(e)}",
                )
            feedback = f"Помилка обробки: {str(e)}"

    logger.error("Reached end of process_expense without returning")
    return ProcessExpenseResult(
        success=False,
        errors=["Unknown error"],
        message="❌ Невідома помилка",
    )
