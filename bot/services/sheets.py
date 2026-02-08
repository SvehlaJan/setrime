from __future__ import annotations

import logging
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import ValueInputOption, ValueRenderOption

from bot.models import (
    COL_CATEGORY,
    COL_DATE,
    COL_DESCRIPTION,
    COL_TOTAL_CZK,
    TOTAL_CZK_COL,
    Expense,
)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

# Category column in gspread 1-indexed notation
CATEGORY_COL_GSPREAD = 3  # Column C

# Data validation: 0-indexed column index for C
CATEGORY_COL_0IDX = 2


class SheetsService:
    """Handles all Google Sheets operations: reading categories, writing
    expense rows, and reading data for summary/undo commands."""

    def __init__(self, credentials_file: str, sheet_id: str) -> None:
        self._sheet_id = sheet_id
        creds: Credentials = Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            credentials_file, scopes=SCOPES
        )
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(sheet_id)
        logger.info("Connected to Google Sheet: %s", self._spreadsheet.title)

    def read_categories(self) -> list[str]:
        """Read categories from the data validation dropdown on the Category
        column (column C) of the first non-empty worksheet.

        Falls back to reading unique values from column C if data validation
        rules cannot be parsed.
        """
        try:
            return self._read_categories_from_validation()
        except Exception as exc:
            logger.warning(
                "Could not read data validation rules (%s), "
                "falling back to unique column values",
                exc,
            )
            return self._read_categories_from_column()

    def _read_categories_from_validation(self) -> list[str]:
        """Read data validation rules via the Sheets API."""
        response: dict[str, Any] = (
            self._client.http_client.request(
                "get",
                f"https://sheets.googleapis.com/v4/spreadsheets/{self._sheet_id}"
                f"?fields=sheets.data.rowData.values.dataValidation"
                f"&includeGridData=true",
            )
        )
        # Navigate to column C (index 2) data validation
        sheets_data = response.get("sheets", [])
        for sheet in sheets_data:
            rows = sheet.get("data", [{}])[0].get("rowData", [])
            for row in rows:
                values = row.get("values", [])
                if len(values) > CATEGORY_COL_0IDX:
                    dv = values[CATEGORY_COL_0IDX].get("dataValidation")
                    if dv and dv.get("condition", {}).get("type") == "ONE_OF_LIST":
                        categories = [
                            v.get("userEnteredValue", "")
                            for v in dv["condition"].get("values", [])
                            if v.get("userEnteredValue")
                        ]
                        if categories:
                            logger.info(
                                "Read %d categories from data validation on column C",
                                len(categories),
                            )
                            return categories

        raise ValueError("No data validation dropdown found on column C")

    def _read_categories_from_column(self) -> list[str]:
        """Fallback: read unique non-empty values from the Category column (C)
        across all worksheets."""
        categories: set[str] = set()
        for ws in self._spreadsheet.worksheets():
            try:
                col_values = ws.col_values(CATEGORY_COL_GSPREAD)
                for val in col_values[1:]:  # skip header
                    stripped = str(val).strip()
                    if stripped:
                        categories.add(stripped)
            except Exception:
                continue

        result = sorted(categories)
        logger.info(
            "Read %d categories from column C values (fallback)", len(result)
        )
        return result

    def get_worksheet(self, tab_name: str) -> gspread.Worksheet:
        """Get a worksheet by tab name (e.g., 'Feb 2026').

        Raises gspread.exceptions.WorksheetNotFound if it doesn't exist.
        """
        return self._spreadsheet.worksheet(tab_name)

    def append_expense(self, expense: Expense) -> int:
        """Append an expense row to the correct monthly tab.

        Returns the row number where the expense was written.
        """
        tab_name = expense.tab_name()
        ws = self.get_worksheet(tab_name)

        row_data = expense.sheet_row()
        # Convert None to empty string for gspread
        row_for_sheet: list[str | float] = [
            v if v is not None else "" for v in row_data
        ]

        # Find the first empty row (after header)
        all_values = ws.get_all_values()
        next_row = len(all_values) + 1

        # Write columns A through G (7 columns), leave H (Total CZK) untouched
        cell_range = f"A{next_row}:G{next_row}"
        ws.update(
            values=[row_for_sheet],
            range_name=cell_range,
            value_input_option=ValueInputOption.user_entered,
        )

        # Try to copy the Total CZK formula from the previous row
        self._copy_total_formula(ws, next_row)

        logger.info(
            "Expense written to sheet '%s' row %d: %s %.2f %s [%s] %s",
            tab_name,
            next_row,
            expense.date.isoformat(),
            expense.amount,
            expense.currency,
            expense.category,
            expense.description,
        )
        return next_row

    def _copy_total_formula(self, ws: gspread.Worksheet, target_row: int) -> None:
        """Copy the Total CZK formula from column H of the previous row."""
        if target_row < 3:
            # Row 2 is the first data row; no previous formula to copy
            return
        try:
            prev_cell = f"{TOTAL_CZK_COL}{target_row - 1}"
            prev_formula = ws.acell(
                prev_cell,
                value_render_option=ValueRenderOption.formula,
            ).value
            if prev_formula and isinstance(prev_formula, str) and prev_formula.startswith("="):
                # Adjust row references in the formula
                new_formula = self._adjust_formula_row(
                    prev_formula, target_row - 1, target_row
                )
                target_cell = f"{TOTAL_CZK_COL}{target_row}"
                ws.update_acell(target_cell, new_formula)
                logger.debug(
                    "Copied Total CZK formula to %s: %s", target_cell, new_formula
                )
        except Exception as exc:
            logger.warning("Could not copy Total CZK formula: %s", exc)

    @staticmethod
    def _adjust_formula_row(formula: str, old_row: int, new_row: int) -> str:
        """Adjust row numbers in relative cell references within a formula.

        Only replaces row numbers in relative references (e.g., E2, F2)
        while preserving absolute references (e.g., $K$2, $L$2) that
        typically point to fixed cells like exchange rates.

        A relative reference looks like: a letter (not preceded by $)
        followed by the row number (not followed by more digits).
        An absolute reference has $ before the row: $K$2.
        """
        import re

        # Match relative cell references: one or more letters NOT preceded
        # by $, followed by the old row number NOT followed by more digits.
        # Examples matched: E2, F2, AB2  |  NOT matched: $K$2, $L$2, E22
        pattern = r'(?<!\$)([A-Za-z]+)' + str(old_row) + r'(?!\d)'
        replacement = r'\g<1>' + str(new_row)
        return re.sub(pattern, replacement, formula)

    def get_last_rows(self, tab_name: str, count: int = 5) -> list[list[str]]:
        """Get the last N data rows from a monthly tab."""
        ws = self.get_worksheet(tab_name)
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return []
        data_rows = all_values[1:]  # skip header
        return data_rows[-count:]

    def delete_last_row(self, tab_name: str) -> list[str] | None:
        """Delete the last data row from a monthly tab.

        Returns the deleted row data, or None if there are no data rows.
        """
        ws = self.get_worksheet(tab_name)
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return None
        last_row_index = len(all_values)
        deleted_data = all_values[-1]
        ws.delete_rows(last_row_index)
        logger.info("Deleted row %d from sheet '%s'", last_row_index, tab_name)
        return deleted_data

    def get_summary(self, tab_name: str) -> dict[str, float]:
        """Get spending totals by category for a monthly tab.

        Returns a dict of {category: total_czk}.
        """
        ws = self.get_worksheet(tab_name)
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return {}

        summary: dict[str, float] = {}
        for row in all_values[1:]:
            if len(row) <= COL_TOTAL_CZK:
                continue
            category = row[COL_CATEGORY].strip()
            total_czk_str = row[COL_TOTAL_CZK].strip()
            if not category or not total_czk_str:
                continue
            try:
                # Handle comma as decimal separator
                total_czk = float(total_czk_str.replace(",", ".").replace(" ", ""))
                summary[category] = summary.get(category, 0.0) + total_czk
            except ValueError:
                continue

        return summary
