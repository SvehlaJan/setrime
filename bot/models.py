import time
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Literal, Optional

from pydantic import BaseModel, Field


Currency = Literal["CZK", "PLN", "EUR"]

# Actual sheet layout (0-indexed positions within the row we write):
#   A: Dátum  |  B: (empty)  |  C: Kategória  |  D: Popis
#   E: # PLN  |  F: # CZK   |  G: # EUR
#   H: # Total CZK  (formula — never written by bot)
#
# The bot writes columns A through G (indices 0–6), leaving H for the formula.
CURRENCY_COLUMNS: dict[str, int] = {
    "PLN": 4,  # Column E (0-indexed within row: 4)
    "CZK": 5,  # Column F
    "EUR": 6,  # Column G
}

# Column indices when reading full rows from gspread (0-indexed)
COL_DATE = 0       # A
COL_CATEGORY = 2   # C
COL_DESCRIPTION = 3  # D
COL_TOTAL_CZK = 7  # H

# Google Sheets column letter for the Total CZK formula
TOTAL_CZK_COL = "H"


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
        """Return the monthly tab name.

        Uses abbreviated English month name + year, matching the actual
        Google Sheet (e.g., 'Feb 2026', 'Mar 2026').
        """
        return self.date.strftime("%b %Y")

    def sheet_row(self) -> list[str | float | None]:
        """Return a row list matching the sheet columns A through G:

        A: Dátum | B: (empty) | C: Kategória | D: Popis |
        E: # PLN | F: # CZK  | G: # EUR

        Column H (Total CZK) is a formula and is NOT included.
        """
        row: list[str | float | None] = [
            # Date without leading zeros: "1.2.2026"
            f"{self.date.day}.{self.date.month}.{self.date.year}",
            None,  # Column B — empty spacer
            self.category,
            self.description,
            None,  # E: Amount PLN
            None,  # F: Amount CZK
            None,  # G: Amount EUR
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
    # Track which poll_options were used (subset of categories for >10 case)
    poll_options: list[str] | None = None
    created_at: float = field(default_factory=time.time)

    def is_expired(self, timeout_seconds: float = 3600.0) -> bool:
        """Check if this pending expense has been waiting too long."""
        return (time.time() - self.created_at) > timeout_seconds
