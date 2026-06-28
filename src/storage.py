"""Storage: PostgreSQL interaction for expense persistence."""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional, List

from .config import DATABASE_URL
from .models import Expense


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


def get_connection():
    """Create a PostgreSQL connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        raise StorageError(f"Failed to connect to database: {e}")


def store_expense(expense: Expense, validation_errors: Optional[str] = None) -> int:
    """
    Store an expense in PostgreSQL.

    Args:
        expense: Expense object to store.
        validation_errors: Optional error message if soft-fail.

    Returns:
        ID of the stored expense.

    Raises:
        StorageError: If insert fails.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO expenses (amount, currency, category, description, datetime, confidence, validation_errors)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    expense.amount,
                    expense.currency,
                    expense.category,
                    expense.description,
                    expense.datetime,
                    expense.confidence,
                    validation_errors,
                ),
            )
            expense_id = cur.fetchone()[0]
            conn.commit()
            return expense_id
    except psycopg2.Error as e:
        conn.rollback()
        raise StorageError(f"Failed to store expense: {e}")
    finally:
        conn.close()


def get_all_expenses() -> List[dict]:
    """
    Retrieve all expenses, ordered by datetime (newest first).

    Returns:
        List of expense dictionaries.

    Raises:
        StorageError: If query fails.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, amount, currency, category, description, datetime, confidence, validation_errors, created_at
                FROM expenses
                ORDER BY datetime DESC;
                """
            )
            return cur.fetchall()
    except psycopg2.Error as e:
        raise StorageError(f"Failed to retrieve expenses: {e}")
    finally:
        conn.close()


def get_expenses_by_category(category: str) -> List[dict]:
    """
    Retrieve expenses filtered by category.

    Args:
        category: Category name to filter by.

    Returns:
        List of expense dictionaries.

    Raises:
        StorageError: If query fails.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, amount, currency, category, description, datetime, confidence, validation_errors, created_at
                FROM expenses
                WHERE category = %s
                ORDER BY datetime DESC;
                """,
                (category,),
            )
            return cur.fetchall()
    except psycopg2.Error as e:
        raise StorageError(f"Failed to retrieve expenses by category: {e}")
    finally:
        conn.close()


def get_total_expense() -> float:
    """
    Get total expense sum.

    Returns:
        Total amount in UAH.

    Raises:
        StorageError: If query fails.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT SUM(amount) FROM expenses WHERE validation_errors IS NULL;")
            result = cur.fetchone()[0]
            return result or 0.0
    except psycopg2.Error as e:
        raise StorageError(f"Failed to calculate total: {e}")
    finally:
        conn.close()


def log_validation_failure(user_input: str, error_message: str, attempt_number: int):
    """
    Log a validation failure for analysis.

    Args:
        user_input: Original user input.
        error_message: Error message from validator.
        attempt_number: Attempt number (1-3).

    Raises:
        StorageError: If insert fails.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO validation_logs (user_input, error_message, attempt_number)
                VALUES (%s, %s, %s);
                """,
                (user_input, error_message, attempt_number),
            )
            conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        raise StorageError(f"Failed to log validation failure: {e}")
    finally:
        conn.close()
