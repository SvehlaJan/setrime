"""Tests for bot.models — data structures and sheet row generation."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from bot.models import (
    COL_CATEGORY,
    COL_DATE,
    COL_DESCRIPTION,
    COL_TOTAL_CZK,
    CURRENCY_COLUMNS,
    TOTAL_CZK_COL,
    Expense,
    ParsedExpense,
    PendingExpense,
)


# ── ParsedExpense ────────────────────────────────────────────────────

class TestParsedExpense:
    def test_all_none(self) -> None:
        p = ParsedExpense()
        assert p.date is None
        assert p.amount is None
        assert p.currency is None
        assert p.category is None
        assert p.description is None

    def test_full(self) -> None:
        p = ParsedExpense(
            date=date(2026, 2, 8),
            amount=450.0,
            currency="CZK",
            category="Potraviny",
            description="Albert",
        )
        assert p.date == date(2026, 2, 8)
        assert p.amount == 450.0
        assert p.currency == "CZK"

    def test_invalid_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ParsedExpense(currency="USD")  # type: ignore[arg-type]


# ── Expense ──────────────────────────────────────────────────────────

class TestExpense:
    def test_tab_name_format(self) -> None:
        """Tab name should be MM/YYYY format."""
        e = Expense(
            date=date(2026, 2, 1),
            amount=100,
            currency="CZK",
            category="Test",
            description="Test",
        )
        assert e.tab_name() == "02/2026"

    def test_tab_name_various_months(self) -> None:
        for month, expected in [
            (1, "01/2026"),
            (3, "03/2026"),
            (12, "12/2025"),
        ]:
            year = 2026 if month != 12 else 2025
            e = Expense(
                date=date(year, month, 15),
                amount=1,
                currency="CZK",
                category="X",
                description="X",
            )
            assert e.tab_name() == expected

    def test_date_format_no_leading_zeros(self) -> None:
        """Date in sheet row should be '1.2.2026' style (no leading zeros)."""
        e = Expense(
            date=date(2026, 2, 1),
            amount=100,
            currency="CZK",
            category="X",
            description="X",
        )
        row = e.sheet_row()
        assert row[1] == "1.2.2026"  # Column B = Date

    def test_date_format_double_digits(self) -> None:
        e = Expense(
            date=date(2026, 12, 25),
            amount=100,
            currency="CZK",
            category="X",
            description="X",
        )
        row = e.sheet_row()
        assert row[1] == "25.12.2026"  # Column B = Date

    def test_row_length_is_7(self) -> None:
        """Row should have 7 values (columns A through G)."""
        e = Expense(
            date=date(2026, 2, 1),
            amount=658,
            currency="CZK",
            category="Potraviny",
            description="Albert",
        )
        row = e.sheet_row()
        assert len(row) == 7

    def test_column_a_is_empty(self) -> None:
        """Column A (index 0) should always be None (empty — table starts at B)."""
        e = Expense(
            date=date(2026, 2, 1),
            amount=100,
            currency="CZK",
            category="X",
            description="X",
        )
        row = e.sheet_row()
        assert row[0] is None

    def test_czk_in_correct_column(self) -> None:
        """CZK amount should be at index 5 (column F)."""
        e = Expense(
            date=date(2026, 2, 1),
            amount=658,
            currency="CZK",
            category="Potraviny",
            description="Apalucha potraviny",
        )
        row = e.sheet_row()
        assert row[4] is None  # PLN empty
        assert row[5] == 658.0  # CZK filled
        assert row[6] is None  # EUR empty

    def test_pln_in_correct_column(self) -> None:
        """PLN amount should be at index 4 (column E)."""
        e = Expense(
            date=date(2026, 2, 2),
            amount=11.7,
            currency="PLN",
            category="Potraviny",
            description="Albert",
        )
        row = e.sheet_row()
        assert row[4] == 11.7  # PLN filled
        assert row[5] is None  # CZK empty
        assert row[6] is None  # EUR empty

    def test_eur_in_correct_column(self) -> None:
        """EUR amount should be at index 6 (column G)."""
        e = Expense(
            date=date(2026, 2, 3),
            amount=118,
            currency="EUR",
            category="Reštika",
            description="Kafe",
        )
        row = e.sheet_row()
        assert row[4] is None  # PLN empty
        assert row[5] is None  # CZK empty
        assert row[6] == 118.0  # EUR filled

    def test_category_at_index_2(self) -> None:
        """Category should be at index 2 (column C)."""
        e = Expense(
            date=date(2026, 2, 1),
            amount=100,
            currency="CZK",
            category="Potraviny",
            description="Test",
        )
        row = e.sheet_row()
        assert row[2] == "Potraviny"

    def test_description_at_index_3(self) -> None:
        """Description should be at index 3 (column D)."""
        e = Expense(
            date=date(2026, 2, 1),
            amount=100,
            currency="CZK",
            category="X",
            description="Apalucha potraviny",
        )
        row = e.sheet_row()
        assert row[3] == "Apalucha potraviny"

    def test_amount_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            Expense(
                date=date(2026, 2, 1),
                amount=0,
                currency="CZK",
                category="X",
                description="X",
            )

    def test_amount_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Expense(
                date=date(2026, 2, 1),
                amount=-10,
                currency="CZK",
                category="X",
                description="X",
            )

    def test_matches_screenshot_row_2(self) -> None:
        """Verify output matches row 2 from the screenshot:
        | 1.2.2026 | Potraviny | Apalucha potraviny | | 658 | | 658
        (column A is empty, data starts at B)
        """
        e = Expense(
            date=date(2026, 2, 1),
            amount=658,
            currency="CZK",
            category="Potraviny",
            description="Apalucha potraviny",
        )
        row = e.sheet_row()
        assert row == [
            None,             # A: empty (table starts at B)
            "1.2.2026",       # B: Dátum
            "Potraviny",      # C: Kategória
            "Apalucha potraviny",  # D: Popis
            None,             # E: PLN
            658.0,            # F: CZK
            None,             # G: EUR
        ]
        assert e.tab_name() == "02/2026"

    def test_matches_screenshot_row_20_pln(self) -> None:
        """Row 20: | 2.2.2026 | Potraviny | Albert | 11.7 | | | 283.36815"""
        e = Expense(
            date=date(2026, 2, 2),
            amount=11.7,
            currency="PLN",
            category="Potraviny",
            description="Albert",
        )
        row = e.sheet_row()
        assert row == [
            None, "2.2.2026", "Potraviny", "Albert",
            11.7, None, None,
        ]


# ── Column constants ─────────────────────────────────────────────────

class TestColumnConstants:
    def test_currency_columns(self) -> None:
        assert CURRENCY_COLUMNS == {"PLN": 4, "CZK": 5, "EUR": 6}

    def test_col_indices(self) -> None:
        assert COL_DATE == 1       # B
        assert COL_CATEGORY == 2   # C
        assert COL_DESCRIPTION == 3  # D
        assert COL_TOTAL_CZK == 7  # H

    def test_total_czk_letter(self) -> None:
        assert TOTAL_CZK_COL == "H"


# ── PendingExpense ───────────────────────────────────────────────────

class TestPendingExpense:
    def test_created_at_is_recent(self) -> None:
        import time
        before = time.time()
        pe = PendingExpense(
            user_id=1, chat_id=2, parsed=ParsedExpense()
        )
        after = time.time()
        assert before <= pe.created_at <= after

    def test_not_expired_when_fresh(self) -> None:
        pe = PendingExpense(
            user_id=1, chat_id=2, parsed=ParsedExpense()
        )
        assert not pe.is_expired()

    def test_expired_when_old(self) -> None:
        import time
        pe = PendingExpense(
            user_id=1, chat_id=2, parsed=ParsedExpense()
        )
        pe.created_at = time.time() - 7200  # 2 hours ago
        assert pe.is_expired()

    def test_poll_options_stored(self) -> None:
        pe = PendingExpense(
            user_id=1,
            chat_id=2,
            parsed=ParsedExpense(),
            poll_options=["A", "B", "C"],
        )
        assert pe.poll_options == ["A", "B", "C"]
