from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timedelta
from typing import Optional


class Expense(BaseModel):
    """Structured expense data extracted by the parser agent."""

    amount: Optional[float] = Field(None, description="Expense amount in UAH. Must be > 0.")
    currency: str = Field("UAH", description="Currency code (hardcoded to UAH).")
    category: Optional[str] = Field(None, description="One of 8 canonical categories.")
    description: str = Field(..., description="Original user text or normalized summary.")
    datetime: str = Field(..., description="ISO 8601 timestamp.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0–1.0).")

    @field_validator("amount")
    def validate_amount(cls, v):
        if v is not None and v <= 0:
            raise ValueError("amount must be > 0")
        return v

    @field_validator("datetime")
    def validate_datetime(cls, v):
        try:
            parsed = datetime.fromisoformat(v)
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            # Use local time + 60s buffer to tolerate LLM processing latency
            now = datetime.now() + timedelta(seconds=60)
            if parsed > now:
                raise ValueError("datetime cannot be in the future")
            return v
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 datetime: {e}")

    @field_validator("confidence")
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v

    @field_validator("description")
    def validate_description(cls, v):
        if not v or not v.strip():
            raise ValueError("description must be non-empty")
        return v.strip()


class ValidationResult(BaseModel):
    """Result of validating an expense."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    feedback: Optional[str] = None


class ProcessExpenseResult(BaseModel):
    """Result of processing an expense (parse + validate + store)."""

    success: bool
    expenses: list[Expense] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    message: str
    validation_errors: Optional[str] = None

    @property
    def expense(self) -> Optional[Expense]:
        """Backward-compat: return the first expense or None."""
        return self.expenses[0] if self.expenses else None
