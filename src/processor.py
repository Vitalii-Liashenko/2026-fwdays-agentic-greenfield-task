"""Expense processor: orchestrates agent → validator → storage."""

import logging
from typing import Optional

from .agent import extract_expense
from .validator import validate_expense
from .models import Expense, ProcessExpenseResult
from .config import MAX_RETRIES

logger = logging.getLogger(__name__)


def process_expense(raw_text: str) -> ProcessExpenseResult:
    """
    Process a raw user input: parse with agent, validate with checker, retry on hard-fail.

    Orchestrates:
    1. Agent extracts expense from raw_text
    2. Validator checks the extraction
    3. If hard-fail, agent retries (max 3 times) with feedback
    4. If soft-fail, expense is marked but stored
    5. Returns result for storage/reply

    Args:
        raw_text: User input text to process.

    Returns:
        ProcessExpenseResult with success flag, expense object, and message.
    """
    logger.info(f"Starting process_expense for input: {raw_text}")
    expense: Optional[Expense] = None
    feedback: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Attempt {attempt}/{MAX_RETRIES}: extracting expense...")
            # Extract expense
            expense = extract_expense(raw_text, feedback=feedback)
            logger.info(f"Expense extracted: {expense}")

            logger.info("Validating expense...")
            # Validate
            validation = validate_expense(expense)
            logger.info(f"Validation result: valid={validation.valid}, errors={validation.errors}")

            if validation.valid:
                # Hard-fail averted or soft-fail (both acceptable)
                message = "✅ Витрата записана"
                if validation.errors:
                    # Soft-fail
                    message += " (низька впевненість)"
                    logger.info(f"Soft-fail with errors: {validation.errors}")
                    return ProcessExpenseResult(
                        success=True,
                        expense=expense,
                        errors=validation.errors,
                        message=message,
                        validation_errors="; ".join(validation.errors),
                    )
                else:
                    logger.info("Validation passed")
                    return ProcessExpenseResult(
                        success=True,
                        expense=expense,
                        message=message,
                    )
            else:
                # Hard-fail: retry
                logger.warning(f"Validation hard-fail: {validation.errors}")
                feedback = validation.feedback
                if attempt == MAX_RETRIES:
                    # Out of retries
                    logger.error(f"Max retries reached. Errors: {validation.errors}")
                    return ProcessExpenseResult(
                        success=False,
                        expense=None,
                        errors=validation.errors,
                        message="❌ Не вдалось обробити після 3 спроб. Спробуйте ще раз або надайте більше деталей.",
                    )
                # else: loop and retry

        except Exception as e:
            logger.exception(f"Exception on attempt {attempt}: {e}")
            # Parse error or other exception
            if attempt == MAX_RETRIES:
                logger.error(f"Max retries reached with exception: {e}")
                return ProcessExpenseResult(
                    success=False,
                    expense=None,
                    errors=[str(e)],
                    message=f"❌ Помилка обробки: {str(e)}",
                )
            feedback = f"Помилка обробки: {str(e)}"

    # Should not reach here
    logger.error("Reached end of process_expense without returning")
    return ProcessExpenseResult(
        success=False,
        expense=None,
        errors=["Unknown error"],
        message="❌ Невідома помилка",
    )
