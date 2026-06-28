"""Unit tests for datetime inference in extract_expense."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.agent import extract_expense
from src.models import Expense, ExpenseList


def _make_expense_list(dt_str: str) -> ExpenseList:
    """Build an ExpenseList with a single expense using the given datetime string."""
    return ExpenseList(
        expenses=[
            Expense(
                amount=50,
                currency="UAH",
                category="Кафе/Ресторани",
                description="купив каву",
                datetime=dt_str,
                confidence=0.95,
            )
        ]
    )


FIXED_NOW = datetime(2026, 6, 28, 15, 0, 0)


@patch("src.agent.datetime")
@patch("src.agent.chain")
def test_no_date_no_time_uses_receipt_timestamp(mock_chain, mock_dt):
    """No date/time in input → LLM receives receipt timestamp and uses it."""
    mock_dt.now.return_value = FIXED_NOW
    expected_dt = FIXED_NOW.isoformat()
    mock_chain.invoke.return_value = _make_expense_list(expected_dt)

    expenses = extract_expense("купив каву за 50")

    # Verify the receipt timestamp was injected into the invoke call
    call_args = mock_chain.invoke.call_args
    invoke_dict = call_args[0][0]
    assert invoke_dict["received_at"] == FIXED_NOW.isoformat()

    assert expenses[0].datetime == expected_dt


@patch("src.agent.datetime")
@patch("src.agent.chain")
def test_relative_time_uses_receipt_timestamp_minus_offset(mock_chain, mock_dt):
    """Relative time "годину назад" → LLM computes receipt_time - 1 hour."""
    mock_dt.now.return_value = FIXED_NOW
    expected_dt = (FIXED_NOW - timedelta(hours=1)).isoformat()
    mock_chain.invoke.return_value = _make_expense_list(expected_dt)

    expenses = extract_expense("годину назад купив каву за 50")

    # Receipt timestamp injected so LLM can subtract
    call_args = mock_chain.invoke.call_args
    invoke_dict = call_args[0][0]
    assert invoke_dict["received_at"] == FIXED_NOW.isoformat()

    assert expenses[0].datetime == expected_dt


@patch("src.agent.datetime")
@patch("src.agent.chain")
def test_date_only_uses_midnight(mock_chain, mock_dt):
    """Date-only input "вчора" → midnight of yesterday."""
    mock_dt.now.return_value = FIXED_NOW
    yesterday_midnight = "2026-06-27T00:00:00"
    mock_chain.invoke.return_value = _make_expense_list(yesterday_midnight)

    expenses = extract_expense("50 на продукти вчора")

    assert expenses[0].datetime == yesterday_midnight


@patch("src.agent.datetime")
@patch("src.agent.chain")
def test_explicit_time_preserved(mock_chain, mock_dt):
    """Explicit time "о 18:30" is preserved unchanged (not replaced by receipt timestamp)."""
    mock_dt.now.return_value = FIXED_NOW
    # Use a past date to avoid the Pydantic "not in the future" guard
    explicit_dt = "2026-06-27T18:30:00"
    mock_chain.invoke.return_value = _make_expense_list(explicit_dt)

    expenses = extract_expense("вчора в ресторані о 18:30 витратив 350")

    # The user-specified time (18:30) must be preserved, not replaced by receipt timestamp (15:00)
    assert expenses[0].datetime == explicit_dt
    assert "T18:30:00" in expenses[0].datetime
