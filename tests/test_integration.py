"""Integration tests: end-to-end expense processing (parse → validate → store)."""

import pytest

from src.processor import process_expense


def test_integration_happy_path():
    """Happy path: valid single-expense input → parsed → validated → ready to store."""
    result = process_expense("купив каву за 50")

    assert result.success is True
    assert len(result.expenses) == 1
    assert result.expense is not None  # backward-compat property
    assert result.expense.amount == 50
    assert result.expense.category == "Кафе/Ресторани"
    assert result.message.startswith("✅")


def test_integration_hard_fail_vague_input():
    """Hard-fail: vague input with no amount → LLM returns null amount →
    Expense construction rejects it (hard rule), retries exhaust, failure returned.

    Under the consolidated-validation model, `amount=None` is a hard-fail enforced
    at Expense construction time (see expense-model-validation capability). Vague
    input that yields a null amount therefore cannot be soft-stored; it retries
    and fails rather than recording an invalid expense.
    """
    result = process_expense("витрати")  # Very vague, no amount

    assert result.success is False
    assert result.expenses == []


def test_integration_hard_fail_retry():
    """Hard-fail path: agent retries on validation error."""
    result = process_expense("на бенз 200")

    assert result.success is True
    assert len(result.expenses) >= 1


def test_integration_error_message():
    """Error message is clear when processing fails."""
    result = process_expense("купив товары за 75")

    assert result.message is not None
    assert len(result.message) > 0


def test_integration_multi_expense_split():
    """Multi-expense input creates multiple expense objects."""
    result = process_expense("купив каву за 50 і хліб за 30")

    assert result.success is True
    assert len(result.expenses) == 2
    amounts = sorted(e.amount for e in result.expenses)
    assert amounts == [30, 50]


def test_integration_combined_total_no_split():
    """Combined-total input with one amount produces a single expense."""
    result = process_expense("купив пиво і воду за 30")

    assert result.success is True
    assert len(result.expenses) == 1
    assert result.expenses[0].amount == 30
