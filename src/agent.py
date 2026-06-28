"""Parser agent: LLM-powered expense extraction from free-form Ukrainian text."""

import json
import logging
from datetime import datetime
from typing import Optional

from openai import OpenAI

from .config import OPENAI_API_KEY, LLM_MODEL, VALID_CATEGORIES
from .models import Expense

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

# System prompt for the LLM (refers to AGENTS.md content)
SYSTEM_PROMPT = """You are an expense parser agent. Your task is to extract structured expense data from free-form Ukrainian text.

You MUST return valid JSON matching this schema:
{
  "amount": number or null,
  "currency": "UAH",
  "category": string or null,
  "description": string,
  "datetime": string (ISO 8601),
  "confidence": number (0.0–1.0)
}

CATEGORY VOCABULARY (must be one of these 8):
- Продукти (groceries, food shopping)
- Транспорт (gas, transit, taxi)
- Кафе/Ресторани (dining out)
- Комуналки (utilities, rent)
- Розваги (entertainment, hobbies)
- Здоров'я (healthcare, pharmacy)
- Покупки (clothing, household goods)
- Інше (catch-all for unclear)

DATETIME INFERENCE RULES (apply in order):
1. Explicit time given (e.g., "о 18:30", "в 14:00") → use it. If no date given, use today's date from "Message received at".
2. Relative time given (e.g., "годину назад", "2 години тому", "хвилину назад") → subtract the offset from the "Message received at" timestamp.
3. Date only, no time (e.g., "вчора", "2026-06-25", "у п'ятницю") → use midnight (00:00:00) of that date.
4. No date and no time at all → copy the "Message received at" timestamp EXACTLY, character for character.

CRITICAL: NEVER use a date from your training data. The ONLY valid source of "today's date" is the "Message received at" field. If you are unsure, use "Message received at" verbatim.

OTHER RULES:
5. Always return ISO 8601 datetime without timezone suffix (e.g., "2026-06-28T14:30:00").
6. Amount must be > 0 or null if unknown.
7. Category must be one of the 8 above or null if too vague.
8. Confidence: 0.9–1.0 for clear input, 0.7–0.8 for slightly ambiguous, 0.3–0.6 for vague, <0.3 for too vague.
9. Do NOT add extra fields or omit required fields.
10. Do NOT hallucinate categories outside the vocabulary.
11. Preserve original text in description unless normalizing for clarity."""


def extract_expense(user_input: str, feedback: Optional[str] = None) -> Expense:
    """
    Extract structured expense from user input using LLM.

    Args:
        user_input: Free-form Ukrainian text describing an expense.
        feedback: Optional validation feedback from a prior failed attempt.

    Returns:
        Expense object (may have null fields if too vague).

    Raises:
        ValueError: If LLM response is malformed or cannot parse JSON.
    """
    logger.info(f"extract_expense called with input: {user_input}, feedback: {feedback}")
    now = datetime.now()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Message received at: {now.isoformat()}\nParse this expense: {user_input}",
        },
    ]

    if feedback:
        messages.append(
            {
                "role": "assistant",
                "content": "I attempted to parse the expense but it failed validation.",
            }
        )
        messages.append(
            {
                "role": "user",
                "content": f"Validation feedback: {feedback}\n\nPlease retry and correct the issue. Original input: {user_input}",
            }
        )

    logger.debug(f"Calling LLM with {len(messages)} messages")
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.3,  # Low temperature for consistent parsing
    )

    content = response.choices[0].message.content
    logger.debug(f"LLM response: {content}")
    if not content:
        raise ValueError("LLM returned empty response")

    try:
        data = json.loads(content)
        logger.info(f"Parsed JSON: {data}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}, content: {content}")
        raise ValueError(f"LLM response is not valid JSON: {e}")

    logger.info(f"Creating Expense object from data: {data}")
    expense = Expense(**data)
    logger.info(f"Expense created successfully: {expense}")
    return expense
