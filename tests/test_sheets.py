"""Tests for bot.services.sheets — formula adjustment and summary parsing."""
from __future__ import annotations

import pytest

from bot.services.sheets import SheetsService


class TestAdjustFormulaRow:
    def test_simple_replacement(self) -> None:
        formula = "=E5*$K$2+F5+G5*$L$2"
        result = SheetsService._adjust_formula_row(formula, 5, 6)
        assert result == "=E6*$K$2+F6+G6*$L$2"

    def test_no_change_when_no_match(self) -> None:
        formula = "=E3+F3"
        result = SheetsService._adjust_formula_row(formula, 5, 6)
        assert result == "=E3+F3"

    def test_double_digit_row(self) -> None:
        formula = "=E15*$K$2+F15+G15*$L$2"
        result = SheetsService._adjust_formula_row(formula, 15, 16)
        assert result == "=E16*$K$2+F16+G16*$L$2"


class TestSummaryParsing:
    """Test the summary aggregation logic with mock row data.

    We simulate what get_summary does without needing a real Sheet connection.
    """

    def _parse_summary(self, rows: list[list[str]]) -> dict[str, float]:
        """Reproduce the summary logic from SheetsService.get_summary."""
        from bot.models import COL_CATEGORY, COL_TOTAL_CZK

        summary: dict[str, float] = {}
        for row in rows:
            if len(row) <= COL_TOTAL_CZK:
                continue
            category = row[COL_CATEGORY].strip()
            total_str = row[COL_TOTAL_CZK].strip()
            if not category or not total_str:
                continue
            try:
                total = float(total_str.replace(",", ".").replace(" ", ""))
                summary[category] = summary.get(category, 0.0) + total
            except ValueError:
                continue
        return summary

    def test_basic_aggregation(self) -> None:
        rows = [
            # A       B     C            D        E     F     G     H
            ["1.2.2026", "", "Potraviny", "Albert", "", "658", "", "658"],
            ["1.2.2026", "", "Potraviny", "Lidl",   "", "365", "", "365"],
            ["1.2.2026", "", "Doprava",   "Uber",   "", "",    "12", "315"],
        ]
        result = self._parse_summary(rows)
        assert result["Potraviny"] == pytest.approx(1023.0)
        assert result["Doprava"] == pytest.approx(315.0)

    def test_comma_decimal_separator(self) -> None:
        rows = [
            ["1.2.2026", "", "Potraviny", "Test", "", "", "", "283,36815"],
        ]
        result = self._parse_summary(rows)
        assert result["Potraviny"] == pytest.approx(283.36815)

    def test_empty_total_skipped(self) -> None:
        rows = [
            ["1.2.2026", "", "Potraviny", "Test", "", "100", "", ""],
        ]
        result = self._parse_summary(rows)
        assert result == {}

    def test_short_row_skipped(self) -> None:
        rows = [
            ["1.2.2026", "", "Potraviny"],  # too short
        ]
        result = self._parse_summary(rows)
        assert result == {}
