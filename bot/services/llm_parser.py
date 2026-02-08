from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from google import genai
from google.genai import types as genai_types
from PIL import Image

from bot.models import Currency, ParsedExpense

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
You are an expense parser. The user tracks expenses in a Google Sheet.

INPUT:
- Text messages are typically in SLOVAK language (sometimes Czech or English)
- Images are banking app screenshots from Czech, Slovak, or Polish banks, or Revolut
- Screenshots may be in English, Czech, or Slovak

EXTRACT these fields:
- date: in YYYY-MM-DD format. Default to {today} if not specified.
- amount: numeric value (use dot as decimal separator, no thousand separators)
- currency: one of "CZK", "PLN", "EUR". Default to "{default_currency}" if ambiguous.
  Recognize: Kč=CZK, zł=PLN, €=EUR.
- category: one of these EXACT Slovak values: [{categories}]
  Match the expense to the best category. The categories are in Slovak.
  If unsure, set to null.
- description: merchant name, payee, or brief description of the expense

Handle Czech/Slovak/Polish number formatting:
- "1 234,50" means 1234.50
- "1.234,50" means 1234.50

Return ONLY a JSON object:
{{
  "date": "YYYY-MM-DD",
  "amount": 123.45,
  "currency": "CZK",
  "category": "...",
  "description": "..."
}}

For any field you cannot determine, set it to null.
Do NOT include any text outside the JSON object.
"""


class LLMParser:
    """Parses expense information from text or images using Gemini."""

    def __init__(
        self, api_key: str, default_currency: Currency = "CZK"
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = "gemini-2.0-flash"
        self._default_currency = default_currency
        logger.info("LLM parser initialized with %s", self._model)

    def _build_prompt(self, categories: list[str]) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(
            today=date.today().isoformat(),
            default_currency=self._default_currency,
            categories=", ".join(f'"{c}"' for c in categories),
        )

    async def parse_text(
        self, text: str, categories: list[str]
    ) -> ParsedExpense:
        """Parse an expense from a free-form text message."""
        prompt = self._build_prompt(categories)
        full_prompt = f"{prompt}\n\nUser message:\n{text}"

        logger.debug("Sending text to LLM: %s", text)
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=full_prompt,
        )
        return self._parse_response(response)

    async def parse_image(
        self,
        image: Image.Image,
        categories: list[str],
        caption: str | None = None,
    ) -> ParsedExpense:
        """Parse an expense from a banking app screenshot."""
        prompt = self._build_prompt(categories)
        if caption:
            prompt += f"\n\nUser also sent this message with the image:\n{caption}"
        else:
            prompt += "\n\nExtract the expense from the following banking app screenshot."

        logger.debug("Sending image to LLM (size: %s)", image.size)
        contents: list[str | Image.Image] = [prompt, image]
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,  # type: ignore[arg-type]
        )
        return self._parse_response(response)

    def _parse_response(self, response: Any) -> ParsedExpense:
        """Extract JSON from the LLM response and parse into a model."""
        raw_text: str = response.text.strip()
        logger.debug("Raw LLM response: %s", raw_text)

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [line for line in lines if not line.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        try:
            data: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM JSON response: %s\nRaw: %s", exc, raw_text)
            raise ValueError(
                f"LLM returned invalid JSON: {exc}\nRaw response: {raw_text}"
            ) from exc

        return ParsedExpense(
            date=self._parse_date(data.get("date")),
            amount=self._parse_amount(data.get("amount")),
            currency=self._parse_currency(data.get("currency")),
            category=data.get("category"),
            description=data.get("description"),
        )

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value is None:
            return None
        try:
            return date.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_amount(value: Any) -> float | None:
        if value is None:
            return None
        try:
            result = float(value)
            return result if result > 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_currency(value: Any) -> Currency | None:
        if value is None:
            return None
        val = str(value).upper().strip()
        if val in ("CZK", "PLN", "EUR"):
            return val  # type: ignore[return-value]
        return None
