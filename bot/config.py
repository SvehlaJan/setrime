from __future__ import annotations

import logging
import os
import sys
from typing import Literal

from dotenv import load_dotenv

from bot.models import Currency

logger = logging.getLogger(__name__)

load_dotenv()


class AppConfig:
    """Application configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.telegram_bot_token: str = self._require("TELEGRAM_BOT_TOKEN")
        self.gemini_api_key: str = self._require("GEMINI_API_KEY")
        self.google_sheet_id: str = self._require("GOOGLE_SHEET_ID")
        self.google_credentials_file: str = self._require("GOOGLE_CREDENTIALS_FILE")

        raw_ids = self._require("ALLOWED_USER_IDS")
        self.allowed_user_ids: list[int] = [
            int(uid.strip()) for uid in raw_ids.split(",") if uid.strip()
        ]

        default_cur = os.getenv("DEFAULT_CURRENCY", "CZK").upper()
        if default_cur not in ("CZK", "PLN", "EUR"):
            logger.warning(
                "Invalid DEFAULT_CURRENCY '%s', falling back to CZK", default_cur
            )
            default_cur = "CZK"
        self.default_currency: Currency = default_cur  # type: ignore[assignment]

        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @staticmethod
    def _require(name: str) -> str:
        value = os.getenv(name)
        if not value:
            logger.critical("Missing required environment variable: %s", name)
            sys.exit(1)
        return value


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging to stdout."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
