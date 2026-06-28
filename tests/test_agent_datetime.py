"""Unit tests for datetime inference in extract_expense."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.agent import extract_expense


def _make_llm_response(dt_str: str) -> MagicMock:
    """Build a fake OpenAI response returning the given datetime string."""
    payload = {
        "amount": 50,
        "currency": "UAH",
        "category": "Кафе/Ресторани",
        "description": "купив каву",
        "datetime": dt_str,
        "confidence": 0.95,
    }
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


FIXED_NOW = datetime(2026, 6, 28, 15, 0, 0)


@patch("src.agent.datetime")
@patch("src.agent.client")
def test_no_date_no_time_uses_receipt_timestamp(mock_client, mock_dt):
    """No date/time in input → LLM receives receipt timestamp and uses it."""
    mock_dt.now.return_value = FIXED_NOW
    expected_dt = FIXED_NOW.isoformat()
    mock_client.chat.completions.create.return_value = _make_llm_response(expected_dt)

    expense = extract_expense("купив каву за 50")

    # Verify the receipt timestamp was injected into the user message
    call_args = mock_client.chat.completions.create.call_args
    user_message = call_args.kwargs["messages"][1]["content"]
    assert f"Message received at: {FIXED_NOW.isoformat()}" in user_message

    assert expense.datetime == expected_dt


@patch("src.agent.datetime")
@patch("src.agent.client")
def test_relative_time_uses_receipt_timestamp_minus_offset(mock_client, mock_dt):
    """Relative time "годину назад" → LLM computes receipt_time - 1 hour."""
    mock_dt.now.return_value = FIXED_NOW
    expected_dt = (FIXED_NOW - timedelta(hours=1)).isoformat()
    mock_client.chat.completions.create.return_value = _make_llm_response(expected_dt)

    expense = extract_expense("годину назад купив каву за 50")

    # Receipt timestamp injected so LLM can subtract
    call_args = mock_client.chat.completions.create.call_args
    user_message = call_args.kwargs["messages"][1]["content"]
    assert f"Message received at: {FIXED_NOW.isoformat()}" in user_message

    assert expense.datetime == expected_dt


@patch("src.agent.datetime")
@patch("src.agent.client")
def test_date_only_uses_midnight(mock_client, mock_dt):
    """Date-only input "вчора" → midnight of yesterday."""
    mock_dt.now.return_value = FIXED_NOW
    yesterday_midnight = "2026-06-27T00:00:00"
    mock_client.chat.completions.create.return_value = _make_llm_response(yesterday_midnight)

    expense = extract_expense("50 на продукти вчора")

    assert expense.datetime == yesterday_midnight


@patch("src.agent.datetime")
@patch("src.agent.client")
def test_explicit_time_preserved(mock_client, mock_dt):
    """Explicit time "о 18:30" is preserved unchanged (not replaced by receipt timestamp)."""
    mock_dt.now.return_value = FIXED_NOW
    # Use a past date to avoid the Pydantic "not in the future" guard
    explicit_dt = "2026-06-27T18:30:00"
    mock_client.chat.completions.create.return_value = _make_llm_response(explicit_dt)

    expense = extract_expense("вчора в ресторані о 18:30 витратив 350")

    # The user-specified time (18:30) must be preserved, not replaced by receipt timestamp (15:00)
    assert expense.datetime == explicit_dt
    assert "T18:30:00" in expense.datetime
