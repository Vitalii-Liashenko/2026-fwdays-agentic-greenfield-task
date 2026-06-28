"""Validator (checker): Rule-based validation of parsed expenses."""

import logging
from datetime import datetime, timedelta

from .config import VALID_CATEGORIES, CONFIDENCE_THRESHOLD
from .models import Expense, ValidationResult

logger = logging.getLogger(__name__)


def validate_expense(expense: Expense) -> ValidationResult:
    """
    Validate a parsed expense against hard and soft rules.

    Hard-fail rules (expense rejected, agent retries):
    1. amount > 0
    2. amount is a valid number
    3. category ∈ enum
    4. datetime is valid ISO 8601, not in future
    5. confidence ∈ [0.0, 1.0]
    6. description is non-empty

    Soft-fail rules (expense stored but flagged):
    7. confidence < 0.7 (flagged for review)

    Args:
        expense: Expense object to validate.

    Returns:
        ValidationResult with valid flag, errors list, and feedback for retry.
    """
    logger.info(f"Validating expense: {expense}")
    errors = []
    soft_fail = False

    # Rule 1: amount > 0
    logger.debug(f"Rule 1: Checking amount={expense.amount}")
    if expense.amount is None:
        errors.append("amount is null")
    elif expense.amount <= 0:
        errors.append(f"amount must be > 0, got {expense.amount}")

    # Rule 2: amount is a valid number
    try:
        float(expense.amount) if expense.amount is not None else None
    except (TypeError, ValueError):
        errors.append(f"amount is not a valid number: {expense.amount}")

    # Rule 3: category ∈ enum
    logger.debug(f"Rule 3: Checking category={expense.category}")
    if expense.category is None:
        errors.append("category is null")
    elif expense.category not in VALID_CATEGORIES:
        errors.append(
            f"category '{expense.category}' is not in vocabulary. "
            f"Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
        )

    # Rule 4: datetime valid and not in future
    logger.debug(f"Rule 4: Checking datetime={expense.datetime}")
    try:
        parsed_dt = datetime.fromisoformat(expense.datetime)
        if parsed_dt.tzinfo is not None:
            parsed_dt = parsed_dt.replace(tzinfo=None)
        # Use local time + 60s buffer to tolerate LLM processing latency
        now = datetime.now() + timedelta(seconds=60)
        logger.debug(f"Parsed datetime: {parsed_dt}, now: {now}")
        if parsed_dt > now:
            errors.append(f"datetime cannot be in the future: {expense.datetime}")
    except ValueError as e:
        logger.error(f"ValueError parsing datetime: {e}")
        errors.append(f"datetime is not valid ISO 8601: {expense.datetime}")

    # Rule 5: confidence in [0.0, 1.0]
    logger.debug(f"Rule 5: Checking confidence={expense.confidence}")
    if not (0.0 <= expense.confidence <= 1.0):
        errors.append(f"confidence must be in [0.0, 1.0], got {expense.confidence}")

    # Rule 6: description non-empty
    logger.debug(f"Rule 6: Checking description='{expense.description}'")
    if not expense.description or not expense.description.strip():
        errors.append("description is empty")

    # Rule 7: confidence < 0.7 (soft-fail, not a hard error)
    if expense.confidence < CONFIDENCE_THRESHOLD:
        soft_fail = True
        logger.debug(f"Soft-fail: confidence {expense.confidence} < {CONFIDENCE_THRESHOLD}")

    # Determine result
    if errors:
        logger.warning(f"Validation hard-fail: {errors}")
        # Hard-fail: return validation errors
        return ValidationResult(
            valid=False,
            errors=errors,
            feedback=f"Validation failed: {'; '.join(errors)}. Please retry.",
        )
    elif soft_fail:
        logger.info("Validation soft-fail (low confidence)")
        # Soft-fail: still valid but flagged
        return ValidationResult(
            valid=True,
            errors=["confidence < 0.7 (flagged for review)"],
            feedback=None,
        )
    else:
        logger.info("Validation passed")
        # Success
        return ValidationResult(valid=True)
