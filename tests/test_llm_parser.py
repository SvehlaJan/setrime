"""Tests for bot.services.llm_parser — JSON parsing logic.

These tests exercise the response parsing without calling the Gemini API.
"""
from __future__ import annotations

from datetime import date

import pytest

from bot.services.llm_parser import LLMParser


class FakeResponse:
    """Minimal fake for Gemini API response."""

    def __init__(self, text: str) -> None:
        self.text = text


class TestParseResponse:
    """Test _parse_response which converts raw LLM JSON into ParsedExpense."""

    def _make_parser(self) -> LLMParser:
        # We never call the API, just test the parsing logic.
        # Use a dummy key — the client is never used in these tests.
        return LLMParser.__new__(LLMParser)

    def test_basic_json(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": "2026-02-08", "amount": 450, "currency": "CZK", '
            '"category": "Potraviny", "description": "Albert"}'
        )
        result = parser._parse_response(resp)
        assert result.date == date(2026, 2, 8)
        assert result.amount == 450.0
        assert result.currency == "CZK"
        assert result.category == "Potraviny"
        assert result.description == "Albert"

    def test_null_fields(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": "2026-02-08", "amount": 185, "currency": "CZK", '
            '"category": null, "description": "obed"}'
        )
        result = parser._parse_response(resp)
        assert result.category is None
        assert result.amount == 185.0

    def test_all_null(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": null, "amount": null, "currency": null, '
            '"category": null, "description": null}'
        )
        result = parser._parse_response(resp)
        assert result.date is None
        assert result.amount is None

    def test_markdown_code_fence_stripped(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '```json\n'
            '{"date": "2026-02-08", "amount": 250, "currency": "CZK", '
            '"category": "Stravovanie", "description": "lunch"}\n'
            '```'
        )
        result = parser._parse_response(resp)
        assert result.amount == 250.0
        assert result.currency == "CZK"

    def test_invalid_json_raises(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse("This is not JSON at all")
        with pytest.raises(ValueError, match="LLM returned invalid JSON"):
            parser._parse_response(resp)

    def test_pln_currency(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": "2026-02-02", "amount": 11.7, "currency": "PLN", '
            '"category": "Potraviny", "description": "Albert"}'
        )
        result = parser._parse_response(resp)
        assert result.currency == "PLN"
        assert result.amount == 11.7

    def test_eur_currency(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": "2026-02-03", "amount": 118, "currency": "EUR", '
            '"category": "Reštika", "description": "Kafe"}'
        )
        result = parser._parse_response(resp)
        assert result.currency == "EUR"

    def test_negative_amount_becomes_none(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": null, "amount": -50, "currency": "CZK", '
            '"category": null, "description": "refund"}'
        )
        result = parser._parse_response(resp)
        assert result.amount is None

    def test_zero_amount_becomes_none(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": null, "amount": 0, "currency": "CZK", '
            '"category": null, "description": "free"}'
        )
        result = parser._parse_response(resp)
        assert result.amount is None

    def test_invalid_date_becomes_none(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": "not-a-date", "amount": 100, "currency": "CZK", '
            '"category": null, "description": "test"}'
        )
        result = parser._parse_response(resp)
        assert result.date is None

    def test_invalid_currency_becomes_none(self) -> None:
        parser = self._make_parser()
        resp = FakeResponse(
            '{"date": null, "amount": 100, "currency": "USD", '
            '"category": null, "description": "test"}'
        )
        result = parser._parse_response(resp)
        assert result.currency is None


class TestStaticParsers:
    def test_parse_date_valid(self) -> None:
        assert LLMParser._parse_date("2026-02-08") == date(2026, 2, 8)

    def test_parse_date_none(self) -> None:
        assert LLMParser._parse_date(None) is None

    def test_parse_date_invalid(self) -> None:
        assert LLMParser._parse_date("invalid") is None

    def test_parse_amount_valid(self) -> None:
        assert LLMParser._parse_amount(450) == 450.0
        assert LLMParser._parse_amount(11.7) == 11.7

    def test_parse_amount_none(self) -> None:
        assert LLMParser._parse_amount(None) is None

    def test_parse_amount_zero(self) -> None:
        assert LLMParser._parse_amount(0) is None

    def test_parse_amount_negative(self) -> None:
        assert LLMParser._parse_amount(-5) is None

    def test_parse_currency_valid(self) -> None:
        assert LLMParser._parse_currency("CZK") == "CZK"
        assert LLMParser._parse_currency("pln") == "PLN"
        assert LLMParser._parse_currency("EUR") == "EUR"

    def test_parse_currency_invalid(self) -> None:
        assert LLMParser._parse_currency("USD") is None
        assert LLMParser._parse_currency("") is None

    def test_parse_currency_none(self) -> None:
        assert LLMParser._parse_currency(None) is None
