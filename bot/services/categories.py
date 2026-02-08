from __future__ import annotations

import logging
import time

from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)

# Refresh categories automatically every hour
CACHE_TTL_SECONDS: float = 3600.0


class CategoryCache:
    """In-memory cache for expense categories read from Google Sheets."""

    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets
        self._categories: list[str] = []
        self._last_refresh: float = 0.0

    @property
    def categories(self) -> list[str]:
        """Return cached categories, refreshing if stale."""
        if self._is_stale():
            self.refresh()
        return self._categories

    def refresh(self) -> list[str]:
        """Force-refresh categories from the Google Sheet."""
        try:
            self._categories = self._sheets.read_categories()
            self._last_refresh = time.time()
            logger.info(
                "Category cache refreshed: %d categories loaded",
                len(self._categories),
            )
        except Exception as exc:
            logger.error("Failed to refresh categories: %s", exc)
            if not self._categories:
                raise
            # Keep stale cache if refresh fails and we have old data
            logger.warning("Using stale category cache (%d items)", len(self._categories))
        return self._categories

    def _is_stale(self) -> bool:
        return (
            not self._categories
            or (time.time() - self._last_refresh) > CACHE_TTL_SECONDS
        )
