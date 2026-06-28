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

RULES:
1. If no time specified, assume NOW (current moment).
2. If no date specified, assume TODAY.
3. Always return ISO 8601 datetime.
4. Amount must be > 0 or null if unknown.
5. Category must be one of the 8 above or null if too vague.
6. Confidence: 0.9–1.0 for clear input, 0.7–0.8 for slightly ambiguous, 0.3–0.6 for vague, <0.3 for too vague.
7. Do NOT add extra fields or omit required fields.
8. Do NOT hallucinate categories outside the vocabulary.
9. Preserve original text in description unless normalizing for clarity."""


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
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Parse this expense: {user_input}",
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
