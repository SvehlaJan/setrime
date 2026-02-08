from __future__ import annotations

import logging
import traceback
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.auth import check_authorized
from bot.models import COL_CATEGORY, COL_DATE, COL_DESCRIPTION, COL_TOTAL_CZK
from bot.services.categories import CategoryCache
from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles bot commands: /start, /help, /summary, /last, /undo, /categories."""

    def __init__(
        self,
        sheets: SheetsService,
        category_cache: CategoryCache,
        allowed_user_ids: list[int],
    ) -> None:
        self._sheets = sheets
        self._categories = category_cache
        self._allowed_user_ids = allowed_user_ids

    async def start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        if not await check_authorized(update, context, self._allowed_user_ids):
            return
        await self._reply(
            update,
            "👋 Welcome to the Expense Bot!\n\n"
            "Send me a text message describing an expense, or a screenshot "
            "from your banking app, and I'll log it to your Google Sheet.\n\n"
            "Type /help to see all available commands.",
        )

    async def help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command."""
        if not await check_authorized(update, context, self._allowed_user_ids):
            return
        await self._reply(
            update,
            "📖 *Available Commands*\n\n"
            "/help — Show this help message\n"
            "/categories — List expense categories\n"
            "/summary — Monthly totals by category\n"
            "/last — Show last 5 expenses\n"
            "/undo — Remove the last expense\n\n"
            "*Usage*\n"
            "• Send a text message with an expense (e.g., `obed 185 Kč`)\n"
            "• Send a banking app screenshot\n"
            "• Add a caption to a screenshot for extra context\n\n"
            "The bot will parse the expense and ask follow-up questions "
            "if any information is missing.",
            parse_mode="Markdown",
        )

    async def categories(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /categories command — list and refresh categories."""
        if not await check_authorized(update, context, self._allowed_user_ids):
            return

        try:
            cats = self._categories.refresh()
        except Exception as exc:
            logger.error("Failed to load categories: %s\n%s", exc, traceback.format_exc())
            await self._reply(
                update,
                f"❌ Error loading categories: {exc}",
            )
            return

        if not cats:
            await self._reply(update, "No categories found in the Google Sheet.")
            return

        numbered = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(cats))
        await self._reply(
            update,
            f"📁 *Expense Categories* ({len(cats)} total):\n\n{numbered}\n\n"
            "_(refreshed from Google Sheet)_",
            parse_mode="Markdown",
        )

    async def summary(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /summary [MM/YYYY] — show monthly totals by category."""
        if not await check_authorized(update, context, self._allowed_user_ids):
            return

        tab_name = self._get_tab_arg(context) or date.today().strftime("%m/%Y")

        try:
            totals = self._sheets.get_summary(tab_name)
        except Exception as exc:
            logger.error(
                "Failed to get summary for '%s': %s\n%s",
                tab_name,
                exc,
                traceback.format_exc(),
            )
            await self._reply(
                update,
                f"❌ Error getting summary for `{tab_name}`: {exc}",
                parse_mode="Markdown",
            )
            return

        if not totals:
            await self._reply(update, f"No expenses found in `{tab_name}`.", parse_mode="Markdown")
            return

        lines: list[str] = []
        grand_total = 0.0
        for category in sorted(totals.keys()):
            amount = totals[category]
            grand_total += amount
            lines.append(f"  {category}: {amount:,.0f} CZK")

        lines.append(f"\n  *Total: {grand_total:,.0f} CZK*")

        await self._reply(
            update,
            f"📊 *Summary for {tab_name}*\n\n" + "\n".join(lines),
            parse_mode="Markdown",
        )

    async def last(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /last [N] — show last N expenses from current month."""
        if not await check_authorized(update, context, self._allowed_user_ids):
            return

        count = 5
        if context.args:
            try:
                count = max(1, min(20, int(context.args[0])))
            except ValueError:
                pass

        tab_name = date.today().strftime("%m/%Y")

        try:
            rows = self._sheets.get_last_rows(tab_name, count)
        except Exception as exc:
            logger.error(
                "Failed to get last rows from '%s': %s\n%s",
                tab_name,
                exc,
                traceback.format_exc(),
            )
            await self._reply(
                update,
                f"❌ Error reading from `{tab_name}`: {exc}",
                parse_mode="Markdown",
            )
            return

        if not rows:
            await self._reply(update, f"No expenses found in `{tab_name}`.", parse_mode="Markdown")
            return

        lines: list[str] = []
        for row in rows:
            # Row: [A:Date, B:empty, C:Category, D:Desc, E:PLN, F:CZK, G:EUR, H:Total]
            row_date = row[COL_DATE] if len(row) > COL_DATE else "?"
            category = row[COL_CATEGORY] if len(row) > COL_CATEGORY else "?"
            desc = row[COL_DESCRIPTION] if len(row) > COL_DESCRIPTION else "?"
            total = row[COL_TOTAL_CZK] if len(row) > COL_TOTAL_CZK else "?"
            lines.append(f"  {row_date} | {category} | {desc} | {total} CZK")

        await self._reply(
            update,
            f"📋 *Last {len(rows)} expenses ({tab_name})*\n\n" + "\n".join(lines),
            parse_mode="Markdown",
        )

    async def undo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /undo — remove the last expense from the current month."""
        if not await check_authorized(update, context, self._allowed_user_ids):
            return

        tab_name = date.today().strftime("%m/%Y")

        try:
            deleted = self._sheets.delete_last_row(tab_name)
        except Exception as exc:
            logger.error(
                "Failed to undo from '%s': %s\n%s",
                tab_name,
                exc,
                traceback.format_exc(),
            )
            await self._reply(
                update,
                f"❌ Error undoing from `{tab_name}`: {exc}",
                parse_mode="Markdown",
            )
            return

        if deleted is None:
            await self._reply(update, f"No expenses to undo in `{tab_name}`.", parse_mode="Markdown")
            return

        row_date = deleted[COL_DATE] if len(deleted) > COL_DATE else "?"
        category = deleted[COL_CATEGORY] if len(deleted) > COL_CATEGORY else "?"
        desc = deleted[COL_DESCRIPTION] if len(deleted) > COL_DESCRIPTION else "?"
        total = deleted[COL_TOTAL_CZK] if len(deleted) > COL_TOTAL_CZK else "?"

        await self._reply(
            update,
            f"🗑️ Removed last expense from `{tab_name}`:\n"
            f"  {row_date} | {category} | {desc} | {total} CZK",
            parse_mode="Markdown",
        )

        logger.info(
            "Undo: removed row from '%s': %s",
            tab_name,
            " | ".join(deleted),
        )

    @staticmethod
    def _get_tab_arg(context: ContextTypes.DEFAULT_TYPE) -> str | None:
        """Extract a tab name argument from the command (e.g., /summary 02/2026)."""
        if context.args:
            return context.args[0]
        return None

    @staticmethod
    async def _reply(
        update: Update, text: str, parse_mode: str | None = None
    ) -> None:
        """Send a reply message."""
        if update.effective_chat:
            await update.effective_chat.send_message(
                text=text, parse_mode=parse_mode
            )
