import time
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Literal, Optional

from pydantic import BaseModel, Field


Currency = Literal["CZK", "PLN", "EUR"]

CURRENCY_COLUMNS: dict[str, int] = {
    "PLN": 3,  # Column D (0-indexed: 3)
    "CZK": 4,  # Column E
    "EUR": 5,  # Column F
}


class ParsedExpense(BaseModel):
    """Structured output from the LLM parser.

    Fields may be None if the LLM could not determine them, which
    triggers follow-up questions to the user.
    """

    date: Optional[Date] = None
    amount: Optional[float] = None
    currency: Optional[Currency] = None
    category: Optional[str] = None
    description: Optional[str] = None


class Expense(BaseModel):
    """A fully validated expense ready to be written to Google Sheets.

    All fields are required (non-None).
    """

    date: Date
    amount: float = Field(gt=0)
    currency: Currency
    category: str
    description: str

    def tab_name(self) -> str:
        """Return the monthly tab name in MM/YYYY format."""
        return self.date.strftime("%m/%Y")

    def sheet_row(self) -> list[str | float | None]:
        """Return a row list matching the sheet columns:
        Date | Category | Description | Amount PLN | Amount CZK | Amount EUR
        (Total CZK is left out — it's a formula.)
        """
        row: list[str | float | None] = [
            self.date.strftime("%d.%m.%Y"),
            self.category,
            self.description,
            None,  # Amount PLN
            None,  # Amount CZK
            None,  # Amount EUR
        ]
        col_index = CURRENCY_COLUMNS[self.currency]
        row[col_index] = self.amount
        return row


@dataclass
class PendingExpense:
    """Tracks an expense that is mid-conversation (waiting for user
    to fill in missing fields via poll or text reply)."""

    user_id: int
    chat_id: int
    parsed: ParsedExpense
    poll_id: str | None = None
    message_id: int | None = None
    created_at: float = field(default_factory=time.time)

    def is_expired(self, timeout_seconds: float = 3600.0) -> bool:
        """Check if this pending expense has been waiting too long."""
        return (time.time() - self.created_at) > timeout_seconds
